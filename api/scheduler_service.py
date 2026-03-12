"""
Scheduler service using APScheduler
Handles cron-based job scheduling with optimizations
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from datetime import datetime
import pytz
import json
import random
import time
import os


class SchedulerService:
    # Configuration constants
    BATCH_SIZE = 50  # Queue 50 leads at a time
    MAX_QUEUE_PER_SCHEDULE = 200  # Max 200 leads per schedule run
    MAX_QUEUE_SIZE = 500  # Don't queue if already 500+ jobs in queue
    MAX_RETRIES = 3  # Retry failed schedule execution
    STAGGER_MAX_DELAY = 30  # Max 30 seconds random delay for concurrent schedules
    
    def __init__(self, database):
        self.db = database
        self.scheduler = BackgroundScheduler()
        self.running = False
    
    def start(self):
        """Start the scheduler with proper timezone and event listeners"""
        if not self.running:
            # Get timezone from environment
            tz = self.get_scheduler_timezone()
            
            if tz:
                print(f"🌍 Using timezone: {tz}")
                self.scheduler.configure(timezone=tz)
            else:
                print("⚠️ Using UTC timezone (pytz not available)")
            
            # Add event listeners for monitoring
            self.scheduler.add_listener(self._job_executed, EVENT_JOB_EXECUTED)
            self.scheduler.add_listener(self._job_error, EVENT_JOB_ERROR)
            
            self.scheduler.start()
            self.running = True
            
            print(f"✅ Scheduler started (timezone: {tz or 'UTC'})")
            
            # Load existing schedules
            self._load_schedules()
    
    def stop(self):
        """Stop the scheduler"""
        if self.running:
            self.scheduler.shutdown()
            self.running = False
    
    def is_running(self):
        """Check if scheduler is running"""
        return self.running
    
    def _load_schedules(self):
        """Load all active schedules from database"""
        from helper.supabase_helper import ScheduleManager
        
        # Get active schedules using ScheduleManager
        schedules = ScheduleManager.get_all_simple()
        active_schedules = [s for s in schedules if s.get('status') == 'active']
        
        print(f"📋 Loading {len(active_schedules)} active schedules...")
        
        for schedule in active_schedules:
            try:
                print(f"   Loading schedule: {schedule.get('name', 'Unknown')} (ID: {schedule['id']})")
                self.add_job(schedule['id'])
                print(f"✓ Loaded schedule: {schedule['name']}")
            except Exception as e:
                print(f"✗ Failed to load schedule {schedule['name']}: {e}")
    
    def add_job(self, schedule_id: str):
        """Add job to scheduler with conflict detection"""
        # Use ScheduleManager instead of db to avoid connection issues
        from helper.supabase_helper import ScheduleManager
         
        schedule = ScheduleManager.get_by_id(schedule_id)
        if not schedule:
            raise ValueError(f"Schedule {schedule_id} not found")
        
        if schedule['status'] != 'active':
            return
        
        # OPTIMIZATION: Schedule conflict detection
        template_id = schedule.get('template_id')
        if template_id:
            self._check_schedule_conflicts(schedule_id, template_id, schedule['start_schedule'])
        
        # Parse cron expression with validation
        cron_parts = schedule['start_schedule'].split()
        if len(cron_parts) != 5:
            raise ValueError(f"Invalid cron expression: {schedule['start_schedule']}")
        
        # Validate cron expression using croniter
        validation = self.validate_cron_expression(schedule['start_schedule'])
        if not validation['valid']:
            raise ValueError(f"Invalid cron expression '{schedule['start_schedule']}': {validation['error']}")
        
        minute, hour, day, month, day_of_week = cron_parts
        
        # OPTIMIZATION: Smart scheduling validation
        self._validate_smart_scheduling(hour, day_of_week)
        
        # Create trigger with timezone from environment
        tz = self.get_scheduler_timezone()
        if tz:
            print(f"   Using timezone: {tz}")
        else:
            print(f"   ⚠️ pytz not installed or timezone error, using UTC")
            print(f"   Install pytz: pip install pytz")
            print(f"   Set SCHEDULER_TIMEZONE environment variable")
        
        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=tz
        )
        
        # Add job
        try:
            self.scheduler.add_job(
                func=self._execute_crawl,
                trigger=trigger,
                id=schedule_id,
                args=[schedule_id],
                replace_existing=True,
                name=schedule['name']
            )
            print(f"   ✓ Job added successfully")
        except Exception as e:
            print(f"   ❌ Failed to add job: {e}")
            raise
        
        # Show next run time
        try:
            job = self.scheduler.get_job(schedule_id)
            next_run = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z') if job and job.next_run_time else 'Unknown'
            print(f"   ✓ Added job: {schedule['name']} ({schedule['start_schedule']})")
            print(f"   📅 Next run: {next_run}")
        except Exception as e:
            print(f"   ⚠️ Could not get next run time: {e}")
    
    def _check_schedule_conflicts(self, schedule_id: str, template_id: str, cron_expression: str):
        """Check for schedule conflicts with same template"""
        # Get all active schedules
        all_schedules = self.db.get_active_schedules()
        
        conflicts = []
        for sched in all_schedules:
            if sched['id'] == schedule_id:
                continue
            
            # Check if same template
            if sched.get('template_id') == template_id:
                # Check if same time
                if sched.get('start_schedule') == cron_expression:
                    conflicts.append(sched['name'])
        
        if conflicts:
            print(f"⚠️ SCHEDULE CONFLICT DETECTED:")
            print(f"   Schedule: {schedule_id}")
            print(f"   Template: {template_id}")
            print(f"   Conflicts with: {', '.join(conflicts)}")
            print(f"   Multiple schedules for same template at same time may cause issues")
            print(f"   Consider consolidating or staggering execution times")
    
    def _validate_smart_scheduling(self, hour: str, day_of_week: str):
        """Validate and suggest optimal scheduling times"""
        # Parse hour (can be */2, 9, 9-17, etc)
        try:
            if hour.isdigit():
                hour_int = int(hour)
                
                # Check if outside business hours
                if hour_int < 6 or hour_int > 22:
                    print(f"⚠️ SCHEDULING SUGGESTION:")
                    print(f"   Scheduled at {hour_int}:00 (outside typical business hours)")
                    print(f"   LinkedIn is less active during late night/early morning")
                    print(f"   Consider scheduling between 8 AM - 6 PM for better results")
                
                # Optimal times
                optimal_hours = [9, 14, 17]  # 9 AM, 2 PM, 5 PM
                if hour_int in optimal_hours:
                    print(f"✅ Optimal scheduling time: {hour_int}:00")
        except:
            pass  # Complex hour expression, skip validation
        
        # Check if weekend
        if day_of_week in ['6', '7', 'sat', 'sun']:
            print(f"⚠️ SCHEDULING SUGGESTION:")
            print(f"   Scheduled on weekend (day_of_week: {day_of_week})")
            print(f"   LinkedIn activity is lower on weekends")
            print(f"   Consider scheduling on weekdays (1-5) for better results")
    
    def remove_job(self, schedule_id: str):
        """Remove job from scheduler"""
        try:
            self.scheduler.remove_job(schedule_id)
            print(f"✓ Removed job: {schedule_id}")
        except Exception as e:
            print(f"✗ Failed to remove job {schedule_id}: {e}")
    
    def pause_job(self, schedule_id: str):
        """Pause job"""
        try:
            self.scheduler.pause_job(schedule_id)
            print(f"✓ Paused job: {schedule_id}")
        except Exception as e:
            print(f"✗ Failed to pause job {schedule_id}: {e}")
    
    def resume_job(self, schedule_id: str):
        """Resume job"""
        try:
            self.scheduler.resume_job(schedule_id)
            print(f"✓ Resumed job: {schedule_id}")
        except Exception as e:
            print(f"✗ Failed to resume job {schedule_id}: {e}")
    
    def reschedule_job(self, schedule_id: str):
        """Reschedule job (remove and add again)"""
        self.remove_job(schedule_id)
        self.add_job(schedule_id)
    
    def _job_executed(self, event):
        """Event listener for successful job execution"""
        job_id = event.job_id
        print(f"✅ Job executed successfully: {job_id}")
    
    def _job_error(self, event):
        """Event listener for job execution errors"""
        job_id = event.job_id
        exception = event.exception
        print(f"❌ Job execution failed: {job_id}")
        print(f"   Error: {exception}")
        
        # Log the error to database
        try:
            self.log_execution(job_id, 'failed', 0, str(exception))
        except Exception as e:
            print(f"⚠️ Failed to log job error: {e}")
    
    def validate_cron_expression(self, cron_expression: str) -> dict:
        """Validate cron expression and return next run times"""
        try:
            from croniter import croniter
            import pytz
            
            # Get timezone
            tz = self.get_scheduler_timezone()
            
            # Validate cron expression
            if not croniter.is_valid(cron_expression):
                return {
                    'valid': False,
                    'error': 'Invalid cron expression format'
                }
            
            # Get next run times
            now = datetime.now(tz)
            cron = croniter(cron_expression, now)
            
            next_runs = []
            for _ in range(5):  # Get next 5 runs
                next_run = cron.get_next(datetime)
                next_runs.append(next_run.strftime('%Y-%m-%d %H:%M:%S %Z'))
            
            return {
                'valid': True,
                'next_runs': next_runs,
                'timezone': str(tz)
            }
            
        except ImportError:
            return {
                'valid': False,
                'error': 'croniter library not installed. Run: pip install croniter'
            }
        except Exception as e:
            return {
                'valid': False,
                'error': f'Validation error: {str(e)}'
            }
    
    def get_scheduler_timezone(self):
        """Get scheduler timezone from environment or default to Asia/Jakarta"""
        try:
            import pytz
            import os
            
            # Get timezone from environment variable
            tz_name = os.getenv('SCHEDULER_TIMEZONE', 'Asia/Jakarta')
            return pytz.timezone(tz_name)
            
        except ImportError:
            print("⚠️ pytz not installed, using UTC")
            return None
        except Exception as e:
            print(f"⚠️ Timezone error: {e}, using UTC")
            return None
    
    def log_execution(self, schedule_id: str, status: str, leads_queued: int = 0, error_message: str = None):
        """Simple logging to database"""
        try:
            from helper.supabase_helper import supabase
            
            supabase.table('scheduler_logs').insert({
                'schedule_id': schedule_id,
                'status': status,
                'leads_queued': leads_queued,
                'error_message': error_message
            }).execute()
            
            print(f"📝 Logged: {status} - {leads_queued} leads")
            
        except Exception as e:
            print(f"⚠️ Failed to log (non-critical): {e}")
    
    def _execute_crawl_with_retry(self, schedule_id: str):
        """Execute crawl with proper retry logic and logging"""
        max_retries = self.MAX_RETRIES
        base_delay = 5  # seconds
        
        for attempt in range(max_retries + 1):
            try:
                start_time = time.time()
                print(f"\n{'='*80}")
                print(f"🔥 SCHEDULER TRIGGERED - ATTEMPT {attempt + 1}/{max_retries + 1}")
                print(f"{'='*80}")
                
                result = self._execute_crawl_internal(schedule_id)
                
                # Log success
                self.log_execution(schedule_id, 'success', result.get('leads_queued', 0))
                print(f"✅ Schedule execution completed successfully")
                return result
                
            except Exception as e:
                if attempt == max_retries:
                    # Final failure
                    error_msg = f"Failed after {max_retries + 1} attempts: {str(e)}"
                    self.log_execution(schedule_id, 'failed', 0, error_msg)
                    print(f"❌ FINAL FAILURE: {error_msg}")
                    
                    # TODO: Send alert (implement in Phase 3)
                    # self.send_failure_alert(schedule_id, error_msg)
                    
                    return {"success": False, "error": error_msg}
                else:
                    # Retry with exponential backoff
                    delay = base_delay * (2 ** attempt)
                    print(f"⚠️ Attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                    time.sleep(delay)
    
    def _execute_crawl(self, schedule_id: str):
        """Main entry point - delegates to retry wrapper"""
        return self._execute_crawl_with_retry(schedule_id)
    
    def _execute_crawl_internal(self, schedule_id: str):
        """Internal execution logic (called by retry wrapper)"""
        print(f"⏰ Execution Time: {datetime.now()}")
        print(f"📋 Schedule ID: {schedule_id}")
        
        # OPTIMIZATION: Concurrent schedule handling - Stagger execution
        stagger_delay = random.uniform(0, self.STAGGER_MAX_DELAY)
        print(f"⏱️ Staggering execution by {stagger_delay:.1f}s to avoid concurrent overload")
        time.sleep(stagger_delay)
        
        # CRITICAL: Import fresh in thread to avoid connection issues
        from helper.supabase_helper import SupabaseManager
        from helper.rabbitmq_helper import queue_publisher
        
        # Create fresh Supabase manager for this thread
        supabase_manager = SupabaseManager()
        
        # Get schedule using fresh connection
        schedule = supabase_manager.supabase.table('crawler_schedules').select('*').eq('id', schedule_id).execute()
        if not schedule.data:
            print(f"✗ Schedule {schedule_id} not found")
            return {"success": False, "error": "Schedule not found"}
        
        schedule = schedule.data[0]
        
        # Update last run timestamp (non-critical, skip if fails)
        try:
            supabase_manager.supabase.table('crawler_schedules').update({
                'last_run': datetime.now().isoformat()
            }).eq('id', schedule_id).execute()
        except Exception as e:
            print(f"⚠️ Failed to update last_run (non-critical): {e}")
        
        # Get template_id from schedule
        template_id = schedule.get('template_id')
        if not template_id:
            print("⚠ No template_id configured in schedule")
            return {"success": False, "error": "No template_id configured"}
        
        print(f"📋 Template ID: {template_id}")
        print(f"📝 Schedule Name: {schedule.get('name', 'Unnamed')}")
        
        # OPTIMIZATION: Queue size check - Prevent overload
        print(f"🔍 Checking current queue size...")
        queue_info = queue_publisher.get_queue_info()
        current_queue_size = queue_info.get('messages', 0) if queue_info else 0
        print(f"📊 Current queue size: {current_queue_size} jobs")
        
        if current_queue_size > self.MAX_QUEUE_SIZE:
            print(f"⚠️ Queue too large ({current_queue_size} > {self.MAX_QUEUE_SIZE})")
            print(f"   Skipping this schedule run to prevent overload")
            print(f"   Will retry in next scheduled time")
            return {"success": False, "error": "Queue overload", "skipped": True}
        
        # Get leads for this template
        print(f"🔍 Fetching leads from database...")
        leads = supabase_manager.get_leads_by_template_id(template_id)
        
        if not leads:
            print("⚠ No leads found for template - auto-deactivating schedule")
            
            # Auto-deactivate schedule if no leads exist
            try:
                from helper.supabase_helper import ScheduleManager
                schedule_manager = ScheduleManager()
                schedule_manager.update_schedule_status(schedule_id, False)
                print(f"✅ Auto-deactivated schedule - no leads found")
            except Exception as e:
                print(f"⚠️ Failed to auto-deactivate schedule: {e}")
            
            return {"success": True, "leads_queued": 0, "message": "No leads found - schedule deactivated"}
        
        # Filter leads that need processing
        needs_processing = [lead for lead in leads if lead.get('needs_processing', False)]
        
        if not needs_processing:
            print("✓ All leads already complete, auto-deactivating schedule")
            
            # Auto-deactivate schedule if no leads need processing
            try:
                from helper.supabase_helper import ScheduleManager
                schedule_manager = ScheduleManager()
                schedule_manager.update_schedule_status(schedule_id, False)
                print(f"✅ Auto-deactivated schedule - all leads complete")
            except Exception as e:
                print(f"⚠️ Failed to auto-deactivate schedule: {e}")
            
            return {"success": True, "leads_queued": 0, "message": "All leads complete - schedule deactivated"}
        
        print(f"📊 Found {len(needs_processing)} leads that need processing")
        
        # OPTIMIZATION: Batching - Limit total leads per run
        leads_to_queue = needs_processing[:self.MAX_QUEUE_PER_SCHEDULE]
        
        if len(needs_processing) > self.MAX_QUEUE_PER_SCHEDULE:
            print(f"⚠️ Limiting to {self.MAX_QUEUE_PER_SCHEDULE} leads per run")
            print(f"   Total leads: {len(needs_processing)}")
            print(f"   Remaining: {len(needs_processing) - self.MAX_QUEUE_PER_SCHEDULE} (will be queued in next run)")
        
        # Queue in batches
        queued_count = 0
        failed_count = 0
        total_batches = (len(leads_to_queue) + self.BATCH_SIZE - 1) // self.BATCH_SIZE
        
        print(f"📤 Queueing {len(leads_to_queue)} leads in {total_batches} batches...")
        
        for i in range(0, len(leads_to_queue), self.BATCH_SIZE):
            batch = leads_to_queue[i:i + self.BATCH_SIZE]
            batch_num = i // self.BATCH_SIZE + 1
            print(f"   Batch {batch_num}/{total_batches}: {len(batch)} leads...", end=' ')
            
            batch_success = 0
            for lead in batch:
                success = queue_publisher.publish_crawler_job(
                    profile_url=lead['profile_url'],
                    template_id=template_id
                )
                if success:
                    queued_count += 1
                    batch_success += 1
                else:
                    failed_count += 1
            
            print(f"✓ {batch_success} queued")
            
            # Small delay between batches to avoid overwhelming queue
            if i + self.BATCH_SIZE < len(leads_to_queue):
                time.sleep(0.5)  # 500ms delay between batches
        
        # Success summary
        print(f"\n{'='*60}")
        print(f"✅ SCHEDULE EXECUTION COMPLETED")
        print(f"   Successfully queued: {queued_count} leads")
        if failed_count > 0:
            print(f"   Failed to queue: {failed_count} leads")
        if len(needs_processing) > self.MAX_QUEUE_PER_SCHEDULE:
            remaining = len(needs_processing) - self.MAX_QUEUE_PER_SCHEDULE
            print(f"   Remaining for next run: {remaining} leads")
        print(f"   Execution time: {datetime.now()}")
        print(f"{'='*60}\n")
        
        # Update global crawl session (SCHEDULED trigger)
        try:
            import sys
            import pytz
            
            # Get Jakarta timezone for consistent timestamps
            jakarta_tz = pytz.timezone('Asia/Jakarta')
            started_at_jakarta = datetime.now(jakarta_tz).isoformat()
            
            # Try to find main module in sys.modules
            main_module = None
            for module_name in ['main', '__main__', 'backend.api.main']:
                if module_name in sys.modules:
                    main_module = sys.modules[module_name]
                    if hasattr(main_module, 'current_crawl_session'):
                        break
            
            if main_module and hasattr(main_module, 'current_crawl_session'):
                # Get template name from database
                try:
                    template = supabase_manager.get_template_by_id(template_id)
                    template_name = template.get('name', 'Unknown Template') if template else f"Template {template_id[:8]}"
                except Exception as e:
                    print(f"⚠️ Failed to get template name: {e}")
                    template_name = f"Template {template_id[:8]}"
                
                main_module.current_crawl_session = {
                    'is_active': True,
                    'source': 'scheduled',
                    'schedule_id': schedule_id,
                    'schedule_name': schedule.get('name', 'Unknown Schedule'),
                    'template_id': template_id,
                    'template_name': template_name,
                    'started_at': started_at_jakarta,
                    'leads_queued': queued_count
                }
                print(f"✅ Updated crawl session for scheduled run")
            else:
                print(f"⚠️ Could not update crawl session - main module not accessible")
                
        except Exception as e:
            print(f"⚠️ Failed to update crawl session: {e}")
        
        return {
            "success": True,
            "leads_queued": queued_count,
            "failed_count": failed_count,
            "total_leads": len(needs_processing),
            "remaining_leads": max(0, len(needs_processing) - self.MAX_QUEUE_PER_SCHEDULE)
        }

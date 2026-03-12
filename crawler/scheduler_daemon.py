"""
Crawler Scheduler Daemon
Polls Supabase for scheduled crawl jobs and executes them
Auto-starts crawler consumer when needed
"""
import os
import time
import json
import subprocess
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from supabase import create_client, Client
import logging
import psutil

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

# Supabase client
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

# Config
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', 60))  # 1 minute default
DEFAULT_REQUIREMENTS_ID = os.getenv('DEFAULT_REQUIREMENTS_ID', 'desk_collection')


def get_pending_schedules():
    """Get schedules that should run now based on cron expressions"""
    try:
        # Get active schedules
        response = supabase.table('crawler_schedules').select('*').eq('status', 'active').execute()
        schedules = response.data
        
        pending = []
        now = datetime.now(timezone.utc)  # Use UTC timezone
        current_hour = now.hour
        current_minute = now.minute
        current_day = now.weekday()  # 0=Monday, 6=Sunday
        
        for schedule in schedules:
            start_schedule = schedule.get('start_schedule', '')
            stop_schedule = schedule.get('stop_schedule', '')
            last_run = schedule.get('last_run')
            
            # Check if it's time to run based on cron
            should_run = _should_run_now(
                start_schedule, 
                stop_schedule, 
                current_hour, 
                current_minute, 
                current_day
            )
            
            if should_run:
                # Additional check: don't run too frequently (at least 5 minutes apart)
                if last_run:
                    last_run_time = datetime.fromisoformat(last_run.replace('Z', '+00:00'))
                    time_diff = (now - last_run_time).total_seconds()
                    
                    # Skip if last run was less than 5 minutes ago
                    if time_diff < 300:  # 5 minutes = 300 seconds
                        logger.debug(f"Skipping schedule {schedule['name']} - ran {time_diff:.0f}s ago")
                        continue
                
                pending.append(schedule)
        
        return pending
    
    except Exception as e:
        logger.error(f"Error getting pending schedules: {e}")
        return []


def _should_run_now(start_cron, stop_cron, hour, minute, day):
    """
    Check if crawler should be running based on cron expressions
    Same logic as crawler_manager.py
    """
    try:
        # Parse start cron: "minute hour day month weekday"
        # Example: "0 9 * * *" = every day at 9:00
        # Example: "0 9 * * 1-5" = weekdays at 9:00
        
        if not start_cron:
            return False
        
        parts = start_cron.split()
        if len(parts) < 5:
            return False
        
        start_minute = parts[0]
        start_hour = parts[1]
        # day_of_month = parts[2]  # Not used for now
        # month = parts[3]  # Not used for now
        weekday = parts[4]
        
        # Check weekday first
        if weekday != '*':
            # Parse weekday range (e.g., "1-5" for Mon-Fri)
            if '-' in weekday:
                start_day, end_day = map(int, weekday.split('-'))
                if not (start_day <= day <= end_day):
                    logger.debug(f"Not running - wrong weekday: {day} not in {start_day}-{end_day}")
                    return False
            elif weekday.isdigit():
                if int(weekday) != day:
                    logger.debug(f"Not running - wrong weekday: {day} != {weekday}")
                    return False
        
        # Parse start time
        if start_hour == '*':
            start_h = 0
        else:
            start_h = int(start_hour)
        
        if start_minute == '*':
            start_m = 0
        else:
            start_m = int(start_minute)
        
        # Parse stop time (if exists)
        stop_h = 23
        stop_m = 59
        
        if stop_cron:
            stop_parts = stop_cron.split()
            if len(stop_parts) >= 2:
                if stop_parts[1] != '*':
                    stop_h = int(stop_parts[1])
                if stop_parts[0] != '*':
                    stop_m = int(stop_parts[0])
        
        # Convert current time and schedule times to minutes for easier comparison
        current_minutes = hour * 60 + minute
        start_minutes = start_h * 60 + start_m
        stop_minutes = stop_h * 60 + stop_m
        
        # Check if current time is within the scheduled range
        if start_minutes <= stop_minutes:
            # Normal case: start and stop on same day (e.g., 9:00 to 17:00)
            is_in_range = start_minutes <= current_minutes <= stop_minutes
        else:
            # Overnight case: start late, stop early next day (e.g., 22:00 to 06:00)
            is_in_range = current_minutes >= start_minutes or current_minutes <= stop_minutes
        
        if is_in_range:
            logger.debug(f"Should run - time {hour:02d}:{minute:02d} is within {start_h:02d}:{start_m:02d} to {stop_h:02d}:{stop_m:02d}")
            return True
        else:
            logger.debug(f"Not running - time {hour:02d}:{minute:02d} is outside {start_h:02d}:{start_m:02d} to {stop_h:02d}:{stop_m:02d}")
            return False
    
    except Exception as e:
        logger.error(f"Error parsing cron: {e}")
        return False


def get_unscraped_profiles_from_supabase(limit=100):
    """Get profile URLs from leads_list that haven't been scraped yet
    
    Criteria: profile_data is null or empty
    """
    try:
        # Get leads where profile_data is null or empty
        response = supabase.table('leads_list')\
            .select('profile_url, name')\
            .is_('profile_data', 'null')\
            .limit(limit)\
            .execute()
        
        urls = []
        if response.data:
            for lead in response.data:
                url = lead.get('profile_url')
                if url:
                    urls.append(url)
        
        logger.info(f"Found {len(urls)} unscraped profiles in Supabase")
        return urls
    
    except Exception as e:
        logger.error(f"Error getting unscraped profiles: {e}")
        return []


def execute_schedule(schedule):
    """Execute a scheduled crawl job - Start consumer if needed"""
    schedule_id = schedule['id']
    schedule_name = schedule['name']
    
    logger.info(f"\n{'='*60}")
    logger.info(f"EXECUTING SCHEDULE: {schedule_name}")
    logger.info(f"Schedule ID: {schedule_id}")
    logger.info(f"{'='*60}\n")
    
    # Update last_run
    try:
        supabase.table('crawler_schedules').update({
            'last_run': datetime.now(timezone.utc).isoformat()
        }).eq('id', schedule_id).execute()
        logger.info(f"✓ Updated last_run timestamp")
    except Exception as e:
        logger.error(f"Error updating last_run: {e}")
    
    # Check queue status
    try:
        from helper.rabbitmq_helper import RabbitMQManager
        
        # Use RabbitMQ helper instead of direct pika
        mq = RabbitMQManager()
        
        if mq.connect():
            queue_size = mq.get_queue_size()
            mq.close()
            
            logger.info(f"📊 Queue Status:")
            logger.info(f"   - Queue: {mq.queue_name}")
            logger.info(f"   - Messages waiting: {queue_size}")
            
            if queue_size > 0:
                logger.info(f"✅ Queue has {queue_size} messages ready to be processed")
                
                # Auto-start crawler consumer if not running
                if not is_consumer_running():
                    logger.info(f"🚀 Starting crawler consumer automatically...")
                    start_crawler_consumer()
                else:
                    logger.info(f"✅ Crawler consumer is already running")
            else:
                logger.info(f"ℹ️  Queue is empty - no profiles to process")
        else:
            logger.error(f"✗ Failed to connect to RabbitMQ")
        
    except Exception as e:
        logger.error(f"✗ Failed to check queue: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info(f"\n{'='*60}")
    logger.info(f"SCHEDULE COMPLETED: {schedule_name}")
    logger.info(f"{'='*60}\n")


def is_consumer_running():
    """Check if crawler consumer is already running"""
    import psutil
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and 'python' in cmdline[0] and 'crawler_consumer.py' in ' '.join(cmdline):
                logger.info(f"✅ Found running consumer: PID {proc.info['pid']}")
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    return False


def start_crawler_consumer():
    """Start crawler consumer as background process"""
    import subprocess
    import os
    
    try:
        # Get current directory (should be backend/crawler)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        consumer_path = os.path.join(current_dir, 'crawler_consumer.py')
        
        # Start consumer as background process
        process = subprocess.Popen(
            ['python', consumer_path],
            cwd=current_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
        )
        
        logger.info(f"🚀 Crawler consumer started with PID: {process.pid}")
        logger.info(f"📁 Working directory: {current_dir}")
        logger.info(f"🐍 Command: python {consumer_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to start crawler consumer: {e}")
        return False


def main():
    """Main daemon loop"""
    logger.info("="*60)
    logger.info("CRAWLER SCHEDULER DAEMON STARTED")
    logger.info(f"Poll Interval: {POLL_INTERVAL} seconds")
    logger.info(f"Supabase URL: {os.getenv('SUPABASE_URL')}")
    logger.info("="*60)
    
    while True:
        try:
            logger.info(f"\n[{datetime.now(timezone.utc)}] Checking for pending schedules...")
            
            pending_schedules = get_pending_schedules()
            
            if pending_schedules:
                logger.info(f"Found {len(pending_schedules)} pending schedule(s)")
                
                for schedule in pending_schedules:
                    logger.info(f"Executing schedule: {schedule['name']}")
                    logger.info(f"  Start: {schedule.get('start_schedule', 'N/A')}")
                    logger.info(f"  Stop: {schedule.get('stop_schedule', 'N/A')}")
                    execute_schedule(schedule)
            else:
                # Show current time and why no schedules are running
                now = datetime.now(timezone.utc)
                logger.info(f"No pending schedules at {now.strftime('%H:%M')} UTC (weekday: {now.weekday()})")
                
                # Show all active schedules for debugging
                try:
                    response = supabase.table('crawler_schedules').select('name, start_schedule, stop_schedule, status').eq('status', 'active').execute()
                    if response.data:
                        logger.info("Active schedules:")
                        for schedule in response.data:
                            logger.info(f"  - {schedule['name']}: {schedule.get('start_schedule', 'N/A')} to {schedule.get('stop_schedule', 'N/A')}")
                    else:
                        logger.info("No active schedules found in database")
                except Exception as e:
                    logger.error(f"Error fetching schedules for debug: {e}")
            
            logger.info(f"Sleeping for {POLL_INTERVAL} seconds...\n")
            time.sleep(POLL_INTERVAL)
        
        except KeyboardInterrupt:
            logger.info("\n\nShutting down gracefully...")
            break
        
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            logger.info(f"Retrying in {POLL_INTERVAL} seconds...")
            time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()

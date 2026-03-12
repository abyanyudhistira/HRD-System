"""LinkedIn Profile Scraper with Scoring Integration - Refactored with Helper Modules"""
import json
import glob
import os
import sys
import threading
import time
import pika
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from crawler import LinkedInCrawler
from helper.rabbitmq_helper import RabbitMQManager, ack_message, nack_message
from helper.supabase_helper import SupabaseManager

# Import pools
from browser_pool import get_browser_pool, cleanup_browser_pool
sys.path.append(str(Path(__file__).parent.parent / "api" / "helper"))
from connection_pool import get_connection_pool, get_pooled_supabase_manager, cleanup_connection_pool

# Add API helper to path for shared utilities (with fallback)
sys.path.append(str(Path(__file__).parent.parent / "api" / "helper"))

# Try to import from common_utils, fallback to local implementation
try:
    from common_utils import get_profile_hash, StatsManager, ProfileValidator, WebhookChecker
    print("✓ Using shared common_utils")
except ImportError:
    print("⚠ common_utils not found, using local implementation")
    
    # Local fallback implementations
    import hashlib
    import threading
    
    def get_profile_hash(profile_url):
        """Generate unique hash from profile URL"""
        return hashlib.md5(profile_url.encode()).hexdigest()[:8]
    
    class StatsManager:
        def __init__(self, stats_config=None):
            default_stats = {
                'processing': 0, 'completed': 0, 'failed': 0, 'skipped': 0,
                'sent_to_scoring': 0, 'saved_to_supabase': 0, 'supabase_failed': 0,
                'lock': threading.Lock()
            }
            if stats_config:
                default_stats.update(stats_config)
            self.stats = default_stats
        
        def increment(self, key):
            with self.stats['lock']:
                if key in self.stats:
                    self.stats[key] += 1
        
        def decrement(self, key):
            with self.stats['lock']:
                if key in self.stats:
                    self.stats[key] -= 1
        
        def get_stats(self):
            with self.stats['lock']:
                return {k: v for k, v in self.stats.items() if k != 'lock'}
        
        def print_stats(self, title="STATISTICS"):
            stats_copy = self.get_stats()
            print(f"\n{'='*60}\n{title}\n{'='*60}")
            for key, value in stats_copy.items():
                print(f"{key.replace('_', ' ').title()}: {value}")
            if stats_copy.get('completed', 0) + stats_copy.get('failed', 0) > 0:
                success_rate = stats_copy['completed'] / (stats_copy['completed'] + stats_copy['failed']) * 100
                print(f"Success Rate: {success_rate:.1f}%")
            print("="*60)
    
    class ProfileValidator:
        @staticmethod
        def validate_message(message):
            if not message:
                return False, "Empty message"
            if not message.get('url'):
                return False, "No URL in message"
            if not message.get('template_id'):
                return False, "No template_id in message"
            return True, "Valid"
        
        @staticmethod
        def should_skip_processing(existing_lead):
            if not existing_lead:
                return False, "No existing data"
            
            connection_status = existing_lead.get('connection_status', '')
            profile_data = existing_lead.get('profile_data')
            scoring_data = existing_lead.get('scoring_data')
            score = existing_lead.get('score', 0)
            
            has_profile = profile_data and profile_data not in [None, '', '{}', {}]
            has_scoring = scoring_data and scoring_data not in [None, '', '{}', {}]
            
            if connection_status == 'pending':
                return False, "Status: pending"
            elif connection_status == 'scraped':
                if not has_profile or not has_scoring:
                    missing = []
                    if not has_profile:
                        missing.append("profile_data")
                    if not has_scoring:
                        missing.append("scoring_data")
                    return False, f"Missing: {', '.join(missing)}"
                elif score == 0 and has_scoring:
                    return True, "Score: 0% but valid (candidate not suitable)"
                elif score > 0 and has_profile and has_scoring:
                    return True, f"Complete (Score: {score}%)"
            
            if not has_profile or not has_scoring:
                missing = []
                if not has_profile:
                    missing.append("profile_data")
                if not has_scoring:
                    missing.append("scoring_data")
                return False, f"Status: {connection_status}, missing: {', '.join(missing)}"
            
            return False, f"Status: {connection_status}"
    
    class WebhookChecker:
        @staticmethod
        def check_and_send_webhook(supabase_client, template_id, worker_id=""):
            try:
                schedule_result = supabase_client.table('crawler_schedules').select('id').eq('template_id', template_id).execute()
                
                if schedule_result.data:
                    schedule_id = schedule_result.data[0]['id']
                    print(f"[{worker_id}] 🔔 Checking webhook for schedule {schedule_id}...")
                    
                    try:
                        from webhook_helper import send_completion_webhook
                        webhook_sent = send_completion_webhook(supabase_client, schedule_id)
                        if webhook_sent:
                            print(f"[{worker_id}] ✅ Webhook notification sent")
                        return webhook_sent
                    except ImportError:
                        print(f"[{worker_id}] ⚠ Webhook helper not available")
                        return False
                
            except Exception as webhook_error:
                print(f"[{worker_id}] ⚠ Webhook check failed: {webhook_error}")
                return False

try:
    from query_optimizer import QueryOptimizer
    QUERY_OPTIMIZER_AVAILABLE = True
except ImportError:
    print("⚠ Query optimizer not available, using standard queries")
    QUERY_OPTIMIZER_AVAILABLE = False

load_dotenv()

# Configuration
SCORING_QUEUE = os.getenv('SCORING_QUEUE', 'scoring_queue')
REQUIREMENTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'scoring', 'requirements')
DB_CHECK_INTERVAL = int(os.getenv('DB_CHECK_INTERVAL', '60'))  # 1 minute default

# Statistics manager with crawler-specific stats
stats_manager = StatsManager({
    'sent_to_scoring': 0,
    'saved_to_supabase': 0,
    'supabase_failed': 0
})


def check_if_already_crawled(profile_url, output_dir='data/output'):
    """Check if profile URL has already been crawled"""
    if not os.path.exists(output_dir):
        return False, None
    
    url_hash = get_profile_hash(profile_url)
    pattern = os.path.join(output_dir, f"*_{url_hash}.json")
    existing_files = glob.glob(pattern)
    
    if existing_files:
        return True, existing_files[0]
    
    all_files = glob.glob(os.path.join(output_dir, "*.json"))
    for filepath in all_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('profile_url') == profile_url:
                    return True, filepath
        except:
            continue
    
    return False, None


def save_profile_data(profile_data, output_dir='data/output'):
    """Save profile data to JSON file (with duplicate prevention)"""
    os.makedirs(output_dir, exist_ok=True)
    
    profile_url = profile_data.get('profile_url', '')
    
    if profile_url:
        already_exists, existing_file = check_if_already_crawled(profile_url, output_dir)
        if already_exists:
            print(f"\n⚠ Profile already exists: {existing_file}")
            print(f"  Skipping save to avoid duplication")
            return existing_file
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = profile_data.get('name', 'unknown')
    if not name or name == 'N/A' or len(name.strip()) == 0:
        name = 'unknown'
    
    name_slug = name.replace(' ', '_').replace('/', '_').replace('\\', '_').lower()
    name_slug = ''.join(c for c in name_slug if c.isalnum() or c in ('_', '-'))
    
    url_hash = get_profile_hash(profile_url) if profile_url else 'nohash'
    filename = f"{name_slug}_{timestamp}_{url_hash}.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(profile_data, indent=2, ensure_ascii=False, fp=f)
    
    print(f"\n✓ Profile data saved to: {filepath}")
    return filepath


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


# ============================================================================
# TEMPLATE-BASED QUEUE MANAGEMENT FUNCTIONS (DEPRECATED - UI handles queueing)
# ============================================================================
# These functions are kept for reference but no longer used in main flow
# Messages are now published directly from UI instead of template selection

def check_template_has_requirements(template_id):
    """Check if template has requirements file"""
    if not template_id:
        return False
    
    # Method 1: Check if requirements file exists by template_id
    requirements_file = os.path.join(REQUIREMENTS_DIR, f"{template_id}.json")
    if os.path.exists(requirements_file):
        return True
    
    # Method 2: Check common template names
    common_templates = ['desk_collection', 'backend_dev_senior', 'frontend_dev', 'fullstack_dev', 'data_scientist', 'devops_engineer']
    for template_name in common_templates:
        requirements_file = os.path.join(REQUIREMENTS_DIR, f"{template_name}.json")
        if os.path.exists(requirements_file):
            return True
    
    # Method 3: Try to get template name from database (with error handling)
    try:
        supabase = SupabaseManager()
        template = supabase.get_template_by_id(template_id)
        if template and template.get('name'):
            template_name = template['name'].lower().replace(' ', '_')
            requirements_file = os.path.join(REQUIREMENTS_DIR, f"{template_name}.json")
            return os.path.exists(requirements_file)
    except Exception as e:
        print(f"⚠ Warning: Could not check template in database: {e}")
        # Continue with file-based check only
    
    return False


def select_template_interactive():
    """Interactive template selection for crawler"""
    try:
        supabase = SupabaseManager()
        templates = supabase.get_all_templates()
        
        if not templates:
            print("❌ No templates found in database")
            return None
        
        print("\n" + "="*60)
        print("📋 TEMPLATE SELECTION")
        print("="*60)
        print("Available templates:")
        
        for i, template in enumerate(templates, 1):
            print(f"  {i}. {template['name']} (ID: {template['id']})")
        
        print(f"  0. Exit")
        print("="*60)
        
        while True:
            try:
                choice = input("\nSelect template number: ").strip()
                
                if choice == '0':
                    print("Exiting...")
                    return None
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(templates):
                    selected_template = templates[choice_num - 1]
                    print(f"\n✓ Selected: {selected_template['name']}")
                    return selected_template['id']
                else:
                    print(f"❌ Invalid choice. Please select 1-{len(templates)} or 0 to exit")
            
            except ValueError:
                print("❌ Please enter a valid number")
            except KeyboardInterrupt:
                print("\n\nExiting...")
                return None
    
    except Exception as e:
        print(f"❌ Error selecting template: {e}")
        return None


def queue_leads_by_template(template_id, mq_config):
    """Queue leads that need processing for specific template_id"""
    try:
        print(f"\n🔍 Analyzing leads for template: {template_id}")
        
        supabase = SupabaseManager()
        leads = supabase.get_leads_by_template_id(template_id)
        
        if not leads:
            print(f"❌ No leads found for template: {template_id}")
            return 0
        
        # Filter leads that need processing
        needs_processing = [lead for lead in leads if lead['needs_processing']]
        already_complete = [lead for lead in leads if not lead['needs_processing']]
        
        print(f"\n📊 Lead Analysis Results:")
        print(f"   Total leads: {len(leads)}")
        print(f"   Need processing: {len(needs_processing)}")
        print(f"   Already complete: {len(already_complete)}")
        
        if already_complete:
            print(f"\n✅ Complete leads (will be skipped):")
            for lead in already_complete[:5]:  # Show first 5
                print(f"   - {lead['name']} (Score: {lead['score_percentage']}%)")
            if len(already_complete) > 5:
                print(f"   ... and {len(already_complete) - 5} more")
        
        if not needs_processing:
            print(f"\n🎉 All leads for this template are already complete!")
            return 0
        
        print(f"\n📤 Queueing {len(needs_processing)} leads that need processing:")
        
        # Connect to RabbitMQ
        mq = RabbitMQManager()
        mq.host = mq_config['host']
        mq.port = mq_config['port']
        mq.username = mq_config['username']
        mq.password = mq_config['password']
        mq.queue_name = mq_config['queue_name']
        
        if not mq.connect():
            print("❌ Failed to connect to RabbitMQ for queueing")
            return 0
        
        queued_count = 0
        
        try:
            for lead in needs_processing:
                message = {
                    'url': lead['profile_url'],
                    'template_id': template_id,
                    'timestamp': datetime.now().isoformat(),
                    'trigger': 'template_selection',
                    'lead_id': lead['id'],
                    'reason': ', '.join(lead['status_reason'])
                }
                
                try:
                    mq.channel.basic_publish(
                        exchange='',
                        routing_key=mq.queue_name,
                        body=json.dumps(message),
                        properties=pika.BasicProperties(
                            delivery_mode=2,  # Persistent
                            content_type='application/json'
                        )
                    )
                    queued_count += 1
                    print(f"   ✓ Queued: {lead['name']} ({', '.join(lead['status_reason'])})")
                    
                except Exception as e:
                    print(f"   ❌ Failed to queue {lead['name']}: {e}")
            
            print(f"\n✅ Successfully queued {queued_count}/{len(needs_processing)} leads")
            
        finally:
            mq.close()
        
        return queued_count
    
    except Exception as e:
        print(f"❌ Error queueing leads by template: {e}")
        return 0


def send_to_scoring_queue(profile_data, template_id, mq_config):
    """Send profile data to scoring queue"""
    try:
        # Connect to RabbitMQ
        mq = RabbitMQManager()
        mq.host = mq_config['host']
        mq.port = mq_config['port']
        mq.username = mq_config['username']
        mq.password = mq_config['password']
        mq.queue_name = SCORING_QUEUE
        
        if not mq.connect():
            print(f"  ✗ Failed to connect to scoring queue")
            return False
        
        # Prepare message
        message = {
            'profile_data': profile_data,
            'template_id': template_id,  # Use template_id instead of requirements_id
            'profile_url': profile_data.get('profile_url', '')
        }
        
        # Publish to scoring queue
        mq.channel.queue_declare(queue=SCORING_QUEUE, durable=True)
        mq.channel.basic_publish(
            exchange='',
            routing_key=SCORING_QUEUE,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
            )
        )
        
        mq.close()
        print(f"  📤 Sent to scoring queue: {SCORING_QUEUE}")
        return True
    
    except Exception as e:
        print(f"  ✗ Failed to send to scoring queue: {e}")
        return False





def process_profile_message(worker_id, message, supabase, mq_config):
    """Process a single profile scraping message using browser pool"""
    browser_info = None
    
    try:
        # Validate message
        is_valid, validation_msg = ProfileValidator.validate_message(message)
        if not is_valid:
            print(f"[Worker {worker_id}] ✗ Invalid message: {validation_msg}")
            return False
        
        url = message.get('url')
        template_id = message.get('template_id')
        
        print(f"\n[Worker {worker_id}] 📥 Processing: {url}")
        print(f"[Worker {worker_id}] 📁 Template ID: {template_id}")
        
        stats_manager.increment('processing')
        
        # Check if already scraped in Supabase - OPTIMIZED
        if supabase:
            existing_lead = get_existing_lead_optimized(supabase, url)
            
            if existing_lead:
                should_skip, reason = ProfileValidator.should_skip_processing(existing_lead)
                
                if should_skip:
                    print(f"[Worker {worker_id}] ⊘ {reason}")
                    stats_manager.increment('skipped')
                    return True
                else:
                    print(f"[Worker {worker_id}] 🔄 Re-processing ({reason})")
        
        # Get browser from pool
        browser_pool = get_browser_pool()
        browser_info = browser_pool.get_browser(timeout=30)
        
        if not browser_info:
            print(f"[Worker {worker_id}] ✗ No browser available")
            return False
        
        print(f"[Worker {worker_id}] 🚗 Using pooled browser (usage: {browser_info['usage_count']})")
        
        # Scrape profile using pooled browser
        crawler = browser_info['crawler']
        profile_data = crawler.get_profile(url)
        profile_data['template_id'] = template_id
        
        # Update Supabase using pooled connection
        if supabase:
            update_supabase_result(worker_id, supabase, url, profile_data, template_id)
        
        # Send to scoring queue
        print(f"[Worker {worker_id}] 📤 Sending to scoring...")
        if send_to_scoring_queue(profile_data, template_id, mq_config):
            stats_manager.increment('sent_to_scoring')
        
        stats_manager.increment('completed')
        print(f"[Worker {worker_id}] ✓ Completed: {profile_data.get('name', 'Unknown')}")
        
        # Print stats after completion
        stats_manager.print_stats()
        
        return True
        
    except Exception as e:
        stats_manager.increment('failed')
        print(f"[Worker {worker_id}] ✗ Error: {e}")
        stats_manager.print_stats()
        return False
    
    finally:
        # Return browser to pool
        if browser_info:
            browser_pool = get_browser_pool()
            browser_pool.return_browser(browser_info)
            print(f"[Worker {worker_id}] 🔄 Browser returned to pool")
        
        stats_manager.decrement('processing')


def get_existing_lead_optimized(supabase, url):
    """Get existing lead with query optimization if available"""
    if QUERY_OPTIMIZER_AVAILABLE and hasattr(supabase, 'client'):
        try:
            optimizer = QueryOptimizer(supabase.client)
            return optimizer.check_lead_exists_optimized(url)
        except:
            # Fallback to standard query
            return supabase.get_lead_by_url(url)
    else:
        return supabase.get_lead_by_url(url)


def update_supabase_result(worker_id, supabase, url, profile_data, template_id):
    """Update Supabase with scraped data and handle webhook using pooled connection"""
    print(f"[Worker {worker_id}] 💾 Updating Supabase (using connection pool)...")
    
    if supabase.update_lead_after_scrape(profile_url=url, profile_data=profile_data):
        stats_manager.increment('saved_to_supabase')
        print(f"[Worker {worker_id}] ✓ Updated Supabase")
        
        # Check webhook completion using pooled connection
        def webhook_operation(client):
            WebhookChecker.check_and_send_webhook(client, template_id, worker_id)
        
        try:
            connection_pool = get_connection_pool()
            client = connection_pool.get_connection()
            webhook_operation(client)
            connection_pool.return_connection(client)
        except Exception as webhook_error:
            print(f"[Worker {worker_id}] ⚠ Webhook check failed: {webhook_error}")
    else:
        stats_manager.increment('supabase_failed')
        print(f"[Worker {worker_id}] ⚠ Failed to update Supabase")
def worker_thread(worker_id, mq_config):
    """Worker thread that continuously processes messages"""
    print(f"[Worker {worker_id}] Started")
    
    # Setup RabbitMQ connection
    mq = setup_worker_rabbitmq(worker_id, mq_config)
    if not mq:
        return
    
    # Setup Supabase connection
    supabase = setup_worker_supabase(worker_id)
    
    # Set QoS - only process 1 message at a time
    mq.channel.basic_qos(prefetch_count=1)
    
    def callback(ch, method, properties, body):
        """Process each message"""
        try:
            # Parse message
            message = json.loads(body)
            
            # Process the message
            success = process_profile_message(worker_id, message, supabase, mq_config)
            
            # Acknowledge or reject message
            if success:
                ack_message(ch, method.delivery_tag)
            else:
                nack_message(ch, method.delivery_tag, requeue=False)
        
        except Exception as e:
            print(f"[Worker {worker_id}] ✗ Fatal error: {e}")
            nack_message(ch, method.delivery_tag, requeue=False)
    
    try:
        # Start consuming
        mq.channel.basic_consume(
            queue=mq.queue_name,
            on_message_callback=callback,
            auto_ack=False
        )
        
        print(f"[Worker {worker_id}] Waiting for messages...")
        mq.channel.start_consuming()
    
    except Exception as e:
        print(f"[Worker {worker_id}] Error: {e}")
    
    finally:
        mq.close()
        print(f"[Worker {worker_id}] Stopped")


def setup_worker_rabbitmq(worker_id, mq_config):
    """Setup RabbitMQ connection for worker"""
    mq = RabbitMQManager()
    mq.host = mq_config['host']
    mq.port = mq_config['port']
    mq.username = mq_config['username']
    mq.password = mq_config['password']
    mq.queue_name = mq_config['queue_name']
    
    if not mq.connect():
        print(f"[Worker {worker_id}] Failed to connect to RabbitMQ")
        return None
    
    return mq


def setup_worker_supabase(worker_id):
    """Setup Supabase connection for worker using connection pool"""
    try:
        # Use pooled Supabase manager
        supabase = get_pooled_supabase_manager()
        print(f"[Worker {worker_id}] ✓ Connected to Supabase (using connection pool)")
        return supabase
    except Exception as e:
        print(f"[Worker {worker_id}] ⚠ Supabase connection failed: {e}")
        print(f"[Worker {worker_id}]   Continuing without Supabase (data won't be saved to DB)")
        return None


def main():
    print("="*60)
    print("LINKEDIN CRAWLER CONSUMER - OPTIMIZED WITH POOLS")
    print("="*60)
    print("Using Browser Pool + Connection Pool for better performance")
    print("="*60)
    
    # Initialize pools first
    print("\n🚀 Initializing Performance Pools...")
    try:
        browser_pool = get_browser_pool()
        connection_pool = get_connection_pool()
        
        # Print pool stats
        browser_stats = browser_pool.get_pool_stats()
        conn_stats = connection_pool.get_pool_stats()
        
        print(f"✅ Browser Pool: {browser_stats['available']}/{browser_stats['pool_size']} ready")
        print(f"✅ Connection Pool: {conn_stats['available']}/{conn_stats['pool_size']} ready")
        
    except Exception as e:
        print(f"❌ Failed to initialize pools: {e}")
        return
    
    # Number of concurrent workers (default 3)
    num_workers = int(os.getenv('NUM_WORKERS', '3'))
    print(f"\n🚀 Concurrent Workers: {num_workers}")
    print(f"   Each worker uses shared browser and connection pools")
    print(f"   Expected capacity: ~{num_workers * 200} profiles/hour (with pools)")
    
    # Connect to RabbitMQ
    print("\n→ Connecting to LavinMQ...")
    mq = RabbitMQManager()
    if not mq.connect():
        print("✗ Failed to connect to LavinMQ")
        cleanup_pools()
        return
    
    print(f"✓ Connected to LavinMQ: {mq.host}")
    
    # Save config for workers
    mq_config = {
        'host': mq.host,
        'port': mq.port,
        'username': mq.username,
        'password': mq.password,
        'queue_name': mq.queue_name
    }
    
    # Check current queue size
    queue_size = mq.get_queue_size()
    print(f"\n→ Current queue status:")
    print(f"  - Queue: {mq.queue_name}")
    print(f"  - Messages waiting: {queue_size}")
    print(f"  - Scoring queue: {SCORING_QUEUE}")
    
    mq.close()
    
    if queue_size == 0:
        print("\n⚠ Queue is empty. Waiting for messages from UI...")
        print("  Workers will start processing once messages are published from UI")
    
    print(f"\n→ Starting {num_workers} optimized crawler workers...")
    print("  Workers will:")
    print("  1. Use shared browser pool (faster, less memory)")
    print("  2. Use connection pool (faster DB operations)")
    print("  3. Scrape LinkedIn profiles efficiently")
    print("  4. Update Supabase and send to scoring")
    print("\n  Press Ctrl+C to stop")
    print(f"  LavinMQ Dashboard: https://leopard.lmq.cloudamqp.com")
    
    # Start worker threads with staggered startup
    threads = []
    print(f"\n🔄 Initializing workers...")
    for i in range(num_workers):
        worker_id = i + 1
        print(f"   Starting Worker {worker_id}...")
        t = threading.Thread(
            target=worker_thread, 
            args=(worker_id, mq_config), 
            daemon=True,
            name=f"CrawlerWorker-{worker_id}"
        )
        t.start()
        threads.append(t)
        time.sleep(1)  # Stagger startup to avoid race conditions
    
    print(f"\n✅ All {num_workers} workers are running with optimized pools!")
    print(f"   Memory usage: ~{browser_stats['pool_size'] * 400}MB (shared browsers)")
    print(f"   Processing capacity: {num_workers}x workers sharing {browser_stats['pool_size']} browsers")
    print("\n💡 Optimizations active:")
    print("  1. Browser Pool → Reuse logged-in browsers")
    print("  2. Connection Pool → Reuse database connections")
    print("  3. Concurrent Workers → Parallel processing")
    print("  4. Smart Queueing → Efficient message handling")
    
    try:
        # Keep main thread alive and monitor progress
        last_stats_time = time.time()
        
        while True:
            time.sleep(10)  # Check every 10 seconds
            
            # Print stats periodically
            current_time = time.time()
            if current_time - last_stats_time >= 30:  # Every 30 seconds
                stats_manager.print_stats()
                
                # Print pool stats
                browser_stats = browser_pool.get_pool_stats()
                conn_stats = connection_pool.get_pool_stats()
                print(f"🚗 Browser Pool: {browser_stats['available']}/{browser_stats['pool_size']} available, {browser_stats['busy']} busy")
                print(f"🏊 Connection Pool: {conn_stats['available']}/{conn_stats['pool_size']} available, {conn_stats['busy']} busy")
                
                last_stats_time = current_time
                
                # Check if all work is done
                current_stats = stats_manager.get_stats()
                if current_stats['processing'] == 0:
                    # Check queue size
                    mq_temp = RabbitMQManager()
                    mq_temp.host = mq_config['host']
                    mq_temp.port = mq_config['port']
                    mq_temp.username = mq_config['username']
                    mq_temp.password = mq_config['password']
                    mq_temp.queue_name = mq_config['queue_name']
                    
                    if mq_temp.connect():
                        remaining_queue = mq_temp.get_queue_size()
                        mq_temp.close()
                        
                        if remaining_queue == 0:
                            print(f"\n🎉 All work completed!")
                            print(f"   Queue is empty and no workers are processing")
                            break
    
    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted by user. Stopping all workers...")
        print("  (Workers will finish current tasks)")
    
    finally:
        # Cleanup pools
        cleanup_pools()
        
        # Wait a bit for workers to finish current tasks
        time.sleep(3)
        
        # Final stats
        print("\n" + "="*60)
        print("FINAL RESULTS")
        print("="*60)
        current_stats = stats_manager.get_stats()
        print(f"✓ Completed: {current_stats['completed']}")
        print(f"✗ Failed: {current_stats['failed']}")
        print(f"⊘ Skipped: {current_stats['skipped']}")
        print(f"📤 Sent to Scoring: {current_stats['sent_to_scoring']}")
        print(f"💾 Updated Supabase: {current_stats['saved_to_supabase']}")
        print(f"⚠ Supabase Failed: {current_stats['supabase_failed']}")
        if current_stats['completed'] + current_stats['failed'] > 0:
            success_rate = current_stats['completed'] / (current_stats['completed'] + current_stats['failed']) * 100
            print(f"📊 Success Rate: {success_rate:.1f}%")
        print("="*60)
        print(f"\nOptimized crawler with pools completed!")


def cleanup_pools():
    """Cleanup all pools"""
    print("\n🧹 Cleaning up performance pools...")
    try:
        cleanup_browser_pool()
        cleanup_connection_pool()
        print("✓ All pools cleaned up")
    except Exception as e:
        print(f"⚠ Error during cleanup: {e}")


if __name__ == "__main__":
    main()

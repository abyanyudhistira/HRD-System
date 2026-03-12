"""
Common utilities shared across all backend services
"""
import hashlib
import threading
import pika
import os
from dotenv import load_dotenv

load_dotenv()


def get_profile_hash(profile_url):
    """Generate unique hash from profile URL"""
    return hashlib.md5(profile_url.encode()).hexdigest()[:8]


class StatsManager:
    """Thread-safe statistics manager"""
    
    def __init__(self, stats_config=None):
        """Initialize with custom stats configuration"""
        default_stats = {
            'processing': 0,
            'completed': 0,
            'failed': 0,
            'skipped': 0,
            'lock': threading.Lock()
        }
        
        if stats_config:
            default_stats.update(stats_config)
        
        self.stats = default_stats
    
    def increment(self, key):
        """Thread-safe increment"""
        with self.stats['lock']:
            if key in self.stats:
                self.stats[key] += 1
    
    def decrement(self, key):
        """Thread-safe decrement"""
        with self.stats['lock']:
            if key in self.stats:
                self.stats[key] -= 1
    
    def get_stats(self):
        """Get current stats copy"""
        with self.stats['lock']:
            return {k: v for k, v in self.stats.items() if k != 'lock'}
    
    def print_stats(self, title="STATISTICS"):
        """Print current statistics"""
        stats_copy = self.get_stats()
        print("\n" + "="*60)
        print(title)
        print("="*60)
        
        for key, value in stats_copy.items():
            print(f"{key.replace('_', ' ').title()}: {value}")
        
        if stats_copy.get('completed', 0) + stats_copy.get('failed', 0) > 0:
            success_rate = stats_copy['completed'] / (stats_copy['completed'] + stats_copy['failed']) * 100
            print(f"Success Rate: {success_rate:.1f}%")
        print("="*60)


class ProfileValidator:
    """Validate profile processing requirements"""
    
    @staticmethod
    def validate_message(message):
        """Validate incoming message structure"""
        if not message:
            return False, "Empty message"
        
        url = message.get('url')
        template_id = message.get('template_id')
        
        if not url:
            return False, "No URL in message"
        
        if not template_id:
            return False, "No template_id in message"
        
        return True, "Valid"
    
    @staticmethod
    def should_skip_processing(existing_lead):
        """Determine if profile should be skipped based on existing data"""
        if not existing_lead:
            return False, "No existing data"
        
        connection_status = existing_lead.get('connection_status', '')
        profile_data = existing_lead.get('profile_data')
        scoring_data = existing_lead.get('scoring_data')
        score = existing_lead.get('score', 0)
        
        # Check if data exists
        has_profile = profile_data and profile_data not in [None, '', '{}', {}]
        has_scoring = scoring_data and scoring_data not in [None, '', '{}', {}]
        
        # RULE 1: If status is pending, always process
        if connection_status == 'pending':
            return False, "Status: pending"
        
        # RULE 2: If status is scraped, check data completeness
        elif connection_status == 'scraped':
            if not has_profile or not has_scoring:
                missing = []
                if not has_profile:
                    missing.append("profile_data")
                if not has_scoring:
                    missing.append("scoring_data")
                return False, f"Missing: {', '.join(missing)}"
            
            # If score is 0 but has scoring data = valid result
            elif score == 0 and has_scoring:
                return True, "Score: 0% but valid (candidate not suitable)"
            
            # If score > 0 and all data exists = complete
            elif score > 0 and has_profile and has_scoring:
                return True, f"Complete (Score: {score}%)"
        
        # Other cases - check data completeness
        if not has_profile or not has_scoring:
            missing = []
            if not has_profile:
                missing.append("profile_data")
            if not has_scoring:
                missing.append("scoring_data")
            return False, f"Status: {connection_status}, missing: {', '.join(missing)}"
        
        return False, f"Status: {connection_status}"


def create_rabbitmq_connection():
    """Create standardized RabbitMQ connection"""
    RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
    RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
    RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'guest')
    RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASS', 'guest')
    RABBITMQ_VHOST = os.getenv('RABBITMQ_VHOST', '/')
    
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        virtual_host=RABBITMQ_VHOST,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )
    return pika.BlockingConnection(parameters)


def create_rabbitmq_channel(queue_name, durable=True):
    """Create RabbitMQ channel with queue declaration"""
    connection = create_rabbitmq_connection()
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=durable)
    return connection, channel


class WebhookChecker:
    """Handle webhook completion checking"""
    
    @staticmethod
    def check_and_send_webhook(supabase_client, template_id, worker_id=""):
        """Check if schedule is completed and send webhook if needed"""
        try:
            # Get schedule_id from template
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
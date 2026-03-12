"""
RabbitMQ Helper for API
Centralized queue management
"""
import os
import json
import pika
from datetime import datetime
from typing import Dict, Optional

# LavinMQ Configuration
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', '5672'))
RABBITMQ_USER = os.getenv('RABBITMQ_USER')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS')
RABBITMQ_VHOST = os.getenv('RABBITMQ_VHOST')
RABBITMQ_QUEUE = os.getenv('RABBITMQ_QUEUE')
OUTREACH_QUEUE = os.getenv('OUTREACH_QUEUE')


class QueuePublisher:
    """Simplified queue publisher for LavinMQ"""
    
    def __init__(self):
        self.credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        
        # SSL/TLS support for port 5671
        if RABBITMQ_PORT == 5671:
            import ssl
            ssl_options = pika.SSLOptions(ssl.create_default_context())
            self.parameters = pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                virtual_host=RABBITMQ_VHOST,
                credentials=self.credentials,
                ssl_options=ssl_options,
                heartbeat=600,
                blocked_connection_timeout=300
            )
        else:
            self.parameters = pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                virtual_host=RABBITMQ_VHOST,
                credentials=self.credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
    
    def publish(self, queue_name: str, message: Dict) -> bool:
        """Publish message to queue"""
        print(f"🔄 Attempting to publish to queue: {queue_name}")
        print(f"   Host: {RABBITMQ_HOST}")
        print(f"   User: {RABBITMQ_USER}")
        print(f"   VHost: {RABBITMQ_VHOST}")
        
        if not queue_name:
            print(f"❌ Queue name is None or empty")
            return False
            
        if not RABBITMQ_HOST or not RABBITMQ_USER or not RABBITMQ_PASS:
            print(f"❌ Missing RabbitMQ credentials:")
            print(f"   RABBITMQ_HOST: {RABBITMQ_HOST}")
            print(f"   RABBITMQ_USER: {RABBITMQ_USER}")
            print(f"   RABBITMQ_PASS: {'***' if RABBITMQ_PASS else 'None'}")
            return False
        
        try:
            print(f"🔌 Connecting to LavinMQ...")
            connection = pika.BlockingConnection(self.parameters)
            channel = connection.channel()
            
            print(f"📋 Declaring queue: {queue_name}")
            # Declare queue
            channel.queue_declare(queue=queue_name, durable=True)
            
            print(f"📤 Publishing message...")
            # Publish message
            channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent
                    content_type='application/json'
                )
            )
            
            connection.close()
            print(f"✅ Message published successfully to {queue_name}")
            return True
            
        except Exception as e:
            print(f"❌ Queue publish failed: {e}")
            print(f"   Queue: {queue_name}")
            print(f"   Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return False
    
    def publish_crawler_job(self, profile_url: str, template_id: Optional[str] = None) -> bool:
        """Publish crawler job to queue"""
        message = {
            'url': profile_url,
            'template_id': template_id,
            'timestamp': datetime.now().isoformat(),
            'trigger': 'api'
        }
        return self.publish(RABBITMQ_QUEUE, message)
    
    def publish_outreach_job(self, lead: Dict, message_text: str, dry_run: bool = True, batch_id: str = None) -> bool:
        """Publish outreach job to queue"""
        print(f"🎯 publish_outreach_job called:")
        print(f"   OUTREACH_QUEUE env var: {OUTREACH_QUEUE}")
        print(f"   Lead: {lead.get('name')} - {lead.get('profile_url')}")
        print(f"   Dry run: {dry_run}")
        
        if not OUTREACH_QUEUE:
            print(f"❌ OUTREACH_QUEUE not configured in environment variables")
            print(f"   Current value: {OUTREACH_QUEUE}")
            return False
            
        message = {
            'job_id': f"outreach_{batch_id}_{lead.get('id', 'unknown')}",
            'lead_id': lead.get('id'),
            'name': lead.get('name'),
            'profile_url': lead.get('profile_url'),
            'message': message_text,
            'dry_run': dry_run,
            'batch_id': batch_id,
            'created_at': datetime.now().isoformat()
        }
        
        print(f"📤 Publishing to queue: {OUTREACH_QUEUE}")
        print(f"   Message keys: {list(message.keys())}")
        
        result = self.publish(OUTREACH_QUEUE, message)
        print(f"📊 Publish result: {result}")
        return result
    
    def get_queue_info(self, queue_name: str = None) -> Optional[Dict]:
        """Get queue information (message count, etc.)"""
        if not queue_name:
            queue_name = RABBITMQ_QUEUE
        
        try:
            connection = pika.BlockingConnection(self.parameters)
            channel = connection.channel()
            
            # Passive declare to get queue info without creating it
            method = channel.queue_declare(queue=queue_name, passive=True)
            
            info = {
                'queue': queue_name,
                'messages': method.method.message_count,
                'consumers': method.method.consumer_count
            }
            
            connection.close()
            return info
            
        except Exception as e:
            print(f"❌ Failed to get queue info: {e}")
            return None
    
    def purge_queue(self, queue_name: str = None) -> bool:
        """Purge (delete all messages) from queue"""
        if not queue_name:
            queue_name = RABBITMQ_QUEUE
        
        try:
            connection = pika.BlockingConnection(self.parameters)
            channel = connection.channel()
            
            # Purge the queue
            method = channel.queue_purge(queue=queue_name)
            purged_count = method.method.message_count
            
            connection.close()
            print(f"✅ Purged {purged_count} messages from queue: {queue_name}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to purge queue: {e}")
            return False


# Global instance
queue_publisher = QueuePublisher()

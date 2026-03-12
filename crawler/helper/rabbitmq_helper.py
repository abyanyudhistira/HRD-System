"""RabbitMQ helper for queue management"""
import pika
import json
import os
from dotenv import load_dotenv

load_dotenv()


class RabbitMQManager:
    def __init__(self):
        """Initialize RabbitMQ connection"""
        self.host = os.getenv('RABBITMQ_HOST', 'localhost')
        self.port = int(os.getenv('RABBITMQ_PORT', '5672'))
        self.username = os.getenv('RABBITMQ_USER', 'guest')
        self.password = os.getenv('RABBITMQ_PASS', 'guest')
        self.vhost = os.getenv('RABBITMQ_VHOST', '/')
        self.queue_name = os.getenv('RABBITMQ_QUEUE', 'linkedin_profiles')
        
        self.connection = None
        self.channel = None
    
    def connect(self):
        """Connect to RabbitMQ"""
        try:
            credentials = pika.PlainCredentials(self.username, self.password)
            
            # Check if SSL is needed (port 5671 = SSL)
            use_ssl = self.port == 5671
            
            if use_ssl:
                import ssl
                ssl_options = pika.SSLOptions(ssl.create_default_context())
                parameters = pika.ConnectionParameters(
                    host=self.host,
                    port=self.port,
                    virtual_host=self.vhost,
                    credentials=credentials,
                    ssl_options=ssl_options,
                    heartbeat=600,
                    blocked_connection_timeout=300
                )
            else:
                parameters = pika.ConnectionParameters(
                    host=self.host,
                    port=self.port,
                    virtual_host=self.vhost,
                    credentials=credentials,
                    heartbeat=600,
                    blocked_connection_timeout=300
                )
            
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            self.channel.queue_declare(queue=self.queue_name, durable=True)
            
            print(f"✓ Connected to RabbitMQ at {self.host}:{self.port} (SSL: {use_ssl})")
            return True
        except Exception as e:
            print(f"✗ Failed to connect to RabbitMQ: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def publish_url(self, url):
        """Publish a LinkedIn profile URL to queue"""
        try:
            message = json.dumps({'url': url})
            
            self.channel.basic_publish(
                exchange='',
                routing_key=self.queue_name,
                body=message,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                )
            )
            return True
        except Exception as e:
            print(f"✗ Failed to publish URL: {e}")
            return False
    
    def publish_urls(self, urls):
        """Publish multiple URLs to queue"""
        success_count = 0
        for url in urls:
            if self.publish_url(url):
                success_count += 1
        
        print(f"✓ Published {success_count}/{len(urls)} URLs to queue")
        return success_count
    
    def consume(self, callback, auto_ack=False):
        """Consume messages from queue"""
        try:
            self.channel.basic_qos(prefetch_count=1)
            
            self.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=callback,
                auto_ack=auto_ack
            )
            
            print(f"✓ Waiting for messages in queue '{self.queue_name}'...")
            print("  Press Ctrl+C to stop")
            
            self.channel.start_consuming()
        except KeyboardInterrupt:
            print("\n⚠ Interrupted by user")
            self.stop_consuming()
        except Exception as e:
            print(f"✗ Error consuming messages: {e}")
    
    def stop_consuming(self):
        """Stop consuming messages"""
        if self.channel:
            self.channel.stop_consuming()
    
    def get_queue_size(self):
        """Get number of messages in queue"""
        try:
            queue_state = self.channel.queue_declare(
                queue=self.queue_name,
                durable=True,
                passive=True
            )
            return queue_state.method.message_count
        except Exception as e:
            print(f"✗ Failed to get queue size: {e}")
            return 0
    
    def purge_queue(self):
        """Delete all messages from queue"""
        try:
            self.channel.queue_purge(queue=self.queue_name)
            print(f"✓ Purged queue '{self.queue_name}'")
            return True
        except Exception as e:
            print(f"✗ Failed to purge queue: {e}")
            return False
    
    def close(self):
        """Close connection"""
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
                print("✓ Closed RabbitMQ connection")
        except Exception as e:
            print(f"⚠ Error closing connection: {e}")


def ack_message(channel, delivery_tag):
    """Acknowledge a message (mark as processed)"""
    if channel.is_open:
        channel.basic_ack(delivery_tag)


def nack_message(channel, delivery_tag, requeue=True):
    """Negative acknowledge (reject) a message
    
    Args:
        requeue: If True, put message back in queue for retry
    """
    if channel.is_open:
        channel.basic_nack(delivery_tag, requeue=requeue)

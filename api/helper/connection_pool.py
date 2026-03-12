"""
Database Connection Pool - Manage reusable Supabase connections for better performance
"""
import threading
import time
import queue
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


class SupabaseConnectionPool:
    """Thread-safe connection pool for Supabase database connections"""
    
    def __init__(self, pool_size=None):
        # Get configuration from environment
        self.pool_size = pool_size or int(os.getenv('DB_POOL_SIZE', '5'))
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_KEY')
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment")
        
        self.available_connections = queue.Queue(maxsize=self.pool_size)
        self.busy_connections = set()
        self.lock = threading.Lock()
        self.created_count = 0
        self.max_connection_age = int(os.getenv('MAX_CONNECTION_AGE_MINUTES', '30'))  # 30 minutes
        
        print(f"🏊 Initializing Database Connection Pool (size: {self.pool_size})...")
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize connection pool with database connections"""
        for i in range(self.pool_size):
            try:
                print(f"   Creating connection {i+1}/{self.pool_size}...")
                connection_info = self._create_connection()
                self.available_connections.put(connection_info)
                print(f"   ✓ Connection {i+1} ready")
            except Exception as e:
                print(f"   ✗ Failed to create connection {i+1}: {e}")
        
        print(f"✅ Connection Pool initialized with {self.available_connections.qsize()} connections")
    
    def _create_connection(self):
        """Create a new database connection"""
        client = create_client(self.supabase_url, self.supabase_key)
        
        # Test connection
        try:
            # Simple test query
            result = client.table('leads_list').select('id').limit(1).execute()
            print(f"   Connection test successful")
        except Exception as e:
            print(f"   ⚠ Connection test failed: {e}")
            # Continue anyway, might work later
        
        connection_info = {
            'client': client,
            'created_at': time.time(),
            'usage_count': 0,
            'last_used': time.time()
        }
        
        with self.lock:
            self.created_count += 1
        
        return connection_info
    
    def get_connection(self, timeout=10):
        """Get an available connection from the pool"""
        try:
            # Try to get connection from pool
            connection_info = self.available_connections.get(timeout=timeout)
            
            with self.lock:
                self.busy_connections.add(connection_info)
            
            # Check if connection is too old
            age_minutes = (time.time() - connection_info['created_at']) / 60
            if age_minutes > self.max_connection_age:
                print(f"⚠ Connection too old ({age_minutes:.1f}min), refreshing...")
                self._refresh_connection(connection_info)
            
            connection_info['last_used'] = time.time()
            connection_info['usage_count'] += 1
            
            return connection_info['client']
            
        except queue.Empty:
            print("⚠ No connections available in pool, creating temporary connection...")
            temp_connection = self._create_connection()
            return temp_connection['client']
    
    def return_connection(self, client):
        """Return connection to the pool"""
        try:
            # Find the connection info for this client
            connection_info = None
            with self.lock:
                for conn_info in list(self.busy_connections):
                    if conn_info['client'] == client:
                        connection_info = conn_info
                        self.busy_connections.remove(conn_info)
                        break
            
            if connection_info:
                # Check connection health before returning
                if self._is_connection_healthy(connection_info):
                    self.available_connections.put_nowait(connection_info)
                else:
                    print("⚠ Connection unhealthy, creating replacement...")
                    self._replace_connection(connection_info)
            else:
                print("⚠ Connection not found in busy set, might be temporary connection")
                
        except queue.Full:
            # Pool is full, don't return this connection
            print("⚠ Pool full, discarding excess connection")
        except Exception as e:
            print(f"⚠ Error returning connection: {e}")
    
    def _is_connection_healthy(self, connection_info):
        """Check if connection is still healthy"""
        try:
            client = connection_info['client']
            # Simple health check - try a lightweight query
            result = client.table('leads_list').select('id').limit(1).execute()
            return True
        except Exception as e:
            print(f"Connection health check failed: {e}")
            return False
    
    def _refresh_connection(self, connection_info):
        """Refresh connection by creating new client"""
        try:
            # Create new client
            new_client = create_client(self.supabase_url, self.supabase_key)
            connection_info['client'] = new_client
            connection_info['created_at'] = time.time()
            connection_info['usage_count'] = 0
            print("✓ Connection refreshed successfully")
        except Exception as e:
            print(f"✗ Failed to refresh connection: {e}")
    
    def _replace_connection(self, old_connection_info):
        """Replace unhealthy connection with new one"""
        try:
            # Create new connection
            new_connection_info = self._create_connection()
            self.available_connections.put_nowait(new_connection_info)
            print("✓ Connection replaced successfully")
            
        except Exception as e:
            print(f"✗ Failed to replace connection: {e}")
    
    def get_pool_stats(self):
        """Get pool statistics"""
        with self.lock:
            return {
                'pool_size': self.pool_size,
                'available': self.available_connections.qsize(),
                'busy': len(self.busy_connections),
                'total_created': self.created_count
            }
    
    def cleanup(self):
        """Cleanup all connections in pool"""
        print("🧹 Cleaning up connection pool...")
        
        # Clear busy connections
        with self.lock:
            self.busy_connections.clear()
        
        # Clear available connections
        while not self.available_connections.empty():
            try:
                connection_info = self.available_connections.get_nowait()
                # Supabase connections don't need explicit closing
            except queue.Empty:
                break
        
        print("✓ Connection pool cleanup completed")


class PooledSupabaseManager:
    """Supabase manager that uses connection pool"""
    
    def __init__(self, connection_pool):
        self.pool = connection_pool
    
    def execute_with_pool(self, operation):
        """Execute database operation using pooled connection"""
        client = self.pool.get_connection()
        try:
            result = operation(client)
            return result
        finally:
            self.pool.return_connection(client)
    
    def update_lead_after_scrape(self, profile_url, profile_data):
        """Update lead after scraping using pooled connection"""
        def operation(client):
            result = client.table('leads_list').update({
                'profile_data': profile_data,
                'connection_status': 'scraped',
                'processed_at': time.time()
            }).eq('profile_url', profile_url).execute()
            return result.data is not None
        
        return self.execute_with_pool(operation)
    
    def get_lead_by_url(self, profile_url):
        """Get lead by URL using pooled connection"""
        def operation(client):
            result = client.table('leads_list').select('*').eq('profile_url', profile_url).execute()
            return result.data[0] if result.data else None
        
        return self.execute_with_pool(operation)
    
    def get_leads_by_template_id(self, template_id):
        """Get leads by template ID using pooled connection"""
        def operation(client):
            result = client.table('leads_list').select('*').eq('template_id', template_id).execute()
            return result.data
        
        return self.execute_with_pool(operation)


# Global connection pool instance
connection_pool = None

def get_connection_pool():
    """Get global connection pool instance"""
    global connection_pool
    if connection_pool is None:
        connection_pool = SupabaseConnectionPool()
    return connection_pool

def get_pooled_supabase_manager():
    """Get Supabase manager with connection pool"""
    pool = get_connection_pool()
    return PooledSupabaseManager(pool)

def cleanup_connection_pool():
    """Cleanup global connection pool"""
    global connection_pool
    if connection_pool:
        connection_pool.cleanup()
        connection_pool = None
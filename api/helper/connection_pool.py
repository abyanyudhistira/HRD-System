"""
PostgreSQL Connection Pool for LinkedIn Crawler
Provides pooled database connections for better performance
"""
import threading
import time
import queue
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        database=os.getenv('POSTGRES_DB', 'hrd_system'),
        user=os.getenv('POSTGRES_USER', 'hrd_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'hrd_password_change_me')
    )

class ConnectionPool:
    """PostgreSQL connection pool manager"""
    
    def __init__(self, pool_size=None):
        # Get configuration from environment
        self.pool_size = pool_size or int(os.getenv('DB_POOL_SIZE', '5'))
        
        self.available_connections = queue.Queue(maxsize=self.pool_size)
        self.all_connections = []
        self.lock = threading.Lock()
        
        # Initialize pool
        self._initialize_pool()
        
    def _initialize_pool(self):
        """Initialize connection pool"""
        print(f"🔗 Initializing PostgreSQL connection pool (size: {self.pool_size})")
        
        for i in range(self.pool_size):
            try:
                connection_info = self._create_connection()
                self.available_connections.put(connection_info)
                self.all_connections.append(connection_info)
                print(f"   ✓ Connection {i+1}/{self.pool_size} created")
            except Exception as e:
                print(f"   ✗ Failed to create connection {i+1}: {e}")
        
        print(f"✓ Connection pool initialized with {self.available_connections.qsize()} connections")
    
    def _create_connection(self):
        """Create a new database connection"""
        conn = get_db_connection()
        
        # Test connection
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        except Exception as e:
            conn.close()
            raise e
        
        return {
            'connection': conn,
            'created_at': time.time(),
            'last_used': time.time()
        }
    
    def get_connection(self, timeout=30):
        """Get connection from pool"""
        try:
            connection_info = self.available_connections.get(timeout=timeout)
            connection_info['last_used'] = time.time()
            
            # Test if connection is still alive
            try:
                with connection_info['connection'].cursor() as cur:
                    cur.execute("SELECT 1")
            except:
                # Connection is dead, create new one
                try:
                    connection_info['connection'].close()
                except:
                    pass
                connection_info = self._create_connection()
            
            return connection_info
        except queue.Empty:
            raise Exception(f"No available connections in pool (timeout: {timeout}s)")
    
    def return_connection(self, connection_info):
        """Return connection to pool"""
        try:
            self.available_connections.put_nowait(connection_info)
        except queue.Full:
            # Pool is full, close this connection
            try:
                connection_info['connection'].close()
            except:
                pass
    
    def close_all(self):
        """Close all connections in pool"""
        print("🔗 Closing all connections in pool...")
        
        with self.lock:
            # Close available connections
            while not self.available_connections.empty():
                try:
                    connection_info = self.available_connections.get_nowait()
                    connection_info['connection'].close()
                except:
                    pass
            
            # Close all tracked connections
            for connection_info in self.all_connections:
                try:
                    connection_info['connection'].close()
                except:
                    pass
            
            self.all_connections.clear()
        
        print("✓ All connections closed")

# Global connection pool instance
_connection_pool = None
_pool_lock = threading.Lock()

def get_connection_pool():
    """Get global connection pool instance"""
    global _connection_pool
    
    if _connection_pool is None:
        with _pool_lock:
            if _connection_pool is None:
                _connection_pool = ConnectionPool()
    
    return _connection_pool

def get_pooled_db_manager():
    """Get database manager using connection pool"""
    from database import Database
    return Database()

def cleanup_connection_pool():
    """Cleanup global connection pool"""
    global _connection_pool
    
    if _connection_pool:
        _connection_pool.close_all()
        _connection_pool = None
"""
Browser Pool - Manage reusable browser instances for better performance
"""
import threading
import time
import queue
import os
from crawler import LinkedInCrawler
from helper.browser_helper import create_driver


class BrowserPool:
    """Thread-safe browser pool for reusing logged-in browser instances"""
    
    def __init__(self, pool_size=None):
        # Get pool size from environment or default to 3
        self.pool_size = pool_size or int(os.getenv('BROWSER_POOL_SIZE', '3'))
        self.available_browsers = queue.Queue(maxsize=self.pool_size)
        self.busy_browsers = set()
        self.lock = threading.Lock()
        self.created_count = 0
        self.max_browser_age = int(os.getenv('MAX_BROWSER_AGE_MINUTES', '60'))  # 1 hour
        
        print(f"🚗 Initializing Browser Pool (size: {self.pool_size})...")
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize browser pool with logged-in browsers"""
        for i in range(self.pool_size):
            try:
                print(f"   Creating browser {i+1}/{self.pool_size}...")
                browser_info = self._create_browser_with_login()
                self.available_browsers.put(browser_info)
                print(f"   ✓ Browser {i+1} ready and logged in")
            except Exception as e:
                print(f"   ✗ Failed to create browser {i+1}: {e}")
        
        print(f"✅ Browser Pool initialized with {self.available_browsers.qsize()} browsers")
    
    def _create_browser_with_login(self):
        """Create a new browser instance and login"""
        crawler = LinkedInCrawler()
        crawler.login()
        
        browser_info = {
            'crawler': crawler,
            'created_at': time.time(),
            'usage_count': 0,
            'last_used': time.time()
        }
        
        with self.lock:
            self.created_count += 1
        
        return browser_info
    
    def get_browser(self, timeout=30):
        """Get an available browser from the pool"""
        try:
            # Try to get browser from pool
            browser_info = self.available_browsers.get(timeout=timeout)
            
            with self.lock:
                self.busy_browsers.add(browser_info)
            
            # Check if browser is too old
            age_minutes = (time.time() - browser_info['created_at']) / 60
            if age_minutes > self.max_browser_age:
                print(f"⚠ Browser too old ({age_minutes:.1f}min), refreshing...")
                self._refresh_browser(browser_info)
            
            browser_info['last_used'] = time.time()
            browser_info['usage_count'] += 1
            
            return browser_info
            
        except queue.Empty:
            print("⚠ No browsers available in pool, creating temporary browser...")
            return self._create_browser_with_login()
    
    def return_browser(self, browser_info):
        """Return browser to the pool"""
        try:
            with self.lock:
                if browser_info in self.busy_browsers:
                    self.busy_browsers.remove(browser_info)
            
            # Check browser health before returning
            if self._is_browser_healthy(browser_info):
                self.available_browsers.put_nowait(browser_info)
            else:
                print("⚠ Browser unhealthy, creating replacement...")
                self._replace_browser(browser_info)
                
        except queue.Full:
            # Pool is full, close this browser
            print("⚠ Pool full, closing excess browser")
            self._close_browser(browser_info)
    
    def _is_browser_healthy(self, browser_info):
        """Check if browser is still healthy"""
        try:
            crawler = browser_info['crawler']
            # Simple health check - try to get current URL
            current_url = crawler.driver.current_url
            return 'linkedin.com' in current_url or current_url == 'data:,'
        except:
            return False
    
    def _refresh_browser(self, browser_info):
        """Refresh browser by re-login"""
        try:
            crawler = browser_info['crawler']
            crawler.login()
            browser_info['created_at'] = time.time()
            browser_info['usage_count'] = 0
            print("✓ Browser refreshed successfully")
        except Exception as e:
            print(f"✗ Failed to refresh browser: {e}")
            # Create new browser
            self._replace_browser(browser_info)
    
    def _replace_browser(self, old_browser_info):
        """Replace unhealthy browser with new one"""
        try:
            # Close old browser
            self._close_browser(old_browser_info)
            
            # Create new browser
            new_browser_info = self._create_browser_with_login()
            self.available_browsers.put_nowait(new_browser_info)
            print("✓ Browser replaced successfully")
            
        except Exception as e:
            print(f"✗ Failed to replace browser: {e}")
    
    def _close_browser(self, browser_info):
        """Safely close browser"""
        try:
            crawler = browser_info['crawler']
            crawler.close()
        except Exception as e:
            print(f"⚠ Error closing browser: {e}")
    
    def get_pool_stats(self):
        """Get pool statistics"""
        with self.lock:
            return {
                'pool_size': self.pool_size,
                'available': self.available_browsers.qsize(),
                'busy': len(self.busy_browsers),
                'total_created': self.created_count
            }
    
    def cleanup(self):
        """Cleanup all browsers in pool"""
        print("🧹 Cleaning up browser pool...")
        
        # Close busy browsers
        with self.lock:
            for browser_info in list(self.busy_browsers):
                self._close_browser(browser_info)
            self.busy_browsers.clear()
        
        # Close available browsers
        while not self.available_browsers.empty():
            try:
                browser_info = self.available_browsers.get_nowait()
                self._close_browser(browser_info)
            except queue.Empty:
                break
        
        print("✓ Browser pool cleanup completed")


# Global browser pool instance
browser_pool = None

def get_browser_pool():
    """Get global browser pool instance"""
    global browser_pool
    if browser_pool is None:
        browser_pool = BrowserPool()
    return browser_pool

def cleanup_browser_pool():
    """Cleanup global browser pool"""
    global browser_pool
    if browser_pool:
        browser_pool.cleanup()
        browser_pool = None
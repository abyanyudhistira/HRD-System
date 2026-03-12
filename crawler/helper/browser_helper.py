"""Browser automation helper functions"""
import time
import random
from dotenv import load_dotenv
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.action_chains import ActionChains

load_dotenv()

# Load delay configuration from environment
try:
    MIN_DELAY = float(os.getenv('MIN_DELAY'))
    MAX_DELAY = float(os.getenv('MAX_DELAY'))
    PROFILE_DELAY_MIN = float(os.getenv('PROFILE_DELAY_MIN'))
    PROFILE_DELAY_MAX = float(os.getenv('PROFILE_DELAY_MAX'))
    USE_MOBILE_MODE = os.getenv('USE_MOBILE_MODE').lower() == 'true'
except:
    MIN_DELAY = 2.0
    MAX_DELAY = 5.0
    PROFILE_DELAY_MIN = 10.0
    PROFILE_DELAY_MAX = 20.0
    USE_MOBILE_MODE = False


def create_driver(mobile_mode=None):
    """Create and configure Chrome driver with anti-detection"""
    if mobile_mode is None:
        mobile_mode = USE_MOBILE_MODE
    
    options = webdriver.ChromeOptions()
    
    # Check if running in production (Docker/Render)
    is_production = os.getenv('RENDER', 'false').lower() == 'true' or os.getenv('DOCKER', 'false').lower() == 'true'
    
    # Anti-detection: Hide automation flags
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Stealth mode
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    
    # Production mode: headless
    if is_production:
        options.add_argument('--headless=new')  # New headless mode (more stable)
        options.add_argument('--disable-software-rasterizer')
        print("🔧 Running in HEADLESS mode (production)")
    
    # User agent and window size
    if mobile_mode:
        mobile_user_agents = [
            'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Linux; Android 12; SM-S906N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36',
        ]
        selected_ua = random.choice(mobile_user_agents)
        options.add_argument(f'user-agent={selected_ua}')
        options.add_argument('--window-size=412,915')
        mobile_emulation = {
            "deviceMetrics": {"width": 412, "height": 915, "pixelRatio": 2.625},
            "userAgent": selected_ua
        }
        options.add_experimental_option("mobileEmulation", mobile_emulation)
        print("🔧 Using MOBILE mode (412x915)")
    else:
        user_agents = [
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
        ]
        selected_ua = random.choice(user_agents)
        options.add_argument(f'user-agent={selected_ua}')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--start-maximized')
        print("🔧 Using DESKTOP mode (1920x1080)")
    
    options.add_argument('--lang=en-US')
    options.add_experimental_option('prefs', {'intl.accept_languages': 'en-US,en'})
    
    driver = None
    try:
        service = ChromeService()
        driver = webdriver.Chrome(service=service, options=options)
        print("✓ Using Selenium auto-managed ChromeDriver")
    except Exception as e:
        print(f"⚠ Selenium auto-download failed: {e}")
        try:
            print("  Trying webdriver-manager...")
            from webdriver_manager.chrome import ChromeDriverManager
            import shutil
            cache_path = os.path.expanduser("~/.wdm")
            if os.path.exists(cache_path):
                shutil.rmtree(cache_path, ignore_errors=True)
            driver_path = ChromeDriverManager().install()
            service = ChromeService(executable_path=driver_path)
            driver = webdriver.Chrome(service=service, options=options)
            print("✓ Using webdriver-manager ChromeDriver")
        except:
            raise Exception("Failed to create ChromeDriver")
    
    if driver is None:
        raise Exception("Failed to create ChromeDriver")
    
    # Anti-detection scripts
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    driver.execute_script("""
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        window.chrome = {runtime: {}};
    """)
    
    return driver


def human_delay(min_sec=None, max_sec=None):
    """Random delay to mimic human behavior"""
    if min_sec is None:
        min_sec = MIN_DELAY
    if max_sec is None:
        max_sec = MAX_DELAY
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)


def profile_delay():
    """Longer delay between profiles to avoid detection"""
    delay = random.uniform(PROFILE_DELAY_MIN, PROFILE_DELAY_MAX)
    print(f"⏳ Waiting {delay:.1f}s before next profile (anti-detection)...")
    time.sleep(delay)


def random_mouse_movement(driver):
    """Simulate random mouse movements"""
    try:
        actions = ActionChains(driver)
        for _ in range(random.randint(2, 4)):
            x_offset = random.randint(-100, 100)
            y_offset = random.randint(-100, 100)
            actions.move_by_offset(x_offset, y_offset)
        actions.perform()
    except:
        pass


def smooth_scroll(driver, element):
    """Smooth scroll to element"""
    driver.execute_script(
        "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
        element
    )
    time.sleep(random.uniform(0.3, 0.6))


def scroll_page_to_load(driver):
    """Scroll entire page to load all lazy-loaded content"""
    print("Scrolling page to load all content...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_pause_time = random.uniform(0.8, 1.2)
    
    for i in range(5):
        scroll_amount = random.randint(1000, 1500)
        driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
        time.sleep(random.uniform(0.5, 0.8))
        if random.random() > 0.85:
            driver.execute_script(f"window.scrollBy(0, -{random.randint(100, 300)});")
            time.sleep(random.uniform(0.3, 0.5))
    
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(scroll_pause_time)
    new_height = driver.execute_script("return document.body.scrollHeight")
    if new_height > last_height:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_pause_time)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(random.uniform(0.5, 0.8))

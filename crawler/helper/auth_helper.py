"""Authentication helper for LinkedIn login and session management"""
import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .browser_helper import human_delay


COOKIES_FILE = "data/cookie/.linkedin_cookies.json"


def save_cookies(driver):
    """Save cookies to JSON file for session persistence"""
    try:
        Path("data/cookie").mkdir(parents=True, exist_ok=True)
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, 'w') as f:
            json.dump(cookies, f, indent=2)
        print("✓ Cookies saved for future sessions")
    except Exception as e:
        print(f"⚠ Could not save cookies: {e}")


def load_cookies(driver):
    """Load cookies from JSON file"""
    try:
        if not os.path.exists(COOKIES_FILE):
            return False
        
        driver.get('https://www.linkedin.com')
        human_delay(2, 3)
        
        with open(COOKIES_FILE, 'r') as f:
            cookies = json.load(f)
        
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except:
                pass
        
        # Navigate to feed to verify login
        print("  Navigating to feed to verify session...")
        driver.get('https://www.linkedin.com/feed/')
        human_delay(3, 4)
        
        current_url = driver.current_url
        # Check if we're on feed or if we got redirected to login
        if 'feed' in current_url or 'mynetwork' in current_url or '/in/' in current_url:
            print("✓ Logged in using saved session!")
            return True
        elif 'login' in current_url or 'uas/login' in current_url:
            print("  ⚠ Session expired, cookies invalid")
            return False
        else:
            # Unknown state, but not on login page - assume success
            print(f"  ✓ Session appears valid (URL: {current_url[:50]}...)")
            return True
        
    except Exception as e:
        print(f"⚠ Could not load cookies: {e}")
        return False


def login(driver):
    """Login to LinkedIn with automatic verification detection and OAuth support"""
    load_dotenv()
    
    print("Checking for saved session...")
    if load_cookies(driver):
        return
    
    # Check if OAuth mode is enabled
    use_oauth = os.getenv('USE_OAUTH_LOGIN', 'false').lower() == 'true'
    
    if use_oauth:
        print("\n" + "="*60)
        print("🔐 OAUTH LOGIN MODE")
        print("="*60)
        print("Silakan login manual menggunakan Google/Microsoft/Apple")
        print("Browser akan terbuka ke halaman login LinkedIn")
        print("="*60 + "\n")
        
        driver.get('https://www.linkedin.com/login')
        human_delay(2, 3)
        
        print("⏳ Menunggu Anda login...")
        print("   Tekan ENTER setelah berhasil login dan melihat feed/homepage")
        input("\nTekan ENTER setelah login berhasil...")
        
        # Verify login success
        current_url = driver.current_url
        if 'feed' in current_url or 'mynetwork' in current_url or '/in/' in current_url:
            print("✓ Login berhasil!")
            save_cookies(driver)
            return
        else:
            print(f"⚠ Warning: URL saat ini: {current_url}")
            retry = input("Apakah Anda sudah login? (y/n): ")
            if retry.lower() == 'y':
                save_cookies(driver)
                return
            else:
                raise Exception("Login dibatalkan")
    
    # Original email/password login flow
    email = os.getenv('LINKEDIN_EMAIL')
    password = os.getenv('LINKEDIN_PASSWORD')
    
    if not email or not password:
        print("\n⚠ LinkedIn credentials not found in .env file")
        print("  Falling back to manual login mode...")
        print("  (Set USE_OAUTH_LOGIN=true in .env to skip this message)")
        
        driver.get('https://www.linkedin.com/login')
        human_delay(2, 3)
        
        print("\n⏳ Silakan login manual di browser...")
        input("Tekan ENTER setelah berhasil login...")
        save_cookies(driver)
        return
    
    print("Attempting automatic login...")
    driver.get('https://www.linkedin.com/login')
    human_delay(2, 3)
    
    try:
        wait = WebDriverWait(driver, 10)
        
        print("Filling email...")
        email_field = wait.until(EC.presence_of_element_located((By.ID, 'username')))
        email_field.clear()
        email_field.send_keys(email)
        human_delay(0.5, 1.0)
        
        print("Filling password...")
        password_field = driver.find_element(By.ID, 'password')
        password_field.clear()
        password_field.send_keys(password)
        human_delay(0.5, 1.0)
        
        print("Clicking login button...")
        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()
        
        print("Checking login status...")
        human_delay(3, 5)
        
        current_url = driver.current_url
        
        verification_indicators = [
            'checkpoint/challenge', 'challenge', 'verify', 'captcha',
            '/uas/login-submit', 'phone',
        ]
        
        needs_verification = any(indicator in current_url for indicator in verification_indicators)
        
        if needs_verification:
            print("\n" + "="*60)
            print("⚠ VERIFICATION REQUIRED!")
            print("="*60)
            page_text = driver.page_source.lower()
            if 'phone' in page_text or 'number' in page_text:
                print("Type: PHONE VERIFICATION")
            elif 'captcha' in page_text or 'puzzle' in page_text:
                print("Type: CAPTCHA/PUZZLE")
            elif 'pin' in page_text or 'code' in page_text:
                print("Type: PIN/CODE (check your email)")
            else:
                print("Type: SECURITY CHECK")
            
            print("\nSilakan selesaikan verifikasi di browser")
            print("Tekan ENTER setelah verifikasi selesai...")
            print("="*60 + "\n")
            
            input("Tekan ENTER setelah verifikasi selesai dan Anda sudah login...")
            
            current_url = driver.current_url
            if 'feed' in current_url or 'mynetwork' in current_url or '/in/' in current_url:
                print("✓ Login berhasil!")
                save_cookies(driver)
            else:
                print("⚠ Warning: Sepertinya belum berhasil login.")
                retry = input("Lanjutkan scraping? (y/n): ")
                if retry.lower() != 'y':
                    raise Exception("Login dibatalkan")
        else:
            if 'feed' in current_url or 'mynetwork' in current_url or '/in/' in current_url:
                print("✓ Login otomatis berhasil tanpa verifikasi!")
                save_cookies(driver)
            else:
                print(f"⚠ Login status tidak jelas. Current URL: {current_url}")
                input("Tekan ENTER jika sudah login di browser...")
                save_cookies(driver)
    
    except Exception as e:
        print(f"\nError during login: {e}")
        import traceback
        traceback.print_exc()
        print("\nSilakan login manual di browser yang terbuka...")
        input("Tekan ENTER setelah berhasil login...")
        save_cookies(driver)

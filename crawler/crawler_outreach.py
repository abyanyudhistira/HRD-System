"""LinkedIn Automated Outreach - Connection Request with Note"""
import json
import os
import time
import random
import threading
import pika
from datetime import datetime
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from helper.rabbitmq_helper import RabbitMQManager, ack_message, nack_message
from helper.supabase_helper import SupabaseManager
from helper.browser_helper import create_driver, human_delay
from helper.auth_helper import login

load_dotenv()

# Configuration
OUTREACH_QUEUE = os.getenv('OUTREACH_QUEUE', 'outreach_queue')

# Initialize Supabase Manager
supabase_manager = None

def init_supabase():
    """Initialize Supabase manager with better error handling"""
    global supabase_manager
    
    if supabase_manager is not None:
        return True
    
    try:
        print(f"🔌 Connecting to Supabase...")
        supabase_manager = SupabaseManager()
        
        # Test connection
        test_lead = supabase_manager.client.table('leads_list').select('id').limit(1).execute()
        print("✓ Supabase manager initialized and tested successfully")
        return True
    except ValueError as e:
        print(f"⚠️  Supabase credentials missing: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Failed to initialize Supabase: {e}")
        import traceback
        traceback.print_exc()
        supabase_manager = None
        return False

# Try to initialize on module load
init_supabase()


def update_lead_status(profile_url, note_sent, status='success'):
    """
    Update lead status in Supabase after outreach
    
    Args:
        profile_url: LinkedIn profile URL (unique identifier)
        note_sent: The message that was sent
        status: Connection status ('success', 'pending', 'failed')
    """
    # Try to initialize if not already done
    if not supabase_manager:
        print("  ⚠️  Supabase not initialized, attempting to initialize...")
        if not init_supabase():
            print("  ✗ Failed to initialize Supabase, skipping database update")
            return False
    
    try:
        print(f"\n📝 Updating database...")
        print(f"  Profile: {profile_url}")
        print(f"  Status: {status}")
        print(f"  Note: {note_sent[:50]}...")
        
        # Use the helper method
        return supabase_manager.update_outreach_status(
            profile_url=profile_url,
            note_sent=note_sent,
            status=status
        )
    
    except Exception as e:
        print(f"  ✗ Failed to update database: {e}")
        import traceback
        traceback.print_exc()
        return False


def find_connect_button(driver, wait):
    """
    Find Connect button with correct priority order:
    
    IN HEADER:
    1. Look for Connect FIRST (aria-label "Invite...to connect")
    2. If not found → check Pending
    3. If not found → check Remove connection
    4. If none found → open More dropdown
    
    IN DROPDOWN:
    1. Check Remove connection FIRST
    2. If not found → check Pending
    3. If not found → look for Connect
    4. If none found → error
    """
    
    # 1️⃣ HEADER: Try Connect button FIRST (PROFILE AREA ONLY)
    print("  🔍 Step 1: Looking for Connect button in profile header...")
    
    # Add explicit wait for page to fully render
    time.sleep(2)
    
    # Search in ph5 container (main profile area)
    try:
        connect_buttons = driver.find_elements(By.XPATH, 
            "//div[contains(@class, 'ph5')]//button[contains(@aria-label, 'Invite') and contains(@aria-label, 'to connect')]")
        
        for btn in connect_buttons:
            try:
                if btn.is_displayed() and btn.is_enabled():
                    # Extra validation: check if button has primary styling (not muted/secondary from recommendations)
                    btn_class = btn.get_attribute('class') or ''
                    if 'artdeco-button--primary' in btn_class:
                        btn_label = btn.get_attribute('aria-label') or ''
                        print(f"  ✓ Found Connect button in ph5 area: {btn_label[:60]}")
                        return btn
            except:
                continue
    except Exception as e:
        print(f"  ⚠️  Error searching Connect in ph5 area: {e}")
    
    print("  ℹ️  Connect button not found in profile header")
    
    # 2️⃣ HEADER: Check for Pending button (PROFILE AREA ONLY)
    print("  🔍 Step 2: Checking for Pending button in profile header...")
    
    try:
        # Search in ph5 area
        pending_buttons = driver.find_elements(By.XPATH, 
            "//div[contains(@class, 'ph5')]//button[.//span[normalize-space()='Pending']]")
        
        for btn in pending_buttons:
            try:
                if btn.is_displayed():
                    # Check if it's primary/secondary button (not from recommendations which are muted)
                    btn_class = btn.get_attribute('class') or ''
                    if 'artdeco-button--primary' in btn_class or 'artdeco-button--secondary' in btn_class:
                        print("  ✅ Found Pending button in ph5 area - request already sent!")
                        return "PENDING"
            except:
                continue
    except Exception as e:
        print(f"  ⚠️  Error checking Pending: {e}")
    
    print("  ℹ️  Pending button not found in profile header")
    
    # 3️⃣ HEADER: Check for Remove connection button (PROFILE AREA ONLY)
    print("  🔍 Step 3: Checking for Remove connection button in profile header...")
    
    try:
        # Search in ph5 area
        remove_buttons = driver.find_elements(By.XPATH, 
            "//div[contains(@class, 'ph5')]//button[contains(., 'Remove connection') or contains(@aria-label, 'Remove connection')]")
        
        for btn in remove_buttons:
            try:
                if btn.is_displayed():
                    print("  ✅ Found Remove connection in ph5 area - already connected!")
                    return "ALREADY_CONNECTED"
            except:
                continue
    except Exception as e:
        print(f"  ⚠️  Error checking Remove connection: {e}")
    
    print("  ℹ️  Remove connection button not found in profile header")
    
    # 4️⃣ HEADER: None found → open More dropdown
    print("  🔍 Step 4: Opening More dropdown...")
    
    # Search More button with multiple strategies
    more_button = None
    more_selectors = [
        # Most specific - in profile actions area
        "//div[contains(@class, 'pvs-sticky-header-profile-actions')]//button[contains(@aria-label, 'More actions')]",
        "//div[contains(@class, 'pvs-sticky-header-profile-actions')]//button[contains(., 'More')]",
        # In any profile header area
        "//div[contains(@class, 'pv-top-card')]//button[contains(@aria-label, 'More actions')]",
        # Generic but check if it's in top part of page
        "//button[contains(@aria-label, 'More actions') and contains(@id, 'profile-overflow')]",
        "//button[contains(@aria-label, 'More actions')]",
    ]
    
    for i, selector in enumerate(more_selectors):
        try:
            print(f"  Trying More selector {i+1}/{len(more_selectors)}...")
            buttons = driver.find_elements(By.XPATH, selector)
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    # Check if button is in top part of page (not in recommendations)
                    location = btn.location
                    if location['y'] < 1000:  # Top 1000px of page
                        more_button = btn
                        print(f"  ✓ Found More button at y={location['y']}")
                        break
            if more_button:
                break
        except Exception as e:
            print(f"  Selector {i+1} failed: {e}")
            continue
    
    if not more_button:
        print("  ✗ More button not found")
        return None
    
    print("  ✓ Clicking More button...")
    more_button.click()
    
    # Wait for dropdown to appear and be visible
    print("  ⏳ Waiting for dropdown to appear...")
    time.sleep(3)  # Increased wait time
    
    # Wait for dropdown menu to be visible
    try:
        wait.until(EC.presence_of_element_located((By.XPATH, "//div[@role='menu' or contains(@class, 'artdeco-dropdown__content')]")))
        print("  ✓ Dropdown appeared")
    except:
        print("  ⚠️  Dropdown wait timeout, continuing anyway...")
    
    time.sleep(1)  # Extra wait for animation
    
    # 5️⃣ DROPDOWN: Check Remove connection FIRST
    print("  🔍 Step 5: Checking for Remove connection in dropdown...")
    
    try:
        dropdown_elements = driver.find_elements(By.XPATH, 
            "//div[@role='menu']//div[@role='button'] | //div[contains(@class, 'artdeco-dropdown__content')]//div[@role='button']")
        
        for elem in dropdown_elements:
            try:
                if elem.is_displayed():
                    elem_text = elem.text.strip().lower()
                    elem_label = (elem.get_attribute('aria-label') or '').lower()
                    
                    # Check if this is "Remove connection"
                    if ('remove' in elem_text and 'connection' in elem_text) or \
                       ('remove' in elem_label and 'connection' in elem_label):
                        print(f"  ✅ Found Remove connection in dropdown - already connected!")
                        return "ALREADY_CONNECTED"
            except:
                continue
    except Exception as e:
        print(f"  ⚠️  Error checking Remove connection in dropdown: {e}")
    
    print("  ℹ️  Remove connection not found in dropdown")
    
    # 6️⃣ DROPDOWN: Check for Pending
    print("  🔍 Step 6: Checking for Pending in dropdown...")
    
    try:
        dropdown_elements = driver.find_elements(By.XPATH, 
            "//div[@role='menu']//div[@role='button'] | //div[contains(@class, 'artdeco-dropdown__content')]//div[@role='button']")
        
        for elem in dropdown_elements:
            try:
                if elem.is_displayed():
                    elem_text = elem.text.strip().lower()
                    elem_label = (elem.get_attribute('aria-label') or '').lower()
                    
                    # Check if this is Pending
                    if 'pending' in elem_text or 'pending' in elem_label:
                        print(f"  ✅ Found Pending in dropdown - request already sent!")
                        return "PENDING"
            except:
                continue
    except Exception as e:
        print(f"  ⚠️  Error checking Pending in dropdown: {e}")
    
    print("  ℹ️  Pending not found in dropdown")
    
    # 7️⃣ DROPDOWN: Search for Connect button
    print("  🔍 Step 7: Searching for Connect in dropdown...")
    dropdown_connect_selectors = [
        # By aria-label (most specific) - must contain "Invite" and "connect"
        "//div[@role='button' and contains(@aria-label, 'Invite') and contains(@aria-label, 'connect')]",
        # By exact text match
        "//div[contains(@class, 'artdeco-dropdown__item') and @role='button']//span[normalize-space(text())='Connect']/parent::div",
        # Generic - will validate manually
        "//div[@role='menu']//div[@role='button']",
        "//div[contains(@class, 'artdeco-dropdown__content')]//div[@role='button']",
    ]
    
    for i, selector in enumerate(dropdown_connect_selectors):
        try:
            print(f"  Trying dropdown selector {i+1}/{len(dropdown_connect_selectors)}...")
            elements = driver.find_elements(By.XPATH, selector)
            print(f"    Found {len(elements)} elements")
            for elem in elements:
                if elem.is_displayed() and elem.is_enabled():
                    # Get text and label
                    elem_text = elem.text.strip().lower()
                    elem_label = (elem.get_attribute('aria-label') or '').lower()
                    print(f"    Checking: text='{elem.text.strip()}', label='{elem_label[:60]}'")
                    
                    # CRITICAL: Reject dangerous keywords
                    dangerous_keywords = ['remove', 'withdraw', 'pending', 'message', 'unfollow', 'disconnect']
                    has_dangerous = any(keyword in elem_text or keyword in elem_label for keyword in dangerous_keywords)
                    
                    if has_dangerous:
                        print(f"    ✗ REJECTED: contains dangerous keyword")
                        continue
                    
                    # CRITICAL: Accept only if:
                    # 1. Text is EXACTLY "connect" (not "connection", "disconnect")
                    # 2. OR label contains "invite" + "connect" (LinkedIn's aria-label pattern)
                    is_valid_text = elem_text == 'connect'
                    is_valid_label = 'invite' in elem_label and 'connect' in elem_label and 'to connect' in elem_label
                    
                    if is_valid_text or is_valid_label:
                        print(f"  ✓ Found valid Connect inside dropdown!")
                        return elem
                    else:
                        print(f"    ✗ REJECTED: text '{elem_text}' not exactly 'connect' and label not valid")
        except Exception as e:
            print(f"  Selector {i+1} failed: {e}")
            continue
    
    print("  ✗ Connect not found inside dropdown")
    return None


def type_like_human(element, text):
    """Type text character by character with human-like behavior"""
    print(f"  ⌨️  Typing message ({len(text)} chars)...")
    
    for i, char in enumerate(text):
        element.send_keys(char)
        
        # Variable typing speed
        if char == ' ':
            # Longer pause at spaces
            delay = random.uniform(0.1, 0.3)
        elif char in ',.!?':
            # Longer pause at punctuation
            delay = random.uniform(0.2, 0.5)
        else:
            # Normal typing speed
            delay = random.uniform(0.05, 0.15)
        
        time.sleep(delay)
        
        # Occasional typo simulation (5% chance)
        if random.random() < 0.05 and i < len(text) - 1:
            # Type wrong character
            wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
            element.send_keys(wrong_char)
            time.sleep(random.uniform(0.1, 0.2))
            # Backspace to delete
            element.send_keys('\b')
            time.sleep(random.uniform(0.1, 0.2))
        
        # Progress indicator every 20 chars
        if (i + 1) % 20 == 0:
            print(f"    Progress: {i + 1}/{len(text)} chars")
    
    print(f"  ✓ Typing completed!")


def send_connection_request(driver, profile_url, lead_name, message_template, dry_run=True):
    """
    Navigate to profile, click Connect, add note, type message
    
    Args:
        driver: Selenium WebDriver
        profile_url: LinkedIn profile URL
        lead_name: Name of the lead (for personalization)
        message_template: Message template with {lead_name} placeholder
        dry_run: If True, don't click Send button (for testing)
    
    Returns:
        dict: Result with status and details
    """
    result = {
        'status': 'failed',
        'profile_url': profile_url,
        'lead_name': lead_name,
        'error': None,
        'screenshot': None
    }
    
    try:
        print(f"\n{'='*60}")
        print(f"🎯 Target: {lead_name}")
        print(f"🔗 URL: {profile_url}")
        print(f"{'='*60}\n")
        
        # Navigate to profile
        print("1️⃣  Opening profile...")
        driver.get(profile_url)
        human_delay(3, 5)
        
        # Scroll to top to ensure buttons are visible
        print("  Scrolling to top...")
        driver.execute_script("window.scrollTo(0, 0);")
        human_delay(1, 2)
        
        # Wait for page to fully load
        wait = WebDriverWait(driver, 20)
        
        # Wait for profile section to load
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "main")))
        except:
            pass
        
        human_delay(2, 3)
        
        # Find and click Connect button
        print("2️⃣  Looking for Connect button...")
        
        # Use the new find_connect_button function
        connect_button = find_connect_button(driver, wait)
        
        # Check for special status returns
        if connect_button == "PENDING":
            print("  ✅ Connection request already PENDING!")
            print("  ℹ️  Treating as success (request was sent previously)")
            result['status'] = 'pending_success'
            result['error'] = None
            result['note'] = 'Connection request already pending (sent previously)'
            return result
        
        if connect_button == "ALREADY_CONNECTED":
            print("  ✅ Already connected!")
            print("  ℹ️  Treating as success (already connected)")
            result['status'] = 'already_connected_success'
            result['error'] = None
            result['note'] = 'Already connected (Remove connection button found)'
            return result
        
        if not connect_button:
            print("  ✗ Connect button not found!")
            print("  Taking screenshot for debugging...")
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                screenshot_dir = 'data/output/outreach_screenshots'
                os.makedirs(screenshot_dir, exist_ok=True)
                screenshot_path = f"{screenshot_dir}/debug_no_connect_{timestamp}.png"
                driver.save_screenshot(screenshot_path)
                print(f"  📸 Debug screenshot: {screenshot_path}")
                result['screenshot'] = screenshot_path
                
                # Also save page source for debugging
                html_path = f"{screenshot_dir}/debug_page_source_{timestamp}.html"
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(driver.page_source)
                print(f"  📄 Page source: {html_path}")
            except:
                pass
            result['error'] = 'Connect button not found'
            return result
        human_delay(1, 2)
        
        # Click Connect
        print("3️⃣  Clicking Connect...")
        connect_button.click()
        human_delay(2, 3)
        
        # Wait for modal to appear
        print("4️⃣  Waiting for 'Add a note' modal...")
        
        # Click "Add a note" button in the modal
        try:
            add_note_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'Add a note')]"))
            )
            print("  ✓ Found 'Add a note' button")
            human_delay(1, 2)
            add_note_button.click()
            human_delay(2, 3)
        except:
            print("  ⚠️  'Add a note' button not found, checking if note field is already visible...")
        
        # Find the note textarea
        print("5️⃣  Looking for note textarea...")
        note_field = None
        textarea_selectors = [
            "//textarea[@name='message']",
            "//textarea[@id='custom-message']",
            "//textarea[contains(@placeholder, 'Add a note')]",
            "//textarea[contains(@aria-label, 'Add a note')]",
        ]
        
        for selector in textarea_selectors:
            try:
                note_field = wait.until(
                    EC.presence_of_element_located((By.XPATH, selector))
                )
                break
            except:
                continue
        
        if not note_field:
            print("  ✗ Note textarea not found!")
            result['error'] = 'Note textarea not found'
            return result
        
        print("  ✓ Found note textarea")
        human_delay(1, 2)
        
        # Message template is already personalized from process_outreach_job()
        # Just use it directly
        final_message = message_template
        
        # Check character limit (LinkedIn allows 300 chars)
        if len(final_message) > 300:
            print(f"  ⚠️  Message too long ({len(final_message)} chars), truncating to 300...")
            final_message = final_message[:297] + '...'
        
        print(f"6️⃣  Typing message...")
        print(f"  Message preview: {final_message[:50]}...")
        print(f"  Length: {len(final_message)} chars")
        
        # Click on textarea to focus
        note_field.click()
        human_delay(0.5, 1)
        
        # Type message like human
        type_like_human(note_field, final_message)
        
        human_delay(2, 3)
        
        # Take screenshot for verification
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_dir = 'data/output/outreach_screenshots'
        os.makedirs(screenshot_dir, exist_ok=True)
        
        name_slug = lead_name.replace(' ', '_').lower()
        screenshot_path = f"{screenshot_dir}/{name_slug}_{timestamp}.png"
        driver.save_screenshot(screenshot_path)
        print(f"  📸 Screenshot saved: {screenshot_path}")
        
        result['screenshot'] = screenshot_path
        
        if dry_run:
            print("\n" + "="*60)
            print("🧪 DRY RUN MODE - NOT SENDING")
            print("="*60)
            print("Message typed successfully!")
            print("Screenshot saved for verification")
            print("Set dry_run=False to actually send")
            print("="*60 + "\n")
            
            result['status'] = 'dry_run_success'
            
            # Close modal (click X or Cancel)
            try:
                close_button = driver.find_element(By.XPATH, "//button[@aria-label='Dismiss']")
                close_button.click()
                print("  ✓ Closed modal")
            except:
                try:
                    cancel_button = driver.find_element(By.XPATH, "//button[contains(., 'Cancel')]")
                    cancel_button.click()
                    print("  ✓ Cancelled connection request")
                except:
                    print("  ⚠️  Could not close modal, continuing...")
        else:
            # Find and click Send button
            print("7️⃣  Looking for Send button...")
            send_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'Send') or contains(., 'Send')]"))
            )
            
            print("  ✓ Found Send button")
            human_delay(1, 2)
            
            print("8️⃣  Clicking Send...")
            send_button.click()
            human_delay(2, 3)
            
            print("\n" + "="*60)
            print("✅ CONNECTION REQUEST SENT!")
            print("="*60 + "\n")
            
            result['status'] = 'sent'
        
        return result
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        
        result['error'] = str(e)
        
        # Try to take screenshot on error
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            screenshot_dir = 'data/output/outreach_screenshots'
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = f"{screenshot_dir}/error_{timestamp}.png"
            driver.save_screenshot(screenshot_path)
            result['screenshot'] = screenshot_path
            print(f"  📸 Error screenshot: {screenshot_path}")
        except:
            pass
        
        return result


def process_outreach_job(message_data, dry_run=True):
    """Process a single outreach job"""
    driver = None
    
    try:
        # Parse message
        lead_name = message_data.get('name', 'Unknown')
        profile_url = message_data.get('profile_url')
        message_template = message_data.get('message')
        
        if not profile_url or not message_template:
            print("✗ Invalid job data: missing profile_url or message")
            return {'status': 'invalid', 'error': 'Missing required fields'}
        
        # Personalize message (support both {lead_name} and [lead_name] formats)
        personalized_message = message_template.replace('{lead_name}', lead_name)
        personalized_message = personalized_message.replace('[lead_name]', lead_name)
        
        # Create browser
        print("🌐 Starting browser...")
        driver = create_driver(mobile_mode=False)
        
        # Login
        print("🔐 Logging in...")
        login(driver)
        
        # Send connection request
        result = send_connection_request(
            driver, 
            profile_url, 
            lead_name, 
            personalized_message,  # Use personalized message, not template
            dry_run=dry_run
        )
        
        # Update database if message was sent (both dry_run and live) or if already pending/connected
        if result['status'] in ['sent', 'dry_run_success', 'pending_success', 'already_connected_success']:
            print(f"\n{'='*60}")
            print("💾 UPDATING DATABASE")
            print(f"{'='*60}")
            
            # Status is 'success' because:
            # - Note was sent successfully, OR
            # - Already pending (sent previously), OR  
            # - Already connected
            db_status = 'success'
            
            print(f"Result status: {result['status']}")
            print(f"DB status: {db_status}")
            print(f"Profile URL: {profile_url}")
            print(f"Personalized message: {personalized_message[:50]}...")
            
            # Update Supabase
            update_success = update_lead_status(
                profile_url=profile_url,
                note_sent=personalized_message,
                status=db_status
            )
            
            result['database_updated'] = update_success
            
            if update_success:
                print(f"✅ Database update: SUCCESS")
            else:
                print(f"⚠️  Database update: FAILED")
            
            print(f"{'='*60}\n")
        else:
            print(f"\n⚠️  Skipping database update (status: {result['status']})")
            result['database_updated'] = False
        
        return result
    
    finally:
        if driver:
            print("🔒 Closing browser...")
            driver.quit()


def worker_thread(worker_id, outreach_queue):
    """Worker thread that consumes from outreach_queue"""
    print(f"[Worker {worker_id}] Started")
    
    # Connect to RabbitMQ
    mq = RabbitMQManager()
    mq.queue_name = outreach_queue
    
    if not mq.connect():
        print(f"[Worker {worker_id}] ✗ Failed to connect to RabbitMQ")
        return
    
    print(f"[Worker {worker_id}] ✓ Connected to RabbitMQ")
    
    # Initialize Supabase
    try:
        supabase = SupabaseManager()
        print(f"[Worker {worker_id}] ✓ Connected to Supabase")
    except Exception as e:
        print(f"[Worker {worker_id}] ✗ Failed to connect to Supabase: {e}")
        print(f"[Worker {worker_id}]   Continuing without Supabase...")
        supabase = None
    
    # Set QoS - process 1 at a time per worker
    mq.channel.basic_qos(prefetch_count=1)
    
    def callback(ch, method, properties, body):
        """Process each outreach job"""
        try:
            print(f"\n[Worker {worker_id}] " + "="*60)
            print(f"[Worker {worker_id}] 📥 NEW JOB RECEIVED")
            print(f"[Worker {worker_id}] " + "="*60)
            
            # Parse message
            message_data = json.loads(body)
            
            # Get dry_run flag from message (default True for safety)
            dry_run = message_data.get('dry_run', True)
            
            print(f"[Worker {worker_id}] Job ID: {message_data.get('job_id', 'N/A')}")
            print(f"[Worker {worker_id}] Lead: {message_data.get('name', 'Unknown')}")
            print(f"[Worker {worker_id}] URL: {message_data.get('profile_url', 'N/A')}")
            print(f"[Worker {worker_id}] Mode: {'🧪 DRY RUN (testing)' if dry_run else '🔴 LIVE (real send)'}")
            print(f"[Worker {worker_id}] " + "="*60)
            
            # Process job
            result = process_outreach_job(message_data, dry_run=dry_run)
            
            # Log result
            print(f"\n[Worker {worker_id}] " + "="*60)
            print(f"[Worker {worker_id}] 📊 JOB RESULT")
            print(f"[Worker {worker_id}] " + "="*60)
            print(f"[Worker {worker_id}] Status: {result['status']}")
            if result.get('error'):
                print(f"[Worker {worker_id}] Error: {result['error']}")
            if result.get('screenshot'):
                print(f"[Worker {worker_id}] Screenshot: {result['screenshot']}")
            if result.get('database_updated'):
                print(f"[Worker {worker_id}] Database: {'✓ Updated' if result['database_updated'] else '✗ Failed'}")
            print(f"[Worker {worker_id}] " + "="*60 + "\n")
            
            # Acknowledge message
            ack_message(ch, method.delivery_tag)
            
            # Rate limiting: wait before next job
            # With 3 workers running in parallel:
            # - Each worker waits 90 seconds between jobs
            # - Total throughput: ~3 requests per 90 seconds = 2 requests/minute
            # - Per hour: ~120 requests
            # - Per day: ~2,880 requests (still high, monitor for LinkedIn limits)
            # 
            # Safer option (recommended for new accounts):
            # - Use delay = 300 (5 minutes) for ~36 requests/hour, ~864/day
            delay = 60  # 60 seconds between jobs per worker
            print(f"[Worker {worker_id}] ⏳ Waiting {delay} seconds before next job (rate limiting)...")
            time.sleep(delay)
        
        except Exception as e:
            print(f"\n[Worker {worker_id}] ✗ Fatal error processing job: {e}")
            import traceback
            traceback.print_exc()
            
            # Don't requeue to avoid infinite loop
            nack_message(ch, method.delivery_tag, requeue=False)
    
    try:
        print(f"[Worker {worker_id}] ✓ Listening for jobs...")
        
        mq.channel.basic_consume(
            queue=outreach_queue,
            on_message_callback=callback,
            auto_ack=False
        )
        
        mq.channel.start_consuming()
    
    except KeyboardInterrupt:
        print(f"\n[Worker {worker_id}] ⚠ Interrupted by user")
    
    except Exception as e:
        print(f"\n[Worker {worker_id}] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        mq.close()
        print(f"[Worker {worker_id}] ✓ Stopped")


def main():
    """Main function to start multiple worker threads"""
    print("="*60)
    print("LINKEDIN AUTOMATED OUTREACH WORKER")
    print("="*60)
    print(f"Queue: {OUTREACH_QUEUE}")
    print("="*60 + "\n")
    
    # Number of workers from environment variable
    num_workers = int(os.getenv('MAX_WORKERS', '3'))
    print(f"→ Number of workers: {num_workers}")
    print(f"→ Queue: {OUTREACH_QUEUE}")
    print(f"→ Rate limit: 90 seconds between jobs per worker")
    print(f"→ Throughput: ~{num_workers * 40} requests/hour with {num_workers} workers\n")
    
    # Start worker threads
    print(f"→ Starting {num_workers} outreach workers...")
    threads = []
    for i in range(num_workers):
        t = threading.Thread(
            target=worker_thread,
            args=(i+1, OUTREACH_QUEUE),
            daemon=True
        )
        t.start()
        threads.append(t)
        time.sleep(0.5)
    
    print(f"\n✓ All {num_workers} workers are running!")
    print("\n💡 How it works:")
    print("  1. Each worker processes 1 job at a time")
    print("  2. Multiple workers run in parallel")
    print("  3. RabbitMQ distributes jobs across workers")
    print("  4. Each worker waits 90 seconds between jobs")
    print("\n  Press Ctrl+C to stop all workers\n")
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted by user. Stopping all workers...")
        print("  (Workers will finish current tasks)")


if __name__ == "__main__":
    main()

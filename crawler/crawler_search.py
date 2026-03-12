"""LinkedIn Profile Search Crawler - Search profiles by name"""
import json
import time
import random
import urllib.parse
import os
import sys
import threading
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import pika

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from helper.browser_helper import create_driver, human_delay
from helper.auth_helper import login
from helper.rabbitmq_helper import RabbitMQManager

load_dotenv()

# Queue configuration
SEARCH_QUEUE = os.getenv('SEARCH_QUEUE', 'linkedin_search_queue')
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '3'))


class LinkedInSearchCrawler:
    """Crawler untuk mencari profil LinkedIn berdasarkan nama"""
    
    def __init__(self):
        """Initialize crawler dengan browser dan login"""
        print("Initializing LinkedIn Search Crawler...")
        self.driver = create_driver()
        self.wait = WebDriverWait(self.driver, 10)
        
        # Login ke LinkedIn
        login(self.driver)
        print("✓ Ready to search profiles\n")
    
    def search_profile(self, name):
        """
        Cari profil LinkedIn berdasarkan nama
        
        Args:
            name (str): Nama yang akan dicari
            
        Returns:
            str or None: URL profil LinkedIn atau None jika tidak ditemukan
        """
        try:
            print(f"Searching for: {name}")
            
            # Encode nama untuk URL
            name_encoded = urllib.parse.quote(name)
            search_url = f"https://www.linkedin.com/search/results/all/?keywords={name_encoded}&origin=GLOBAL_SEARCH_HEADER"
            
            print(f"  Opening search page...")
            self.driver.get(search_url)
            
            # Wait untuk hasil pencarian muncul
            try:
                self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "main"))
                )
                human_delay(2, 3)
            except TimeoutException:
                print("  ⚠ Timeout waiting for search results")
                return None
            
            # Cek apakah ada hasil
            if self._is_no_results():
                print("  ✗ No results found")
                return None
            
            # Extract URL profil pertama
            profile_url = self._extract_first_profile_url()
            
            if profile_url:
                print(f"  ✓ Found: {profile_url}")
            else:
                print("  ✗ Could not extract profile URL")
            
            # Random delay untuk menghindari rate limit
            delay = random.uniform(3, 7)
            print(f"  Waiting {delay:.1f}s before next search...")
            time.sleep(delay)
            
            return profile_url
            
        except Exception as e:
            print(f"  ✗ Error searching profile: {e}")
            return None
    
    def _is_no_results(self):
        """Check apakah halaman menunjukkan 'no results'"""
        try:
            # Cek berbagai indikator "no results"
            no_results_indicators = [
                "//div[contains(text(), 'No results')]",
                "//div[contains(text(), 'no results')]",
                "//div[contains(text(), 'Try different')]",
                "//h2[contains(text(), 'No results')]",
            ]
            
            for xpath in no_results_indicators:
                try:
                    self.driver.find_element(By.XPATH, xpath)
                    return True
                except NoSuchElementException:
                    continue
            
            return False
        except:
            return False
    
    def _extract_first_profile_url(self):
        """Extract URL profil orang pertama dari hasil pencarian"""
        try:
            # Tunggu hasil pencarian muncul
            human_delay(1, 2)
            
            # Berbagai selector untuk mencari link profil
            selectors = [
                # Selector untuk hasil pencarian people
                "//a[contains(@href, '/in/') and contains(@class, 'app-aware-link')]",
                "//a[contains(@href, 'linkedin.com/in/')]",
                # Selector alternatif
                "//span[contains(@class, 'entity-result__title')]//a[contains(@href, '/in/')]",
                "//div[contains(@class, 'entity-result')]//a[contains(@href, '/in/')]",
            ]
            
            for selector in selectors:
                try:
                    # Cari semua link profil
                    profile_links = self.driver.find_elements(By.XPATH, selector)
                    
                    for link in profile_links:
                        href = link.get_attribute('href')
                        
                        if not href:
                            continue
                        
                        # Validasi URL profil
                        if self._is_valid_profile_url(href):
                            # Clean URL (remove query parameters)
                            clean_url = self._clean_profile_url(href)
                            return clean_url
                    
                except NoSuchElementException:
                    continue
            
            return None
            
        except Exception as e:
            print(f"  Error extracting profile URL: {e}")
            return None
    
    def _is_valid_profile_url(self, url):
        """Validasi apakah URL adalah profil LinkedIn yang valid"""
        if not url:
            return False
        
        # Harus mengandung /in/
        if '/in/' not in url:
            return False
        
        # Tidak boleh URL yang tidak diinginkan
        invalid_patterns = [
            '/company/',
            '/school/',
            '/posts/',
            '/feed/',
            '/groups/',
            '/events/',
        ]
        
        for pattern in invalid_patterns:
            if pattern in url:
                return False
        
        return True
    
    def _clean_profile_url(self, url):
        """Clean URL profil (remove query parameters)"""
        try:
            # Split by ? to remove query parameters
            base_url = url.split('?')[0]
            
            # Ensure it starts with https://
            if not base_url.startswith('http'):
                base_url = 'https://www.linkedin.com' + base_url
            
            # Remove trailing slash
            base_url = base_url.rstrip('/')
            
            return base_url
        except:
            return url
    
    def process_json_file(self, input_file, output_file=None):
        """
        Process JSON file berisi array of names dan tambahkan profile_url
        
        Args:
            input_file (str): Path ke input JSON file
            output_file (str): Path ke output JSON file (optional, default: overwrite input)
        """
        try:
            print(f"\n{'='*60}")
            print(f"Processing file: {input_file}")
            print(f"{'='*60}\n")
            
            # Load JSON file
            data = self._load_json(input_file)
            
            if not data:
                print("✗ Failed to load JSON file")
                return
            
            print(f"Found {len(data)} entries to process\n")
            
            # Process setiap entry
            for idx, entry in enumerate(data, 1):
                print(f"\n[{idx}/{len(data)}] Processing entry:")
                
                # Validasi entry memiliki field 'name'
                if 'name' not in entry:
                    print("  ⚠ Skipping: No 'name' field")
                    entry['profile_url'] = None
                    continue
                
                name = entry['name']
                
                # Skip jika sudah ada profile_url
                if 'profile_url' in entry and entry['profile_url']:
                    print(f"  ℹ Already has profile_url: {entry['profile_url']}")
                    continue
                
                # Search profile
                profile_url = self.search_profile(name)
                
                # Tambahkan ke entry
                entry['profile_url'] = profile_url
            
            # Save hasil
            output_path = output_file if output_file else input_file
            self._save_json(data, output_path)
            
            print(f"\n{'='*60}")
            print(f"✓ Processing complete!")
            print(f"  Results saved to: {output_path}")
            print(f"{'='*60}\n")
            
            # Print summary
            self._print_summary(data)
            
        except Exception as e:
            print(f"\n✗ Error processing file: {e}")
            import traceback
            traceback.print_exc()
    
    def _load_json(self, file_path):
        """Load JSON file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validasi data adalah array
            if not isinstance(data, list):
                print("✗ JSON file must contain an array of objects")
                return None
            
            return data
        except FileNotFoundError:
            print(f"✗ File not found: {file_path}")
            return None
        except json.JSONDecodeError as e:
            print(f"✗ Invalid JSON format: {e}")
            return None
        except Exception as e:
            print(f"✗ Error loading file: {e}")
            return None
    
    def _save_json(self, data, file_path):
        """Save data ke JSON file"""
        try:
            # Create directory jika belum ada
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"✓ Saved to: {file_path}")
        except Exception as e:
            print(f"✗ Error saving file: {e}")
    
    def _print_summary(self, data):
        """Print summary hasil processing"""
        total = len(data)
        found = sum(1 for entry in data if entry.get('profile_url'))
        not_found = total - found
        
        print("\nSummary:")
        print(f"  Total entries: {total}")
        print(f"  Found: {found}")
        print(f"  Not found: {not_found}")
        
        if not_found > 0:
            print("\nEntries without LinkedIn URL:")
            for entry in data:
                if not entry.get('profile_url'):
                    print(f"  - {entry.get('name', 'N/A')}")
    
    def close(self):
        """Close browser"""
        try:
            self.driver.quit()
            print("\n✓ Browser closed")
        except:
            pass


def main():
    """Main function - simple queue consumer"""
    import sys
    
    print(f"\n{'='*60}")
    print(f"LINKEDIN SEARCH CRAWLER - QUEUE MODE")
    print(f"{'='*60}")
    print(f"Queue: {SEARCH_QUEUE}")
    print(f"Workers: {MAX_WORKERS}")
    print(f"{'='*60}\n")
    
    # Start queue consumer
    threads = []
    for i in range(MAX_WORKERS):
        worker_id = i + 1
        thread = threading.Thread(
            target=worker_thread,
            args=(worker_id,),
            daemon=True
        )
        thread.start()
        threads.append(thread)
    
    print(f"✓ All {MAX_WORKERS} workers started!")
    print(f"\n💡 Workers will process jobs from queue: {SEARCH_QUEUE}")
    print(f"   Press Ctrl+C to stop\n")
    
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print("\n\n⚠ Stopping workers...")


def send_to_queue(json_file):
    """Send search jobs to RabbitMQ queue"""
    try:
        print(f"\n{'='*60}")
        print(f"SENDING JOBS TO QUEUE: {SEARCH_QUEUE}")
        print(f"{'='*60}\n")
        
        # Load JSON
        print(f"Loading: {json_file}")
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            print("✗ JSON must be an array of objects")
            return
        
        print(f"Found {len(data)} entries\n")
        
        # Connect to RabbitMQ
        rabbitmq = RabbitMQManager()
        rabbitmq.connect()
        rabbitmq.channel.queue_declare(queue=SEARCH_QUEUE, durable=True)
        
        # Send jobs
        sent = 0
        for idx, entry in enumerate(data, 1):
            if 'name' not in entry:
                print(f"[{idx}/{len(data)}] ⚠ Skipping: No 'name' field")
                continue
            
            if entry.get('profile_url'):
                print(f"[{idx}/{len(data)}] ⚠ Skipping: {entry['name']} (already has URL)")
                continue
            
            job = {
                'name': entry['name'],
                'index': idx - 1,
                'source_file': json_file
            }
            
            # Publish to queue
            message = json.dumps(job)
            rabbitmq.channel.basic_publish(
                exchange='',
                routing_key=SEARCH_QUEUE,
                body=message,
                properties=pika.BasicProperties(delivery_mode=2)
            )
            
            sent += 1
            print(f"[{idx}/{len(data)}] ✓ Sent: {entry['name']}")
        
        rabbitmq.close()
        
        print(f"\n{'='*60}")
        print(f"✓ Sent {sent} jobs to queue")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


# Helper script to send jobs
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == '--send':
    if len(sys.argv) < 3:
        print("Usage: python crawler_search.py --send <json_file>")
        sys.exit(1)
    send_to_queue(sys.argv[2])
    sys.exit(0)


def worker_thread(worker_id):
    """Worker thread untuk process jobs dari queue"""
    print(f"[Worker {worker_id}] Starting...")
    
    crawler = None
    rabbitmq = RabbitMQManager()
    stats = {'processed': 0, 'found': 0, 'not_found': 0}
    
    try:
        rabbitmq.connect()
        print(f"[Worker {worker_id}] ✓ Connected to RabbitMQ")
        
        rabbitmq.channel.queue_declare(queue=SEARCH_QUEUE, durable=True)
        rabbitmq.channel.basic_qos(prefetch_count=1)
        
        def callback(ch, method, properties, body):
            nonlocal crawler, stats
            
            try:
                job = json.loads(body)
                name = job.get('name')
                
                print(f"\n[Worker {worker_id}] 📥 Processing: {name}")
                
                # Initialize crawler if needed
                if not crawler:
                    crawler = LinkedInSearchCrawler()
                
                # Search profile
                url = crawler.search_profile(name)
                
                # Update stats
                stats['processed'] += 1
                if url:
                    stats['found'] += 1
                else:
                    stats['not_found'] += 1
                
                print(f"[Worker {worker_id}] ✓ Done: {name}")
                print(f"[Worker {worker_id}] Stats: {stats['found']} found, {stats['not_found']} not found")
                
                # Update source file if specified
                if job.get('source_file') and job.get('index') is not None:
                    update_json_file(job['source_file'], job['index'], url)
                
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
            except Exception as e:
                print(f"[Worker {worker_id}] ✗ Error: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        rabbitmq.channel.basic_consume(
            queue=SEARCH_QUEUE,
            on_message_callback=callback,
            auto_ack=False
        )
        
        print(f"[Worker {worker_id}] ⏳ Waiting for jobs...")
        rabbitmq.channel.start_consuming()
        
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[Worker {worker_id}] ✗ Fatal: {e}")
    finally:
        if crawler:
            crawler.close()
        rabbitmq.close()
        print(f"[Worker {worker_id}] Stopped")


def update_json_file(file_path, index, profile_url):
    """Update JSON file dengan hasil search"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if 0 <= index < len(data):
            data[index]['profile_url'] = profile_url
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  ⚠ Could not update file: {e}")


if __name__ == "__main__":
    import sys
    
    # Check for --send flag
    if len(sys.argv) > 1 and sys.argv[1] == '--send':
        if len(sys.argv) < 3:
            print("Usage: python crawler_search.py --send <json_file>")
            sys.exit(1)
        send_to_queue(sys.argv[2])
    else:
        # Default: run as queue consumer
        main()

"""LinkedIn profile data extractor - Refactored with Helper Modules"""
import time
import random
import os
import json
import re
from pathlib import Path
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from dotenv import load_dotenv
import gender_guesser.detector as gender

# Import helper modules
from helper.browser_helper import (
    create_driver, human_delay, profile_delay, 
    random_mouse_movement, smooth_scroll, scroll_page_to_load
)
from helper.auth_helper import login, save_cookies, load_cookies
from helper.extraction_helper import (
    click_show_all, click_back_arrow, extract_items_from_detail_page
)

# ============================================================================
# MAIN CRAWLER CLASS
# ============================================================================


class LinkedInCrawler:
    def __init__(self):
        """Initialize crawler with browser"""
        self.driver = create_driver()
        self.wait = WebDriverWait(self.driver, 10)
        self.gender_detector = gender.Detector()
        
        # Indonesian name patterns for gender detection fallback - EXPANDED
        self.indonesian_female_indicators = [
            # Common female suffixes
            'dewi', 'sari', 'wati', 'ningsih', 'ning', 'putri', 'ayu', 'ratna', 
            'indah', 'fitri', 'rani', 'maharani', 'rini', 'yanti', 'yani', 'tuti',
            'nita', 'dian', 'ika', 'nia', 'nira', 'lestari', 'utami', 'wulan',
            'kartika', 'permata', 'cahaya', 'anggraini', 'rahayu', 'pratiwi',
            # Additional common female names/patterns
            'sri', 'siti', 'nur', 'nurul', 'mega', 'rina', 'tina', 'lina', 'mira',
            'maya', 'sinta', 'citra', 'puspita', 'melati', 'mawar', 'anisa', 'annisa',
            'fatimah', 'khadijah', 'aisyah', 'zahra', 'zahrah', 'salma', 'laila', 'layla',
            'tiara', 'intan', 'mutiara', 'berlian', 'safira', 'safitri', 'safirah',
            'widya', 'widy', 'retno', 'endah', 'erna', 'yuni', 'yuni', 'yuli',
            'novita', 'vita', 'vina', 'vivi', 'winda', 'windy', 'linda', 'cindy',
            'lia', 'lya', 'lia', 'eka', 'dwi', 'tri', 'catur', 'panca', 'enam',
            'septia', 'okta', 'novia', 'desi', 'dessy', 'desy', 'risa', 'risma',
            'bella', 'nabila', 'nabilla', 'aulia', 'auliya', 'amelia', 'amelya',
            'syifa', 'syifah', 'shifa', 'shifah', 'rahma', 'rahmah', 'rahmi',
            'fika', 'fikri', 'farah', 'farrah', 'fara', 'fira', 'firda', 'firdaus',
            'dina', 'dinah', 'dini', 'dinda', 'dindah', 'diah', 'dyah', 'ajeng',
            'ratu', 'ratih', 'ratih', 'rani', 'raniah', 'rania', 'rania',
            'sinta', 'sintya', 'cynthia', 'cintya', 'cinta', 'cintia'
        ]
        
        self.indonesian_male_indicators = [
            # Common male suffixes/names
            'budi', 'agus', 'adi', 'eko', 'hadi', 'joko', 'bambang', 'sutrisno',
            'wahyu', 'yudi', 'dedi', 'rudi', 'andi', 'hendro', 'teguh', 'putra',
            'wijaya', 'kusuma', 'pramono', 'santoso', 'nugroho',
            # Additional common male names/patterns
            'ahmad', 'muhammad', 'muhamad', 'muh', 'imam', 'umar', 'ali', 'hasan',
            'husein', 'yusuf', 'ibrahim', 'ismail', 'adam', 'idris', 'ilham',
            'rizki', 'rizky', 'riski', 'risky', 'fajar', 'fajri', 'bayu', 'bagus',
            'arif', 'arief', 'arifin', 'irfan', 'irvan', 'iwan', 'ivan', 'iqbal',
            'dimas', 'dimas', 'doni', 'donny', 'dony', 'ferry', 'feri', 'hendra',
            'hendy', 'heri', 'hery', 'harry', 'indra', 'jaya', 'yoga', 'yogi',
            'rama', 'raka', 'reza', 'ridho', 'ridwan', 'rifki', 'rifky', 'rio',
            'sandy', 'sandi', 'satria', 'satrya', 'surya', 'suryo', 'taufik', 'taufiq',
            'wawan', 'wawan', 'willy', 'wily', 'yanto', 'yanto', 'yusuf', 'zaki',
            'zaky', 'zulfikar', 'zulkifli', 'zulkarnain', 'firman', 'firmansyah',
            'andika', 'andhika', 'aditya', 'adithya', 'adiputra', 'adiputra',
            'pratama', 'pramudya', 'prasetyo', 'prasetya', 'prabowo', 'praba',
            'gunawan', 'guntur', 'galih', 'galuh', 'gilang', 'giri', 'gita'
        ]
        
        # Common Indonesian name prefixes that indicate gender
        self.female_prefixes = ['siti', 'sri', 'dewi', 'ratu', 'ajeng', 'dyah', 'diah']
        self.male_prefixes = ['muhammad', 'muhamad', 'muh', 'ahmad', 'imam', 'haji', 'h.']
    
    def login(self):
        """Login to LinkedIn"""
        login(self.driver)
    
    def get_profile(self, url):
        """Main method to scrape a LinkedIn profile"""
        print(f"\nScraping profile: {url}")
        self.driver.get(url)
        
        # Wait for page to load - check if main content exists
        try:
            print("Waiting for page to load...")
            self.wait.until(
                EC.presence_of_element_located((By.TAG_NAME, "main"))
            )
            human_delay(2, 2.5)  # Increased for better initial load
        except TimeoutException:
            print("⚠ Page load timeout! Content may not be available.")
            human_delay(3, 4)  # Wait longer on timeout
        
        # Scroll to load all sections - AGGRESSIVE LOADING
        print("\n" + "="*60)
        print("LOADING ALL CONTENT - AGGRESSIVE SCROLLING")
        print("="*60)
        
        # Get initial height
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        
        # Scroll down multiple times to trigger lazy loading
        for scroll_round in range(3):  # 3 rounds of full page scroll
            print(f"\nScroll round {scroll_round + 1}/3")
            
            # Scroll to bottom in chunks
            current_position = 0
            scroll_step = 800
            
            while current_position < last_height:
                current_position += scroll_step
                self.driver.execute_script(f"window.scrollTo(0, {current_position});")
                human_delay(0.8, 1.2)  # Wait for content to load
            
            # Wait at bottom
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            human_delay(1.5, 2)
            
            # Check if new content loaded
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            print(f"  Height: {last_height} → {new_height}")
            
            if new_height > last_height:
                last_height = new_height
                print(f"  ✓ New content loaded, continuing...")
            else:
                print(f"  ✓ No new content, page fully loaded")
                break
        
        # Scroll back to top
        print("\nScrolling back to top...")
        self.driver.execute_script("window.scrollTo(0, 0);")
        human_delay(1, 1.5)
        
        print("="*60)
        print("CONTENT FULLY LOADED - STARTING EXTRACTION")
        print("="*60)
        
        # Debug: print page info
        print(f"DEBUG - Current URL: {self.driver.current_url}")
        print(f"DEBUG - Page title: {self.driver.title}")
        
        data = {}
        
        print("\n" + "="*60)
        print("EXTRACTING PROFILE DATA")
        print("="*60)
        
        # Add profile URL first
        data['profile_url'] = url
        
        print("\n[1/15] Extracting name...")
        data['name'] = self.extract_name()
        print(f"→ {data['name']}")
        
        print("\n[2/15] Extracting location...")
        data['location'] = self.extract_location()
        print(f"→ {data['location']}")
        
        print("\n[3/15] Extracting about...")
        data['about'] = self.extract_about()
        print(f"→ {len(data['about'])} characters")
        
        print("\n[4/15] Extracting gender (from name + about)...")
        data['gender'] = self.extract_gender_from_name(data['name'], data['about'])
        print(f"→ {data['gender']}")
        
        print("\n[5/15] Extracting experiences...")
        data['experiences'] = self.extract_experiences()
        print(f"→ Found {len(data['experiences'])} experiences")
        
        print("\n[6/15] Extracting education...")
        data['education'] = self.extract_education()
        print(f"→ Found {len(data['education'])} education entries")
        
        print("\n[7/15] Extracting estimated age...")
        data['estimated_age'] = self.estimate_age(data['education'])
        print(f"→ {data['estimated_age']}")
        
        print("\n[8/15] Extracting skills...")
        data['skills'] = self.extract_skills()
        print(f"→ Found {len(data['skills'])} skills")
        
        print("\n[9/15] Extracting projects...")
        data['projects'] = self.extract_projects()
        print(f"→ Found {len(data['projects'])} projects")
        
        print("\n[10/15] Extracting honors & awards...")
        data['honors'] = self.extract_honors()
        print(f"→ Found {len(data['honors'])} honors & awards")
        
        print("\n[11/15] Extracting languages...")
        data['languages'] = self.extract_languages()
        print(f"→ Found {len(data['languages'])} languages")
        
        print("\n[12/15] Extracting licenses & certifications...")
        data['licenses'] = self.extract_licenses()
        print(f"→ Found {len(data['licenses'])} licenses & certifications")
        
        print("\n[13/15] Extracting courses...")
        data['courses'] = self.extract_courses()
        print(f"→ Found {len(data['courses'])} courses")
        
        print("\n[14/15] Extracting volunteering...")
        data['volunteering'] = self.extract_volunteering()
        print(f"→ Found {len(data['volunteering'])} volunteering experiences")
        
        print("\n[15/15] Extracting test scores...")
        data['test_scores'] = self.extract_test_scores()
        print(f"→ Found {len(data['test_scores'])} test scores")
        
        print("\n" + "="*60)
        print("PROFILE EXTRACTION COMPLETE!")
        print("="*60)
        
        return data
    
    def extract_name(self):
        """Extract profile name"""
        selectors = [
            (By.CSS_SELECTOR, "h1.text-heading-xlarge"),
            (By.XPATH, "//h1[contains(@class, 'inline')]"),
            (By.XPATH, "//h1[contains(@class, 'text-heading')]"),
        ]
        
        for by, selector in selectors:
            try:
                element = self.driver.find_element(by, selector)
                name = element.text.strip()
                if name:
                    return name
            except NoSuchElementException:
                continue
        
        # Debug: print page source if name not found
        print("⚠ Name not found! Current URL:", self.driver.current_url)
        print("⚠ Page title:", self.driver.title)
        return "N/A"
    
    def extract_gender(self):
        """Extract gender from pronouns (He/Him, She/Her, They/Them) with name-based fallback"""
        try:
            # Step 1: Try to find pronouns (most accurate)
            pronouns_gender = self._extract_gender_from_pronouns()
            if pronouns_gender != "N/A":
                return pronouns_gender
            
            # Step 2: Fallback to name-based prediction
            print("  No pronouns found, trying name-based prediction...")
            name = self.extract_name()
            if name and name != "N/A":
                predicted_gender = self._predict_gender_from_name(name)
                return predicted_gender
            
            return "Unknown"
        except Exception as e:
            print(f"  Error extracting gender: {e}")
            return "Unknown"
    
    def _extract_gender_from_pronouns(self):
        """Extract gender from pronouns in profile header"""
        try:
            # Pronouns appear next to name in profile header with smaller font
            selectors = [
                (By.XPATH, "//h1[contains(@class, 'text-heading-xlarge')]/..//span[contains(@class, 'text-body-small')]"),
                (By.XPATH, "//h1[contains(@class, 'text-heading-xlarge')]/following-sibling::*//span"),
                (By.XPATH, "//div[.//h1[contains(@class, 'text-heading-xlarge')]]//span[contains(@class, 'text-body-small')]"),
                (By.XPATH, "//main//section[1]//span[contains(@class, 'text-body-small')]"),
            ]
            
            for by, selector in selectors:
                try:
                    elements = self.driver.find_elements(by, selector)
                    
                    for element in elements:
                        text = element.text.strip().lower()
                        
                        # Skip empty or very long text (not pronouns)
                        if not text or len(text) > 20:
                            continue
                        
                        # Check if it contains pronouns pattern
                        if '/' in text:
                            # Map pronouns to gender - more comprehensive patterns
                            # Male patterns: he/him, him/he, he/his, his/he
                            if any(pattern in text for pattern in ['he/him', 'him/he', 'he/his', 'his/he']):
                                print(f"  Found pronouns: {element.text.strip()} → Male")
                                return 'Male'
                            # Female patterns: she/her, her/she, she/hers, hers/she
                            elif any(pattern in text for pattern in ['she/her', 'her/she', 'she/hers', 'hers/she']):
                                print(f"  Found pronouns: {element.text.strip()} → Female")
                                return 'Female'
                            # Non-binary patterns: they/them, them/they
                            elif any(pattern in text for pattern in ['they/them', 'them/they']):
                                print(f"  Found pronouns: {element.text.strip()} → Non-binary")
                                return 'Non-binary'
                    
                except NoSuchElementException:
                    continue
            
            return "N/A"
        except Exception as e:
            print(f"  Error in pronoun extraction: {e}")
            return "N/A"
    
    def extract_gender_from_name(self, full_name, about_text=""):
        """Extract gender from name using multiple fallback methods for better accuracy"""
        if not full_name or full_name == 'N/A':
            return "Unknown"
        
        print(f"  Detecting gender for: '{full_name}'")
        
        # Method 1: Try to extract from pronouns in about text first (most accurate)
        if about_text:
            pronoun_gender = self._extract_gender_from_about_pronouns(about_text)
            if pronoun_gender != "Unknown":
                print(f"  ✓ Gender from pronouns: {pronoun_gender}")
                return pronoun_gender
        
        # Method 2: Try primary name with gender-guesser
        result = self._predict_gender_from_name(full_name)
        if result != "Unknown":
            return result
        
        # Method 3: If unknown and about text is available, try to extract full name from about
        if about_text:
            print("  Primary name unknown, checking about section for full name...")
            import re
            patterns = [
                r'[Nn]ama saya ([A-Z][a-z]+(?: [A-Z][a-z]+)+)',  # "Nama saya Deanira Maharani"
                r'[Mm]y name is ([A-Z][a-z]+(?: [A-Z][a-z]+)+)',  # "My name is John Doe"
                r'[Ss]aya ([A-Z][a-z]+(?: [A-Z][a-z]+)+)',  # "Saya Deanira Maharani"
                r'[Ii]\'m ([A-Z][a-z]+(?: [A-Z][a-z]+)+)',  # "I'm John Doe"
            ]
            
            for pattern in patterns:
                match = re.search(pattern, about_text)
                if match:
                    full_name_from_about = match.group(1)
                    print(f"  Found full name in about: '{full_name_from_about}'")
                    result = self._predict_gender_from_name(full_name_from_about)
                    if result != "Unknown":
                        print(f"  ✓ Gender detected from about text name: {result}")
                        return result
        
        # Method 4: Check for gender keywords in about text
        if about_text:
            keyword_gender = self._extract_gender_from_about_keywords(about_text)
            if keyword_gender != "Unknown":
                print(f"  ✓ Gender from about keywords: {keyword_gender}")
                return keyword_gender
        
        print(f"  ⚠ Could not determine gender, returning Unknown")
        return "Unknown"
    
    def _extract_gender_from_about_pronouns(self, about_text):
        """Extract gender from pronouns in about text (He/Him, She/Her, They/Them)"""
        try:
            about_lower = about_text.lower()
            
            # Check for explicit pronouns - more comprehensive patterns
            # Female patterns
            if any(pattern in about_lower for pattern in ['she/her', 'her/she', 'she/hers', 'hers/she']):
                return 'Female'
            # Male patterns
            if any(pattern in about_lower for pattern in ['he/him', 'him/he', 'he/his', 'his/he']):
                return 'Male'
            # Non-binary patterns
            if any(pattern in about_lower for pattern in ['they/them', 'them/they']):
                return 'Non-binary'
            
            # Check for pronoun usage in sentences
            # Look for patterns like "She is...", "He has...", etc.
            import re
            
            # Female pronouns in context
            female_patterns = [
                r'\bshe\s+(is|has|was|will|can|does)',
                r'\bher\s+(work|experience|passion|goal)',
                r'\bherself\b',
            ]
            
            # Male pronouns in context
            male_patterns = [
                r'\bhe\s+(is|has|was|will|can|does)',
                r'\bhis\s+(work|experience|passion|goal)',
                r'\bhimself\b',
            ]
            
            female_count = sum(1 for pattern in female_patterns if re.search(pattern, about_lower))
            male_count = sum(1 for pattern in male_patterns if re.search(pattern, about_lower))
            
            if female_count > male_count and female_count >= 2:
                return 'Female'
            if male_count > female_count and male_count >= 2:
                return 'Male'
            
            return "Unknown"
        except Exception as e:
            print(f"  Error extracting gender from pronouns: {e}")
            return "Unknown"
    
    def _extract_gender_from_about_keywords(self, about_text):
        """Extract gender from keywords in about text (last resort fallback)"""
        try:
            about_lower = about_text.lower()
            
            # Female indicators
            female_keywords = [
                'wanita', 'perempuan', 'ibu', 'putri', 'gadis',
                'woman', 'female', 'lady', 'girl', 'mother', 'daughter',
                'wife', 'sister', 'ms.', 'mrs.', 'miss'
            ]
            
            # Male indicators
            male_keywords = [
                'pria', 'laki-laki', 'bapak', 'putra', 'cowok',
                'man', 'male', 'gentleman', 'boy', 'father', 'son',
                'husband', 'brother', 'mr.'
            ]
            
            female_count = sum(1 for keyword in female_keywords if keyword in about_lower)
            male_count = sum(1 for keyword in male_keywords if keyword in about_lower)
            
            if female_count > male_count and female_count > 0:
                return 'Female'
            if male_count > female_count and male_count > 0:
                return 'Male'
            
            return "Unknown"
        except Exception as e:
            print(f"  Error extracting gender from keywords: {e}")
            return "Unknown"
    
    def _predict_gender_from_name(self, full_name):
        """Predict gender from name using gender-guesser library with Indonesian name fallback"""
        try:
            # Clean and extract first name
            # Handle cases like "Sri.Mah Gunawan" → try "Sri", "Mah", "Gunawan"
            name_parts = full_name.replace('.', ' ').replace(',', ' ').split()
            
            if not name_parts:
                return "Unknown"
            
            # PRIORITY 1: Check Indonesian name prefixes (most reliable)
            first_name_lower = name_parts[0].lower()
            for prefix in self.female_prefixes:
                if first_name_lower == prefix or first_name_lower.startswith(prefix):
                    print(f"  Indonesian prefix match: '{name_parts[0]}' starts with '{prefix}' → Female")
                    return 'Female'
            
            for prefix in self.male_prefixes:
                if first_name_lower == prefix or first_name_lower.startswith(prefix):
                    print(f"  Indonesian prefix match: '{name_parts[0]}' starts with '{prefix}' → Male")
                    return 'Male'
            
            # PRIORITY 2: Check exact match Indonesian patterns FIRST (before gender-guesser)
            # This prevents false positives from gender-guesser
            print("  Checking Indonesian exact matches...")
            for idx, name_part in enumerate(name_parts):
                name_lower = name_part.lower()
                
                # Exact match female indicators (highest priority)
                if name_lower in self.indonesian_female_indicators:
                    print(f"  Indonesian exact match: '{name_part}' → Female")
                    return 'Female'
            
            # Check male indicators only if no female match found
            for idx, name_part in enumerate(name_parts):
                name_lower = name_part.lower()
                
                if name_lower in self.indonesian_male_indicators:
                    print(f"  Indonesian exact match: '{name_part}' → Male")
                    return 'Male'
            
            # PRIORITY 3: Try gender-guesser library on each name part
            print("  Trying gender-guesser library...")
            for idx, name_part in enumerate(name_parts):
                result = self.gender_detector.get_gender(name_part)
                
                # gender-guesser returns: male, female, mostly_male, mostly_female, andy (androgynous), unknown
                if result in ['male', 'mostly_male']:
                    print(f"  Name prediction: '{name_part}' (part {idx+1}) → Male (confidence: {result})")
                    return 'Male'
                elif result in ['female', 'mostly_female']:
                    print(f"  Name prediction: '{name_part}' (part {idx+1}) → Female (confidence: {result})")
                    return 'Female'
                elif result == 'andy':
                    print(f"  Name prediction: '{name_part}' (part {idx+1}) → Ambiguous")
                    # Continue to next name part
                    continue
                else:
                    # Unknown, try next part
                    continue
            
            # PRIORITY 4: Try with lowercase (some names work better in lowercase)
            print("  Trying lowercase variants...")
            for idx, name_part in enumerate(name_parts):
                result = self.gender_detector.get_gender(name_part.lower())
                
                if result in ['male', 'mostly_male']:
                    print(f"  Name prediction: '{name_part.lower()}' (part {idx+1}, lowercase) → Male (confidence: {result})")
                    return 'Male'
                elif result in ['female', 'mostly_female']:
                    print(f"  Name prediction: '{name_part.lower()}' (part {idx+1}, lowercase) → Female (confidence: {result})")
                    return 'Female'
            
            # PRIORITY 5: Check suffix/contains Indonesian patterns (less reliable)
            print("  Trying Indonesian suffix/contains patterns...")
            
            # Check female patterns first (prioritize female)
            for idx, name_part in enumerate(name_parts):
                name_lower = name_part.lower()
                
                # Check if name ends with or contains female indicators
                for indicator in self.indonesian_female_indicators:
                    if name_lower.endswith(indicator) or (len(indicator) > 3 and indicator in name_lower):
                        print(f"  Indonesian pattern match: '{name_part}' contains/ends with '{indicator}' → Female")
                        return 'Female'
            
            # Then check male patterns
            for idx, name_part in enumerate(name_parts):
                name_lower = name_part.lower()
                
                # Check if name ends with or contains male indicators
                for indicator in self.indonesian_male_indicators:
                    if name_lower.endswith(indicator) or (len(indicator) > 3 and indicator in name_lower):
                        print(f"  Indonesian pattern match: '{name_part}' contains/ends with '{indicator}' → Male")
                        return 'Male'
            
            print(f"  All methods exhausted, cannot determine gender from name: {full_name}")
            return 'Unknown'
        
        except Exception as e:
            print(f"  Error in name-based prediction: {e}")
            return "Unknown"
    
    def extract_location(self):
        """Extract location (city) from profile header"""
        try:
            # Location is usually in the profile header section
            # Format: "Bandung, West Java, Indonesia"
            selectors = [
                (By.XPATH, "//div[contains(@class, 'mt2')]//span[contains(@class, 'text-body-small') and contains(., ',')]"),
                (By.XPATH, "//span[contains(@class, 'text-body-small') and contains(., 'Indonesia') or contains(., 'Jakarta') or contains(., 'Bandung') or contains(., 'Surabaya')]"),
                (By.CSS_SELECTOR, "div.mt2 span.text-body-small"),
            ]
            
            for by, selector in selectors:
                try:
                    element = self.driver.find_element(by, selector)
                    location_text = element.text.strip()
                    
                    # Skip if it's not a location (e.g., pronouns, contact info)
                    if not location_text or len(location_text) < 3:
                        continue
                    
                    # Skip if it looks like pronouns
                    if '/' in location_text:
                        continue
                    
                    # Extract city (first part before comma)
                    if ',' in location_text:
                        city = location_text.split(',')[0].strip()
                        return city
                    else:
                        return location_text
                    
                except NoSuchElementException:
                    continue
            
            return "N/A"
        except Exception as e:
            print(f"  Error extracting location: {e}")
            return "N/A"
    
    def estimate_age(self, education_data):
        """Estimate age from education graduation years"""
        try:
            if not education_data or len(education_data) == 0:
                return "Unknown"
            
            current_year = datetime.now().year
            graduation_years = []
            
            # Extract graduation years from education
            for edu in education_data:
                if not isinstance(edu, dict):
                    continue
                
                year_str = edu.get('year', '')
                if not year_str or year_str == 'N/A':
                    continue
                
                # Extract year number (handle "2020", "2018 - 2020", etc)
                year_match = re.findall(r'\d{4}', year_str)
                if year_match:
                    # Get the latest year (graduation year)
                    year = int(year_match[-1])
                    graduation_years.append({
                        'year': year,
                        'degree': edu.get('degree', '').lower(),
                        'school': edu.get('school', '')
                    })
            
            if not graduation_years:
                return "Unknown"
            
            # Sort by year (most recent first)
            graduation_years.sort(key=lambda x: x['year'], reverse=True)
            
            # Use the most recent graduation to estimate age
            latest_grad = graduation_years[0]
            grad_year = latest_grad['year']
            degree = latest_grad['degree']
            
            # Estimate graduation age based on degree level
            # High School: ~18 years old
            # Bachelor/S1: ~22 years old
            # Master/S2: ~24 years old
            # Doctoral/PhD/S3: ~27 years old
            
            if any(keyword in degree for keyword in ['high school', 'sma', 'smk', 'smu']):
                graduation_age = 18
            elif any(keyword in degree for keyword in ['master', 's2', 'magister', 'mba']):
                graduation_age = 24
            elif any(keyword in degree for keyword in ['doctor', 'phd', 's3', 'doctoral']):
                graduation_age = 27
            elif any(keyword in degree for keyword in ['bachelor', 's1', 'sarjana', 'degree']):
                graduation_age = 22
            elif any(keyword in degree for keyword in ['diploma', 'd3', 'd4']):
                graduation_age = 21
            else:
                # Default to bachelor's age if degree type unclear
                graduation_age = 22
            
            # Calculate estimated current age
            estimated_age = (current_year - grad_year) + graduation_age
            
            # Sanity check: age should be between 18-70
            if estimated_age < 18 or estimated_age > 70:
                print(f"  Age estimation out of range: {estimated_age} (grad year: {grad_year}, degree: {degree})")
                return "Unknown"
            
            # Return age range (±2 years for uncertainty)
            age_min = max(18, estimated_age - 2)
            age_max = min(70, estimated_age + 2)
            
            print(f"  Estimated from {degree} graduation ({grad_year}): ~{estimated_age} years old (range: {age_min}-{age_max})")
            
            return {
                'estimated_age': estimated_age,
                'age_range': f"{age_min}-{age_max}",
                'based_on': f"{degree} graduation in {grad_year}"
            }
        
        except Exception as e:
            print(f"  Error estimating age: {e}")
            return "Unknown"
    
    def extract_about(self):
        """Extract about section"""
        try:
            about_section = self.driver.find_element(
                By.XPATH, 
                "//section[contains(@id, 'about') or .//h2[contains(., 'About')]]"
            )
            
            smooth_scroll(self.driver, about_section)
            
            # Click see more if exists
            try:
                see_more = about_section.find_element(By.XPATH, ".//button[contains(., 'more')]")
                see_more.click()
                human_delay(0.5, 0.8)
            except:
                pass
            
            text_selectors = [
                ".//div[contains(@class, 'display-flex')]//span[@aria-hidden='true']",
                ".//div[contains(@class, 'inline-show-more-text')]//span",
                ".//span[@aria-hidden='true']",
            ]
            
            for selector in text_selectors:
                try:
                    text_element = about_section.find_element(By.XPATH, selector)
                    text = text_element.text.strip()
                    if text and len(text) > 20:
                        return text
                except NoSuchElementException:
                    continue
            
            return "N/A"
        except Exception:
            return "N/A"
    
    def extract_experiences(self):
        """Extract experience section with show all flow"""
        experiences = []
        try:
            print("Looking for experience section...")
            
            # Find section
            exp_section = None
            selectors = [
                "//section[contains(@id, 'experience')]",
                "//section[.//div[@id='experience']]",
                "//section[.//h2[contains(text(), 'Experience')]]",
            ]
            
            for selector in selectors:
                try:
                    exp_section = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    print("✓ Found section")
                    break
                except TimeoutException:
                    continue
            
            if not exp_section:
                print("⚠ Experience section not found")
                return experiences
            
            # Click "Show all"
            clicked = click_show_all(self.driver, exp_section)
            
            if clicked:
                # Extract from detail page
                items = extract_items_from_detail_page(self.driver)
                print(f"Processing {len(items)} items...")
                
                for idx, item in enumerate(items):
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 20:
                            continue
                        
                        print(f"\n  === Item {idx + 1}/{len(items)} ===")
                        print(f"  Raw text length: {len(text)} chars")
                        print(f"  First 200 chars: {text[:200]}...")
                        
                        # Skip nested items (Skills:, etc)
                        if text.startswith('Skills:') or text.startswith('Skill'):
                            print(f"  → SKIP: Nested skills item")
                            continue
                        
                        # Skip if it's just a certificate/training line
                        if text.startswith('Certificate') or text.startswith('Training'):
                            print(f"  → SKIP: Certificate/Training item")
                            continue
                        
                        # Must have company indicator OR be a valid experience format
                        # Some experiences don't have · in first line if it's just title
                        
                        # Split by newlines and remove duplicates (LinkedIn has duplicate lines)
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        
                        # Remove consecutive duplicates
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        print(f"  Total unique lines: {len(lines)}")
                        for i, line in enumerate(lines[:12]):  # Show first 12
                            print(f"    [{i}] {line[:100]}")
                        
                        # LinkedIn structure after deduplication:
                        # 0: Title
                        # 1: Company (with or without · Type)
                        # 2: Date range (e.g., "Aug 2024 - Present · 6 mos")
                        # 3: Date range again (e.g., "Aug 2024 to Present · 6 mos") 
                        # 4: Location (if exists)
                        # 5+: Description/Skills/Certificate (skip these)
                        
                        if len(lines) >= 3:
                            # Check if line 1 looks like a company (has · or is just company name)
                            # Check if line 2 looks like duration (has date or "Present")
                            line1_is_company = True  # Assume line 1 is company
                            line2_is_duration = (
                                '-' in lines[2] or 
                                'Present' in lines[2] or 
                                'to' in lines[2].lower() or
                                any(month in lines[2] for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
                            )
                            
                            if not line2_is_duration:
                                print(f"  → SKIP: Line 2 doesn't look like duration: {lines[2][:50]}")
                                continue
                            
                            # Find location: it's after the duplicate date line
                            location = ""
                            if len(lines) > 4:
                                potential_location = lines[4]
                                # Location is short and doesn't look like description or certificate
                                is_location = (
                                    len(potential_location) < 100 and
                                    ' to ' not in potential_location and
                                    'http' not in potential_location.lower() and
                                    'www.' not in potential_location.lower() and
                                    not potential_location.startswith('Certificate') and
                                    not potential_location.startswith('Training') and
                                    not (len(potential_location) > 50 and ' is ' in potential_location)
                                )
                                
                                if is_location:
                                    location = potential_location
                            
                            exp_data = {
                                'title': lines[0],
                                'company': lines[1],
                                'duration': lines[2],
                                'location': location
                            }
                            
                            experiences.append(exp_data)
                            print(f"  ✓ ADDED {len(experiences)}. {exp_data['title']} at {exp_data['company'][:50]}")
                        else:
                            print(f"  → SKIP: Not enough lines ({len(lines)})")
                    
                    except Exception as e:
                        print(f"  Error parsing item {idx}: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                
                # Click back
                click_back_arrow(self.driver)
            
            else:
                # No "Show all" button - extract from main page
                print("  Extracting from main page...")
                items = exp_section.find_elements(By.XPATH, ".//ul/li")
                print(f"  Found {len(items)} items on main page")
                
                for idx, item in enumerate(items):
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 20:
                            continue
                        
                        print(f"\n  === Item {idx + 1}/{len(items)} ===")
                        
                        # Check if this is a GROUPED experience (multiple roles at same company)
                        # Pattern: Company name first (no ·), then multiple roles with ·
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        print(f"  Lines: {len(lines)}")
                        for i, line in enumerate(lines[:8]):
                            print(f"    [{i}] {line[:80]}")
                        
                        # Detect grouped: 
                        # Grouped = Line 0 is company (no ·), Line 1 has "Full-time · X yrs X mos" (total duration with time), Line 2 is location, Line 3+ are roles
                        # Normal = Line 0 is title (no ·), Line 1 is "Company · Full-time" (company with type, NO duration), Line 2 is duration
                        is_grouped = False
                        if len(lines) >= 4 and '·' not in lines[0]:
                            # Key difference: Grouped has duration (yr/mo) in line 1, Single doesn't
                            # Grouped line 1: "Full-time · 3 yrs 9 mos"
                            # Single line 1: "PT Bank Mandiri · Full-time" (no yr/mo)
                            line1_has_duration = ('yr' in lines[1] or 'mo' in lines[1])
                            
                            # Also check that line 3 looks like a role title (not a date)
                            line3_is_role = (
                                len(lines) > 3 and
                                '-' not in lines[3] and  # Not a date range
                                'Present' not in lines[3] and
                                not any(month in lines[3] for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
                            )
                            
                            if line1_has_duration and line3_is_role:
                                # Line 0 = Company, Line 1 = Total duration, Line 2 = Location, Line 3+ = Roles
                                is_grouped = True
                        
                        if is_grouped:
                            print(f"  → GROUPED experience detected")
                            # Handle grouped: multiple roles at same company
                            # Structure: Company, Total Duration, Location, Role1 Title, Role1 Duration, Role1 Duration Dup, Role2 Title...
                            
                            company = lines[0]
                            company_location = lines[2] if len(lines) > 2 else ""
                            
                            # Parse roles starting from line 3
                            i = 3
                            while i < len(lines):
                                # Each role: Title, Duration, Duration Dup (skip)
                                if i >= len(lines):
                                    break
                                
                                role_title = lines[i]
                                
                                # Skip if this looks like a certificate or skills line
                                if role_title.startswith('Certificate') or role_title.startswith('Skills:'):
                                    i += 1
                                    continue
                                
                                # Check if next line is duration (has - or Present)
                                if i + 1 < len(lines) and ('-' in lines[i + 1] or 'Present' in lines[i + 1]):
                                    role_duration = lines[i + 1]
                                    
                                    # Add this role as separate experience
                                    exp_data = {
                                        'title': role_title,
                                        'company': company,
                                        'duration': role_duration,
                                        'location': company_location
                                    }
                                    experiences.append(exp_data)
                                    print(f"  ✓ ADDED {len(experiences)}. {exp_data['title']} at {company}")
                                    
                                    # Skip duplicate duration line (line i+2) and move to next role
                                    i += 3
                                else:
                                    # Not a valid role, skip
                                    i += 1
                            
                            continue
                        
                        # Normal single experience
                        # Line 0 = Title, Line 1 = Company (has ·), Line 2 = Duration, Line 3 = Duration dup, Line 4 = Location
                        if len(lines) >= 3:
                            # Check if line 1 has company indicator (· for employment type or just company name)
                            # Check if line 2 looks like duration
                            line2_is_duration = (
                                '-' in lines[2] or 
                                'Present' in lines[2] or 
                                'to' in lines[2].lower() or
                                any(month in lines[2] for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
                            )
                            
                            if line2_is_duration:
                                location = ""
                                # Location is at line 4 (after duplicate duration at line 3)
                                if len(lines) > 4:
                                    potential_location = lines[4]
                                    is_location = (
                                        len(potential_location) < 100 and
                                        ' to ' not in potential_location and
                                        'http' not in potential_location.lower() and
                                        'www.' not in potential_location.lower() and
                                        not potential_location.startswith('Certificate') and
                                        not potential_location.startswith('Skills:') and
                                        not (len(potential_location) > 50 and ' is ' in potential_location)
                                    )
                                    if is_location:
                                        location = potential_location
                                
                                exp_data = {
                                    'title': lines[0],
                                    'company': lines[1],
                                    'duration': lines[2],
                                    'location': location
                                }
                                experiences.append(exp_data)
                                print(f"  ✓ ADDED {len(experiences)}. {exp_data['title']} at {exp_data['company'][:50]}")
                            else:
                                print(f"  → SKIP: Line 2 doesn't look like duration: {lines[2][:50]}")
                        else:
                            print(f"  → SKIP: Not enough lines ({len(lines)})")
                    
                    except Exception as e:
                        print(f"  Error: {e}")
                        continue
        
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        
        return experiences
    
    def extract_education(self):
        """Extract education section with show all flow"""
        education = []
        try:
            print("Looking for education section...")
            
            edu_section = None
            selectors = [
                "//section[contains(@id, 'education')]",
                "//section[.//div[@id='education']]",
                "//section[.//h2[contains(text(), 'Education')]]",
            ]
            
            for selector in selectors:
                try:
                    edu_section = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    print("✓ Found section")
                    break
                except TimeoutException:
                    continue
            
            if not edu_section:
                print("⚠ Education section not found")
                return education
            
            # Click "Show all"
            clicked = click_show_all(self.driver, edu_section)
            
            if clicked:
                items = extract_items_from_detail_page(self.driver)
                
                for item in items:
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 5:
                            continue
                        
                        # Remove consecutive duplicates
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        print(f"  Education item lines: {len(lines)}")
                        for i, line in enumerate(lines[:6]):
                            print(f"    {i}: {line[:80]}")
                        
                        # Skip if it's "Activities and societies" or "...see more"
                        if lines[0].startswith('Activities and societies') or lines[0] == '…see more':
                            print(f"  → SKIP: Activities/see more line")
                            continue
                        
                        # LinkedIn structure after deduplication varies:
                        # Sometimes: School, School (dup), Degree, Year
                        # Sometimes: School, Degree, Year
                        # Need to detect which format
                        
                        if len(lines) >= 2:
                            school = lines[0]
                            degree = ""
                            year = ""
                            
                            # Check if line 1 is duplicate of line 0
                            if len(lines) > 1 and lines[1] == lines[0]:
                                # Format: School, School, Degree, Year
                                degree = lines[2] if len(lines) > 2 else ""
                                year_line = lines[3] if len(lines) > 3 else ""
                            else:
                                # Format: School, Degree, Year
                                degree = lines[1] if len(lines) > 1 else ""
                                year_line = lines[2] if len(lines) > 2 else ""
                            
                            # Extract just the end year from year range
                            if year_line:
                                if '-' in year_line or '–' in year_line:
                                    # Split by dash and get last part
                                    parts = year_line.replace('–', '-').split('-')
                                    year = parts[-1].strip()
                                else:
                                    year = year_line.strip()
                            
                            edu_data = {
                                'school': school,
                                'degree': degree,
                                'year': year
                            }
                            education.append(edu_data)
                            print(f"  ✓ {len(education)}. {edu_data['school']}")
                    except Exception as e:
                        print(f"  Error parsing education: {e}")
                        continue
                
                click_back_arrow(self.driver)
            else:
                # No show all, extract from main page
                print("  Extracting from main page...")
                items = edu_section.find_elements(By.XPATH, ".//ul/li")
                
                for item in items:
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 5:
                            continue
                        
                        # Remove consecutive duplicates
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        print(f"  Education lines ({len(lines)}):")
                        for i, line in enumerate(lines[:6]):
                            print(f"    [{i}] {line[:80]}")
                        
                        # Skip if it's "Activities and societies" or "...see more"
                        if lines[0].startswith('Activities and societies') or lines[0] == '…see more':
                            print(f"  → SKIP: Activities/see more line")
                            continue
                        
                        if len(lines) >= 2:
                            school = lines[0]
                            degree = ""
                            year = ""
                            
                            # Check if line 1 is duplicate of line 0
                            if len(lines) > 1 and lines[1] == lines[0]:
                                # Format: School, School, Degree, Year
                                degree = lines[2] if len(lines) > 2 else ""
                                year_line = lines[3] if len(lines) > 3 else ""
                            else:
                                # Format: School, Degree, Year
                                degree = lines[1] if len(lines) > 1 else ""
                                year_line = lines[2] if len(lines) > 2 else ""
                            
                            # Extract just the end year from year range
                            if year_line:
                                if '-' in year_line or '–' in year_line:
                                    # Split by dash and get last part
                                    parts = year_line.replace('–', '-').split('-')
                                    year = parts[-1].strip()
                                else:
                                    year = year_line.strip()
                            
                            edu_data = {
                                'school': school,
                                'degree': degree,
                                'year': year
                            }
                            education.append(edu_data)
                            print(f"  ✓ {len(education)}. {edu_data['school']}")
                    except Exception as e:
                        print(f"  Error: {e}")
                        continue
        
        except Exception as e:
            print(f"Error: {e}")
        
        return education
    
    def extract_skills(self):
        """Extract skills section with details"""
        skills = []
        try:
            print("Looking for skills section...")
            
            skills_section = None
            selectors = [
                "//section[contains(@id, 'skills')]",
                "//section[.//div[@id='skills']]",
                "//section[.//h2[contains(text(), 'Skills')]]",
            ]
            
            for selector in selectors:
                try:
                    skills_section = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    print("✓ Found section")
                    break
                except TimeoutException:
                    continue
            
            if not skills_section:
                print("⚠ Skills section not found")
                return skills
            
            # Click "Show all skills"
            clicked = click_show_all(self.driver, skills_section)
            
            if clicked:
                items = extract_items_from_detail_page(self.driver)
                print(f"Found {len(items)} skill items")
                
                for idx, item in enumerate(items):
                    try:
                        # Get skill name from first span
                        skill_spans = item.find_elements(By.XPATH, ".//span[@aria-hidden='true']")
                        
                        if not skill_spans:
                            continue
                        
                        skill_name = skill_spans[0].text.strip()
                        
                        if not skill_name:
                            continue
                        
                        # Filter junk
                        skip_if_contains = [
                            'Passed LinkedIn', 
                            'LinkedIn Skill Assessment',
                            ' endorsement',      # "6 endorsements", "1 endorsement"
                        ]
                        skip_if_starts_with = ['Show ', 'See ']
                        
                        # Additional check: skip if it's experience/endorsement count pattern
                        # Pattern: starts with number + "experience" or "endorsement"
                        is_count_pattern = False
                        if skill_name and len(skill_name) > 0:
                            first_word = skill_name.split()[0] if ' ' in skill_name else skill_name
                            if first_word.isdigit() and ('experience' in skill_name.lower() or 'endorsement' in skill_name.lower()):
                                is_count_pattern = True
                        
                        # Skip if it's a job title (contains " at ")
                        is_job_title = ' at ' in skill_name and len(skill_name) > 30
                        
                        should_skip = (
                            any(pattern in skill_name for pattern in skip_if_contains) or
                            any(skill_name.startswith(pattern) for pattern in skip_if_starts_with) or
                            len(skill_name) > 100 or
                            is_count_pattern or
                            is_job_title
                        )
                        
                        if should_skip:
                            print(f"  [{idx+1}] Skip: {skill_name[:60]}")
                            continue
                        
                        print(f"\n  [{idx+1}] Processing: {skill_name}")
                        
                        details = []
                        
                        # Step 1: Extract details yang langsung tampil (tanpa click)
                        # Details ada di nested <ul> setelah skill name, tapi bukan endorsement count
                        try:
                            # Ambil semua text lines dari item
                            item_text = item.text.strip()
                            if item_text:
                                lines = [l.strip() for l in item_text.split('\n') if l.strip()]
                                
                                # Remove consecutive duplicates
                                unique_lines = []
                                prev = None
                                for line in lines:
                                    if line != prev:
                                        unique_lines.append(line)
                                        prev = line
                                
                                # Line 0 = skill name
                                # Lines after that could be details or endorsement counts
                                # Filter: skip endorsements, experiences count, skill name itself
                                for line in unique_lines[1:]:  # Skip first line (skill name)
                                    # Skip if it's endorsement/experience count
                                    if 'endorsement' in line.lower():
                                        continue
                                    if 'experience' in line.lower() and ' at ' in line:
                                        # "2 experiences at Company" is not a real detail
                                        continue
                                    # Skip Passed LinkedIn badge
                                    if 'Passed LinkedIn' in line or 'LinkedIn Skill Assessment' in line:
                                        continue
                                    # Skip if it's the skill name again
                                    if line == skill_name:
                                        continue
                                    # Skip if too short
                                    if len(line) < 5:
                                        continue
                                    
                                    # This is a valid detail
                                    if line not in details:
                                        details.append(line)
                                        print(f"      • {line[:60]}")
                        except Exception as e:
                            print(f"    Error extracting visible details: {e}")
                        
                        # Step 2: Check if there's "Show all X details" button
                        try:
                            show_details_btn = item.find_element(By.XPATH, 
                                ".//button[contains(., 'Show all') and contains(., 'detail')] | " +
                                ".//a[contains(., 'Show all') and contains(., 'detail')]"
                            )
                            
                            if show_details_btn:
                                print(f"    → Found 'Show all details' button")
                                
                                # Scroll to button
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", show_details_btn)
                                human_delay(0.3, 0.5)
                                
                                # Click to open modal
                                self.driver.execute_script("arguments[0].click();", show_details_btn)
                                print(f"    → Clicked 'Show all details'")
                                human_delay(0.8, 1.2)
                                
                                # Extract details from modal
                                modal_items = self.driver.find_elements(By.XPATH, 
                                    "//div[contains(@role, 'dialog')]//ul/li | " +
                                    "//div[@data-test-modal]//ul/li | " +
                                    "//div[contains(@class, 'artdeco-modal')]//ul/li"
                                )
                                
                                if modal_items:
                                    print(f"    → Found {len(modal_items)} detail items in modal")
                                    # Clear previous details, use modal data instead
                                    details = []
                                    for modal_item in modal_items:
                                        detail_text = modal_item.text.strip()
                                        if detail_text and len(detail_text) > 5:
                                            # Get first line only (title/name)
                                            first_line = detail_text.split('\n')[0].strip()
                                            if first_line and first_line not in details:
                                                details.append(first_line)
                                                print(f"      • {first_line[:60]}")
                                else:
                                    print(f"    → No detail items found in modal")
                                
                                # Close modal - click X button
                                close_selectors = [
                                    "//button[@aria-label='Dismiss']",
                                    "//button[contains(@aria-label, 'Close')]",
                                    "//button[contains(@class, 'artdeco-modal__dismiss')]",
                                    "//button[@data-test-modal-close-btn]",
                                ]
                                
                                for close_selector in close_selectors:
                                    try:
                                        close_btn = self.driver.find_element(By.XPATH, close_selector)
                                        self.driver.execute_script("arguments[0].click();", close_btn)
                                        print(f"    → Closed modal")
                                        human_delay(0.3, 0.5)
                                        break
                                    except:
                                        continue
                        
                        except NoSuchElementException:
                            # No "Show all details" button - use details from step 1
                            if details:
                                print(f"    → No 'Show all details' button, using visible details")
                            else:
                                print(f"    → No details available")
                        
                        # Add skill with details
                        skill_data = {
                            "name": skill_name,
                            "details": details
                        }
                        skills.append(skill_data)
                        print(f"  ✓ Added: {skill_name} ({len(details)} details)")
                        
                    except Exception as e:
                        print(f"  Error processing skill {idx+1}: {e}")
                        continue
                
                # Click back arrow to return to profile (once at the end)
                click_back_arrow(self.driver)
            
            else:
                # No "Show all skills" button - extract from main page (simplified)
                print("  No 'Show all' button, extracting from main page...")
                items = skills_section.find_elements(By.XPATH, ".//ul/li")
                
                for item in items:
                    try:
                        skill_spans = item.find_elements(By.XPATH, ".//span[@aria-hidden='true']")
                        if skill_spans:
                            skill_name = skill_spans[0].text.strip()
                            if skill_name and len(skill_name) < 100:
                                skill_data = {
                                    "name": skill_name,
                                    "details": []
                                }
                                skills.append(skill_data)
                                print(f"✓ {len(skills)}. {skill_name}")
                    except:
                        continue
        
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        
        return skills
    
    def extract_projects(self):
        """Extract projects section with show all flow"""
        projects = []
        try:
            print("Looking for projects section...")
            
            proj_section = None
            selectors = [
                "//section[contains(@id, 'projects')]",
                "//section[.//div[@id='projects']]",
                "//section[.//h2[contains(text(), 'Projects')]]",
            ]
            
            for selector in selectors:
                try:
                    proj_section = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    print("✓ Found section")
                    break
                except TimeoutException:
                    continue
            
            if not proj_section:
                print("⚠ Projects section not found")
                return projects
            
            # Click "Show all"
            clicked = click_show_all(self.driver, proj_section)
            
            if clicked:
                items = extract_items_from_detail_page(self.driver)
                
                for item in items:
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 10:
                            continue
                        
                        # Remove consecutive duplicates
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        print(f"  Project item lines: {len(lines)}")
                        for i, line in enumerate(lines[:8]):
                            print(f"    [{i}] {line[:80]}")
                        
                        # Structure after deduplication:
                        # 0: Title
                        # 1: Duration
                        # 2: Associated with Company (skip this)
                        # 3: "Show project" link (skip this)
                        # 4+: Detail/Description
                        
                        if len(lines) >= 2:
                            title = lines[0]
                            duration = lines[1]
                            detail = ""
                            
                            # Find detail: skip "Associated with", "Show project", "Other contributors"
                            for line in lines[2:]:
                                if 'Associated with' in line:
                                    continue
                                if 'Show project' in line:
                                    continue
                                if 'Other contributors' in line:
                                    break  # Stop here, rest is contributor info
                                
                                # This is the detail/description
                                if len(line) > 10:
                                    detail = line
                                    break
                            
                            proj_data = {
                                'title': title,
                                'duration': duration,
                                'detail': detail
                            }
                            projects.append(proj_data)
                            print(f"  ✓ {len(projects)}. {proj_data['title']}")
                    except Exception as e:
                        print(f"  Error parsing project: {e}")
                        continue
                
                click_back_arrow(self.driver)
            else:
                # No show all, extract from main page
                print("  Extracting from main page...")
                items = proj_section.find_elements(By.XPATH, ".//ul/li")
                
                for item in items:
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 10:
                            continue
                        
                        # Remove consecutive duplicates
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        if len(lines) >= 2:
                            title = lines[0]
                            duration = lines[1]
                            detail = ""
                            
                            for line in lines[2:]:
                                if 'Associated with' in line or 'Show project' in line:
                                    continue
                                if 'Other contributors' in line:
                                    break
                                if len(line) > 10:
                                    detail = line
                                    break
                            
                            proj_data = {
                                'title': title,
                                'duration': duration,
                                'detail': detail
                            }
                            projects.append(proj_data)
                            print(f"  ✓ {len(projects)}. {proj_data['title']}")
                    except Exception as e:
                        print(f"  Error: {e}")
                        continue
        
        except Exception as e:
            print(f"Error: {e}")
        
        return projects
    
    def extract_honors(self):
        """Extract honors & awards section with show all flow"""
        honors = []
        try:
            print("Looking for honors & awards section...")
            
            honors_section = None
            selectors = [
                "//section[contains(@id, 'honors')]",
                "//section[contains(@id, 'accomplishments')]",
                "//section[.//div[@id='honors']]",
                "//section[.//div[@id='accomplishments']]",
                "//section[.//h2[contains(text(), 'Honors')]]",
                "//section[.//h2[contains(text(), 'awards')]]",
                "//section[.//span[contains(text(), 'Honors & awards')]]",
            ]
            
            for selector in selectors:
                try:
                    honors_section = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    print("✓ Found section")
                    break
                except TimeoutException:
                    continue
            
            if not honors_section:
                print("⚠ Honors & awards section not found")
                return honors
            
            # Click "Show all"
            clicked = click_show_all(self.driver, honors_section)
            
            if clicked:
                items = extract_items_from_detail_page(self.driver)
                
                for item in items:
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 10:
                            continue
                        
                        # Remove consecutive duplicates
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        print(f"  Honor item lines: {len(lines)}")
                        for i, line in enumerate(lines[:4]):
                            print(f"    [{i}] {line[:80]}")
                        
                        # Structure:
                        # 0: Title
                        # 1: "Issued by X · Date" (need to split by ·)
                        
                        if len(lines) >= 2:
                            title = lines[0]
                            issued_line = lines[1]
                            
                            # Split "Issued by X · Date" by ·
                            issued_by = ""
                            year = ""
                            
                            if '·' in issued_line:
                                parts = issued_line.split('·')
                                issued_by = parts[0].strip()
                                year = parts[1].strip() if len(parts) > 1 else ""
                                
                                # Remove "Issued by " prefix
                                if issued_by.startswith('Issued by '):
                                    issued_by = issued_by.replace('Issued by ', '', 1)
                            else:
                                # No ·, whole line is issued_by
                                issued_by = issued_line.replace('Issued by ', '', 1)
                            
                            honor_data = {
                                'title': title,
                                'issued_by': issued_by,
                                'year': year
                            }
                            honors.append(honor_data)
                            print(f"  ✓ {len(honors)}. {honor_data['title']}")
                    except Exception as e:
                        print(f"  Error parsing honor: {e}")
                        continue
                
                click_back_arrow(self.driver)
            else:
                # No show all, extract from main page
                print("  Extracting from main page...")
                items = honors_section.find_elements(By.XPATH, ".//ul/li")
                
                for item in items:
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 10:
                            continue
                        
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        if len(lines) >= 2:
                            title = lines[0]
                            issued_line = lines[1]
                            
                            issued_by = ""
                            year = ""
                            
                            if '·' in issued_line:
                                parts = issued_line.split('·')
                                issued_by = parts[0].strip()
                                year = parts[1].strip() if len(parts) > 1 else ""
                                if issued_by.startswith('Issued by '):
                                    issued_by = issued_by.replace('Issued by ', '', 1)
                            else:
                                issued_by = issued_line.replace('Issued by ', '', 1)
                            
                            honor_data = {
                                'title': title,
                                'issued_by': issued_by,
                                'year': year
                            }
                            honors.append(honor_data)
                            print(f"  ✓ {len(honors)}. {honor_data['title']}")
                    except Exception as e:
                        print(f"  Error: {e}")
                        continue
        
        except Exception as e:
            print(f"Error: {e}")
        
        return honors
    
    def extract_languages(self):
        """Extract languages section"""
        languages = []
        try:
            print("Looking for languages section...")
            
            lang_section = None
            selectors = [
                "//section[contains(@id, 'languages')]",
                "//section[.//div[@id='languages']]",
                "//section[.//h2[contains(text(), 'Languages')]]",
            ]
            
            for selector in selectors:
                try:
                    lang_section = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    print(f"✓ Found section")
                    break
                except TimeoutException:
                    continue
            
            if not lang_section:
                print("⚠ Languages section not found")
                return languages
            
            smooth_scroll(self.driver, lang_section)
            human_delay(0.3, 0.5)
            
            items = lang_section.find_elements(By.XPATH, ".//ul/li")
            
            for item in items:
                try:
                    spans = item.find_elements(By.XPATH, ".//span[@aria-hidden='true']")
                    if spans:
                        lang_name = spans[0].text.strip()
                        proficiency = spans[1].text.strip() if len(spans) > 1 else ""
                        
                        if lang_name:
                            if proficiency and proficiency != lang_name:
                                languages.append(f"{lang_name} - {proficiency}")
                            else:
                                languages.append(lang_name)
                            print(f"✓ {len(languages)}. {lang_name}")
                except:
                    continue
        
        except Exception as e:
            print(f"Languages section not found")
        
        return languages
    
    def extract_licenses(self):
        """Extract licenses & certifications section with show all flow"""
        licenses = []
        try:
            print("Looking for licenses & certifications section...")
            
            licenses_section = None
            selectors = [
                "//section[contains(@id, 'licenses')]",
                "//section[contains(@id, 'certifications')]",
                "//section[.//div[@id='licenses_and_certifications']]",
                "//section[.//h2[contains(text(), 'Licenses')]]",
                "//section[.//h2[contains(text(), 'Certifications')]]",
                "//section[.//span[contains(text(), 'Licenses & certifications')]]",
            ]
            
            for selector in selectors:
                try:
                    licenses_section = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    print("✓ Found section")
                    break
                except TimeoutException:
                    continue
            
            if not licenses_section:
                print("⚠ Licenses & certifications section not found")
                return licenses
            
            # Click "Show all"
            clicked = click_show_all(self.driver, licenses_section)
            
            if clicked:
                items = extract_items_from_detail_page(self.driver)
                
                for item in items:
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 10:
                            continue
                        
                        # Remove consecutive duplicates
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        print(f"  License item lines: {len(lines)}")
                        for i, line in enumerate(lines[:6]):
                            print(f"    [{i}] {line[:80]}")
                        
                        # Structure after deduplication:
                        # 0: Name
                        # 1: Issuer
                        # 2: Issued date (e.g., "Issued Sep 2023")
                        # 3: Credential ID (e.g., "Credential ID: ABC123") - optional
                        
                        if len(lines) >= 2:
                            name = lines[0]
                            issuer = lines[1]
                            issued_date = ""
                            credential_id = ""
                            
                            # Extract issued date
                            if len(lines) > 2:
                                date_line = lines[2]
                                if 'Issued' in date_line:
                                    issued_date = date_line.replace('Issued ', '').strip()
                            
                            # Extract credential ID
                            if len(lines) > 3:
                                cred_line = lines[3]
                                if 'Credential ID' in cred_line:
                                    credential_id = cred_line.replace('Credential ID', '').replace(':', '').strip()
                            
                            license_data = {
                                'name': name,
                                'issuer': issuer,
                                'issued_date': issued_date,
                                'credential_id': credential_id
                            }
                            licenses.append(license_data)
                            print(f"  ✓ {len(licenses)}. {license_data['name']}")
                    except Exception as e:
                        print(f"  Error parsing license: {e}")
                        continue
                
                click_back_arrow(self.driver)
            else:
                # No show all, extract from main page
                print("  Extracting from main page...")
                items = licenses_section.find_elements(By.XPATH, ".//ul/li")
                
                for item in items:
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 10:
                            continue
                        
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        if len(lines) >= 2:
                            name = lines[0]
                            issuer = lines[1]
                            issued_date = ""
                            credential_id = ""
                            
                            if len(lines) > 2:
                                date_line = lines[2]
                                if 'Issued' in date_line:
                                    issued_date = date_line.replace('Issued ', '').strip()
                            
                            if len(lines) > 3:
                                cred_line = lines[3]
                                if 'Credential ID' in cred_line:
                                    credential_id = cred_line.replace('Credential ID', '').replace(':', '').strip()
                            
                            license_data = {
                                'name': name,
                                'issuer': issuer,
                                'issued_date': issued_date,
                                'credential_id': credential_id
                            }
                            licenses.append(license_data)
                            print(f"  ✓ {len(licenses)}. {license_data['name']}")
                    except Exception as e:
                        print(f"  Error: {e}")
                        continue
        
        except Exception as e:
            print(f"Error: {e}")
        
        return licenses
    
    def extract_courses(self):
        """Extract courses section with show all flow"""
        courses = []
        try:
            print("Looking for courses section...")
            
            courses_section = None
            selectors = [
                "//section[contains(@id, 'courses')]",
                "//section[.//div[@id='courses']]",
                "//section[.//h2[contains(text(), 'Courses')]]",
            ]
            
            for selector in selectors:
                try:
                    courses_section = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    print("✓ Found section")
                    break
                except TimeoutException:
                    continue
            
            if not courses_section:
                print("⚠ Courses section not found")
                return courses
            
            # Click "Show all"
            clicked = click_show_all(self.driver, courses_section)
            
            if clicked:
                items = extract_items_from_detail_page(self.driver)
                
                for item in items:
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 5:
                            continue
                        
                        # Remove consecutive duplicates
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        print(f"  Course item lines: {len(lines)}")
                        for i, line in enumerate(lines[:5]):
                            print(f"    [{i}] {line[:80]}")
                        
                        # Skip if this line is "Associated with X" (it's a duplicate from previous course)
                        if lines[0].startswith('Associated with'):
                            print(f"  → SKIP: Associated with line (duplicate)")
                            continue
                        
                        # Structure after deduplication:
                        # 0: Name
                        # 1: Code (e.g., "COMP6502" or "Course number: CS101")
                        # 2: Associated with (e.g., "Associated with University Name")
                        
                        if len(lines) >= 1:
                            name = lines[0]
                            code = ""
                            associated_with = ""
                            
                            # Extract code and associated_with
                            for line in lines[1:]:
                                # Check if it's "Associated with"
                                if line.startswith('Associated with'):
                                    associated_with = line.replace('Associated with', '').strip()
                                # Check if it's course number/code
                                elif 'Course number' in line or 'number' in line.lower():
                                    code = line.replace('Course number', '').replace(':', '').strip()
                                # If it's short and alphanumeric, likely a code (e.g., "COMP6502")
                                elif len(line) < 20 and not line.startswith('Associated'):
                                    code = line
                            
                            course_data = {
                                'name': name,
                                'code': code,
                                'associated_with': associated_with
                            }
                            courses.append(course_data)
                            print(f"  ✓ {len(courses)}. {course_data['name']}")
                    except Exception as e:
                        print(f"  Error parsing course: {e}")
                        continue
                
                click_back_arrow(self.driver)
            else:
                # No show all, extract from main page
                print("  Extracting from main page...")
                items = courses_section.find_elements(By.XPATH, ".//ul/li")
                
                for item in items:
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 5:
                            continue
                        
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        # Skip if this line is "Associated with X" (it's a duplicate from previous course)
                        if lines[0].startswith('Associated with'):
                            print(f"  → SKIP: Associated with line (duplicate)")
                            continue
                        
                        if len(lines) >= 1:
                            name = lines[0]
                            code = ""
                            associated_with = ""
                            
                            # Extract code and associated_with
                            for line in lines[1:]:
                                # Check if it's "Associated with"
                                if line.startswith('Associated with'):
                                    associated_with = line.replace('Associated with', '').strip()
                                # Check if it's course number/code
                                elif 'Course number' in line or 'number' in line.lower():
                                    code = line.replace('Course number', '').replace(':', '').strip()
                                # If it's short and alphanumeric, likely a code (e.g., "COMP6502")
                                elif len(line) < 20 and not line.startswith('Associated'):
                                    code = line
                            
                            course_data = {
                                'name': name,
                                'code': code,
                                'associated_with': associated_with
                            }
                            courses.append(course_data)
                            print(f"  ✓ {len(courses)}. {course_data['name']}")
                    except Exception as e:
                        print(f"  Error: {e}")
                        continue
        
        except Exception as e:
            print(f"Error: {e}")
        
        return courses
    
    def extract_volunteering(self):
        """Extract volunteering section with show all flow"""
        volunteering = []
        try:
            print("Looking for volunteering section...")
            
            vol_section = None
            selectors = [
                "//section[contains(@id, 'volunteering')]",
                "//section[.//div[@id='volunteering-experience']]",
                "//section[.//div[@id='volunteering_experience']]",
                "//section[.//h2[contains(text(), 'Volunteering')]]",
                "//section[.//span[contains(text(), 'Volunteer experience')]]",
                "//div[@id='volunteering-experience-section']",
            ]
            
            for selector in selectors:
                try:
                    vol_section = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    print("✓ Found section")
                    break
                except TimeoutException:
                    continue
            
            if not vol_section:
                print("⚠ Volunteering section not found")
                return volunteering
            
            # Click "Show all"
            clicked = click_show_all(self.driver, vol_section)
            
            if clicked:
                items = extract_items_from_detail_page(self.driver)
                print(f"Found {len(items)} volunteering items")
                
                for idx, item in enumerate(items):
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 10:
                            continue
                        
                        # Remove consecutive duplicates
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        print(f"\n  === Volunteering Item {idx+1}/{len(items)} ===")
                        print(f"  Total lines: {len(lines)}")
                        for i, line in enumerate(lines[:10]):
                            print(f"    [{i}] {line[:80]}")
                        
                        # Structure after deduplication:
                        # [0] Role/Title (e.g., "YLI by McKinsey & Co. Awardee: Wave 14")
                        # [1] Organization (e.g., "Young Leaders for Indonesia Foundation")
                        # [2] Duration (e.g., "May 2022 - Dec 2022 · 8 mos")
                        # [3] Duration duplicate (e.g., "May 2022 to Dec 2022 · 8 mos")
                        # [4] Cause/Category (e.g., "Education")
                        # [5+] Description (optional)
                        
                        if len(lines) >= 3:
                            role = lines[0]
                            organization = lines[1]
                            duration = lines[2]
                            cause = ""
                            description = ""
                            
                            # Line[3] is duplicate duration, skip it
                            # Line[4] is usually cause (short, single word or phrase)
                            if len(lines) > 4:
                                potential_cause = lines[4]
                                # Cause is usually short (< 50 chars) and doesn't have dates or long descriptions
                                if len(potential_cause) < 50 and '-' not in potential_cause and '·' not in potential_cause:
                                    cause = potential_cause
                                    print(f"  → Cause: {cause}")
                            
                            # Description is after cause (if exists)
                            desc_start_idx = 5 if cause else 4
                            if len(lines) > desc_start_idx:
                                # Join remaining lines as description
                                desc_lines = []
                                for line in lines[desc_start_idx:]:
                                    # Skip "Skills:" and skill names
                                    if line.startswith('Skills:') or line == 'Skills':
                                        break
                                    # Skip if it's "Associated with"
                                    if line.startswith('Associated with'):
                                        break
                                    desc_lines.append(line)
                                
                                if desc_lines:
                                    description = ' '.join(desc_lines)
                                    print(f"  → Description: {description[:60]}...")
                            
                            vol_data = {
                                'role': role,
                                'organization': organization,
                                'duration': duration,
                                'cause': cause,
                                'description': description
                            }
                            volunteering.append(vol_data)
                            print(f"  ✓ ADDED {len(volunteering)}. {vol_data['role']}")
                        else:
                            print(f"  → SKIP: Not enough lines ({len(lines)})")
                    except Exception as e:
                        print(f"  Error parsing volunteering item {idx+1}: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                
                click_back_arrow(self.driver)
            else:
                # No show all, extract from main page
                print("  Extracting from main page...")
                items = vol_section.find_elements(By.XPATH, ".//ul/li")
                print(f"  Found {len(items)} items on main page")
                
                for idx, item in enumerate(items):
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 10:
                            continue
                        
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        print(f"\n  === Item {idx+1}/{len(items)} ===")
                        print(f"  Lines: {len(lines)}")
                        for i, line in enumerate(lines[:8]):
                            print(f"    [{i}] {line[:80]}")
                        
                        if len(lines) >= 3:
                            role = lines[0]
                            organization = lines[1]
                            duration = lines[2]
                            cause = ""
                            description = ""
                            
                            if len(lines) > 4:
                                potential_cause = lines[4]
                                if len(potential_cause) < 50 and '-' not in potential_cause and '·' not in potential_cause:
                                    cause = potential_cause
                            
                            desc_start_idx = 5 if cause else 4
                            if len(lines) > desc_start_idx:
                                desc_lines = []
                                for line in lines[desc_start_idx:]:
                                    if line.startswith('Skills:') or line == 'Skills':
                                        break
                                    if line.startswith('Associated with'):
                                        break
                                    desc_lines.append(line)
                                
                                if desc_lines:
                                    description = ' '.join(desc_lines)
                            
                            vol_data = {
                                'role': role,
                                'organization': organization,
                                'duration': duration,
                                'cause': cause,
                                'description': description
                            }
                            volunteering.append(vol_data)
                            print(f"  ✓ ADDED {len(volunteering)}. {vol_data['role']}")
                        else:
                            print(f"  → SKIP: Not enough lines")
                    except Exception as e:
                        print(f"  Error: {e}")
                        continue
        
        except Exception as e:
            print(f"Error extracting volunteering: {e}")
            import traceback
            traceback.print_exc()
        
        return volunteering
    
    def extract_test_scores(self):
        """Extract test scores section with show all flow"""
        test_scores = []
        try:
            print("Looking for test scores section...")
            
            test_section = None
            selectors = [
                "//section[contains(@id, 'test-scores')]",
                "//section[contains(@id, 'test_scores')]",
                "//section[.//div[@id='test-scores']]",
                "//section[.//h2[contains(text(), 'Test scores')]]",
                "//section[.//h2[contains(text(), 'Test Scores')]]",
                "//section[.//span[contains(text(), 'Test scores')]]",
            ]
            
            for selector in selectors:
                try:
                    test_section = self.wait.until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                    print("✓ Found section")
                    break
                except TimeoutException:
                    continue
            
            if not test_section:
                print("⚠ Test scores section not found")
                return test_scores
            
            # Click "Show all"
            clicked = click_show_all(self.driver, test_section)
            
            if clicked:
                items = extract_items_from_detail_page(self.driver)
                
                for item in items:
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 5:
                            continue
                        
                        # Remove consecutive duplicates
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        print(f"  Test score item lines: {len(lines)}")
                        for i, line in enumerate(lines[:6]):
                            print(f"    [{i}] {line[:80]}")
                        
                        # Structure after deduplication:
                        # [0] Test Name (e.g., "TOEFL iBT")
                        # [1] Score · Duration (e.g., "110 · Jan 2023 - Jan 2025")
                        # [2] Score · Duration duplicate (e.g., "110 · Jan 2023 to Jan 2025")
                        # [3] Description (optional)
                        
                        if len(lines) >= 2:
                            name = lines[0]
                            score = ""
                            duration = ""
                            description = ""
                            
                            # Parse line[1]: "Score · Duration"
                            score_duration_line = lines[1]
                            
                            # Split by middle dot (·)
                            if '·' in score_duration_line:
                                parts = score_duration_line.split('·')
                                score = parts[0].strip()
                                duration = parts[1].strip() if len(parts) > 1 else ""
                            else:
                                # No middle dot, whole line is score
                                score = score_duration_line
                            
                            # Line[2] is duplicate, skip it
                            # Line[3+] is description (optional)
                            if len(lines) > 3:
                                desc_lines = []
                                for line in lines[3:]:
                                    # Skip if it's "Associated with" or other metadata
                                    if line.startswith('Associated with'):
                                        break
                                    desc_lines.append(line)
                                
                                if desc_lines:
                                    description = ' '.join(desc_lines)
                            
                            test_data = {
                                'name': name,
                                'score': score,
                                'duration': duration,
                                'description': description
                            }
                            test_scores.append(test_data)
                            print(f"  ✓ {len(test_scores)}. {test_data['name']} - {test_data['score']}")
                    except Exception as e:
                        print(f"  Error parsing test score: {e}")
                        continue
                
                click_back_arrow(self.driver)
            else:
                # No show all, extract from main page
                print("  Extracting from main page...")
                items = test_section.find_elements(By.XPATH, ".//ul/li")
                
                for item in items:
                    try:
                        text = item.text.strip()
                        if not text or len(text) < 5:
                            continue
                        
                        all_lines = [l.strip() for l in text.split('\n') if l.strip()]
                        lines = []
                        prev = None
                        for line in all_lines:
                            if line != prev:
                                lines.append(line)
                                prev = line
                        
                        if len(lines) >= 2:
                            name = lines[0]
                            score = ""
                            duration = ""
                            description = ""
                            
                            score_duration_line = lines[1]
                            
                            if '·' in score_duration_line:
                                parts = score_duration_line.split('·')
                                score = parts[0].strip()
                                duration = parts[1].strip() if len(parts) > 1 else ""
                            else:
                                score = score_duration_line
                            
                            if len(lines) > 3:
                                desc_lines = []
                                for line in lines[3:]:
                                    if line.startswith('Associated with'):
                                        break
                                    desc_lines.append(line)
                                
                                if desc_lines:
                                    description = ' '.join(desc_lines)
                            
                            test_data = {
                                'name': name,
                                'score': score,
                                'duration': duration,
                                'description': description
                            }
                            test_scores.append(test_data)
                            print(f"  ✓ {len(test_scores)}. {test_data['name']}")
                    except Exception as e:
                        print(f"  Error: {e}")
                        continue
        
        except Exception as e:
            print(f"Error: {e}")
        
        return test_scores
    
    def close(self):
        """Close the browser"""
        self.driver.quit()

"""
Scoring Consumer - Process profiles from RabbitMQ and calculate scores
OPTIMIZED VERSION
"""
import json
import os
import sys
import threading
import time
import re
import glob
from datetime import datetime
from pathlib import Path
import pika
from dotenv import load_dotenv
from rapidfuzz import fuzz
from supabase import create_client, Client

# Add API helper to path for shared utilities (with fallback)
sys.path.append(str(Path(__file__).parent.parent / "api" / "helper"))

# Try to import from common_utils, fallback to local implementation
try:
    from common_utils import get_profile_hash, StatsManager, create_rabbitmq_connection, WebhookChecker
    print("✓ Using shared common_utils")
except ImportError:
    print("⚠ common_utils not found, using local implementation")
    
    # Local fallback implementations
    import hashlib
    import threading
    
    def get_profile_hash(profile_url):
        """Generate unique hash from profile URL"""
        return hashlib.md5(profile_url.encode()).hexdigest()[:8]
    
    class StatsManager:
        def __init__(self, stats_config=None):
            default_stats = {
                'processing': 0, 'completed': 0, 'failed': 0, 'skipped': 0,
                'supabase_updated': 0, 'supabase_failed': 0, 'lock': threading.Lock()
            }
            if stats_config:
                default_stats.update(stats_config)
            self.stats = default_stats
        
        def increment(self, key):
            with self.stats['lock']:
                if key in self.stats:
                    self.stats[key] += 1
        
        def decrement(self, key):
            with self.stats['lock']:
                if key in self.stats:
                    self.stats[key] -= 1
        
        def get_stats(self):
            with self.stats['lock']:
                return {k: v for k, v in self.stats.items() if k != 'lock'}
        
        def print_stats(self, title="SCORING STATISTICS"):
            stats_copy = self.get_stats()
            print(f"\n{'='*60}\n{title}\n{'='*60}")
            for key, value in stats_copy.items():
                print(f"{key.replace('_', ' ').title()}: {value}")
            if stats_copy.get('completed', 0) + stats_copy.get('failed', 0) > 0:
                success_rate = stats_copy['completed'] / (stats_copy['completed'] + stats_copy['failed']) * 100
                print(f"Success Rate: {success_rate:.1f}%")
            print("="*60)
    
    def create_rabbitmq_connection():
        """Create standardized RabbitMQ connection"""
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
        parameters = pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            virtual_host=RABBITMQ_VHOST,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300
        )
        return pika.BlockingConnection(parameters)
    
    class WebhookChecker:
        @staticmethod
        def check_and_send_webhook(supabase_client, template_id, worker_id=""):
            try:
                schedule_result = supabase_client.table('crawler_schedules').select('id').eq('template_id', template_id).execute()
                
                if schedule_result.data:
                    schedule_id = schedule_result.data[0]['id']
                    print(f"🔔 Checking webhook for schedule {schedule_id}...")
                    
                    try:
                        # Try to import webhook helper
                        try:
                            from webhook_helper import send_completion_webhook
                        except ImportError:
                            # Fallback: try different path
                            import sys
                            from pathlib import Path
                            sys.path.append(str(Path(__file__).parent.parent / "api" / "helper"))
                            from webhook_helper import send_completion_webhook
                        
                        webhook_sent = send_completion_webhook(supabase_client, schedule_id)
                        if webhook_sent:
                            print(f"✅ Webhook notification sent for completed schedule")
                        return webhook_sent
                    except ImportError:
                        print(f"⚠ Webhook helper not available")
                        return False
                
            except Exception as webhook_error:
                print(f"⚠ Webhook check failed: {webhook_error}")
                return False

# Load environment variables
load_dotenv()

# Configuration
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'guest')
RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASS', 'guest')
RABBITMQ_VHOST = os.getenv('RABBITMQ_VHOST', '/')
SCORING_QUEUE = os.getenv('SCORING_QUEUE', 'scoring_queue')

# Supabase Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

OUTPUT_DIR = 'data/scores'
REQUIREMENTS_DIR = 'requirements'

# Initialize Supabase client (only if credentials provided)
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✓ Supabase connected")
    except Exception as e:
        print(f"⚠ Supabase connection failed: {e}")
else:
    print("⚠ Supabase credentials not found in .env")

# Statistics manager with scoring-specific stats
stats_manager = StatsManager({
    'supabase_updated': 0,
    'supabase_failed': 0
})


class ChecklistScorer:
    """Checklist-based Scorer - Simple True/False matching for each requirement"""
    def __init__(self, requirements):
        self.requirements = requirements
        self.results = []
    
    def score(self, profile):
        """Check each requirement and return matched/not matched"""
        
        # Get requirements array from template
        requirements_list = self.requirements.get('requirements', [])
        
        if not requirements_list:
            print("⚠ No requirements array found in template")
            return {
                'total_requirements': 0,
                'matched': 0,
                'percentage': 0,
                'results': []
            }
        
        matched_count = 0
        total_count = len(requirements_list)
        
        for req in requirements_list:
            req_id = req.get('id', '')
            req_label = req.get('label', '')
            req_type = req.get('type', '')
            req_value = req.get('value')
            
            # Check if requirement is matched
            matched = self._check_requirement(req, profile)
            
            # Get candidate value for display
            candidate_value = self._get_candidate_value(req, profile)
            
            result = {
                'id': req_id,
                'label': req_label,
                'type': req_type,
                'required_value': req_value,
                'candidate_value': candidate_value,
                'matched': matched
            }
            
            self.results.append(result)
            
            if matched:
                matched_count += 1
        
        percentage = (matched_count / total_count * 100) if total_count > 0 else 0
        
        return {
            'total_requirements': total_count,
            'matched': matched_count,
            'percentage': round(percentage, 2),
            'results': self.results
        }
    
    def _check_requirement(self, req, profile):
        """Check if a single requirement is matched"""
        req_type = req.get('type', '')
        req_id = req.get('id', '')
        req_value = req.get('value')
        
        if req_type == 'gender':
            return self._check_gender(req_value, profile)
        elif req_type == 'location':
            return self._check_location(req_value, profile)
        elif req_type == 'age':
            return self._check_age(req_value, profile)
        elif req_type == 'experience':
            return self._check_experience(req_value, profile)
        elif req_type == 'skill':
            return self._check_skill(req_value, profile)
        elif req_type == 'education':
            return self._check_education(req_value, profile)
        else:
            return False
    
    def _get_candidate_value(self, req, profile):
        """Get candidate's value for this requirement"""
        req_type = req.get('type', '')
        
        if req_type == 'gender':
            return profile.get('gender', 'N/A')
        elif req_type == 'location':
            return profile.get('location', 'N/A')
        elif req_type == 'age':
            age = profile.get('age')
            if not age and profile.get('estimated_age'):
                estimated = profile.get('estimated_age', {})
                if isinstance(estimated, dict):
                    age = estimated.get('estimated_age')
                else:
                    age = estimated
            return age or 'N/A'
        elif req_type == 'experience':
            # Return total years of experience
            experiences = profile.get('experiences', [])
            total_months = 0
            for exp in experiences:
                if isinstance(exp, dict):
                    duration = exp.get('duration', '')
                    years = 0
                    months = 0
                    year_match = re.search(r'(\d+)\s*yr', duration)
                    if year_match:
                        years = int(year_match.group(1))
                    month_match = re.search(r'(\d+)\s*mo', duration)
                    if month_match:
                        months = int(month_match.group(1))
                    total_months += (years * 12) + months
            total_years = round(total_months / 12, 1) if total_months > 0 else 0
            return f"{total_years} years"
        elif req_type == 'skill':
            # Return if skill exists
            skills = profile.get('skills', [])
            skill_names = []
            for s in skills:
                if isinstance(s, dict):
                    name = s.get('name', '')
                    if name and name != 'N/A':
                        skill_names.append(name)
                elif isinstance(s, str) and s and s != 'N/A':
                    skill_names.append(s)
            return ', '.join(skill_names[:3]) if skill_names else 'N/A'
        elif req_type == 'education':
            education = profile.get('education', [])
            if education and len(education) > 0:
                if isinstance(education[0], dict):
                    return education[0].get('degree', 'N/A')
            return 'N/A'
        else:
            return 'N/A'
    
    def _check_gender(self, required_gender, profile):
        """Check if gender matches using numeric comparison for accuracy"""
        if not required_gender:
            return True
        
        profile_gender = profile.get('gender', '').lower().strip()
        required_gender = str(required_gender).lower().strip()
        
        if not profile_gender:
            return False
        
        # Convert to numeric codes for exact comparison
        # Male = 0, Female = 1
        def gender_to_code(gender_str):
            gender_str = gender_str.lower()
            if 'male' in gender_str and 'female' not in gender_str:
                return 0  # Male
            elif 'female' in gender_str:
                return 1  # Female
            else:
                return -1  # Unknown
        
        profile_code = gender_to_code(profile_gender)
        required_code = gender_to_code(required_gender)
        
        # If either is unknown, cannot match
        if profile_code == -1 or required_code == -1:
            return False
        
        # Exact match: 0 == 0 (Male) or 1 == 1 (Female)
        return profile_code == required_code
    
    def _check_location(self, required_location, profile):
        """Check if location matches (fuzzy)"""
        if not required_location:
            return True
        
        profile_location = profile.get('location', '').lower()
        required_location = str(required_location).lower()
        
        if not profile_location:
            return False
        
        # Exact or partial match
        if required_location in profile_location or profile_location in required_location:
            return True
        
        # Fuzzy match (80% threshold)
        ratio = fuzz.partial_ratio(required_location, profile_location)
        return ratio >= 80
    
    def _check_age(self, required_age_range, profile):
        """Check if age is in range"""
        if not required_age_range:
            return True
        
        # Get profile age
        profile_age = profile.get('age')
        if not profile_age and profile.get('estimated_age'):
            estimated = profile.get('estimated_age', {})
            if isinstance(estimated, dict):
                profile_age = estimated.get('estimated_age')
            else:
                profile_age = estimated
        
        if not profile_age:
            return False
        
        try:
            age = int(profile_age)
            
            # If required_age_range is a dict with min/max
            if isinstance(required_age_range, dict):
                min_age = required_age_range.get('min', 0)
                max_age = required_age_range.get('max', 100)
                return min_age <= age <= max_age
            
            # If required_age_range is a string like "25-35"
            elif isinstance(required_age_range, str):
                if '-' in required_age_range:
                    parts = required_age_range.split('-')
                    min_age = int(parts[0].strip())
                    max_age = int(parts[1].strip())
                    return min_age <= age <= max_age
            
            return False
        except:
            return False
    
    def _check_experience(self, required_experience, profile):
        """Check if experience meets requirement"""
        if not required_experience:
            return True
        
        experiences = profile.get('experiences', [])
        
        # If required_experience is a number (minimum years)
        if isinstance(required_experience, (int, float)):
            min_years = required_experience
            total_months = 0
            
            for exp in experiences:
                if isinstance(exp, dict):
                    duration = exp.get('duration', '')
                    years = 0
                    months = 0
                    year_match = re.search(r'(\d+)\s*yr', duration)
                    if year_match:
                        years = int(year_match.group(1))
                    month_match = re.search(r'(\d+)\s*mo', duration)
                    if month_match:
                        months = int(month_match.group(1))
                    total_months += (years * 12) + months
            
            total_years = total_months / 12
            return total_years >= min_years
        
        # If required_experience is a string (keyword to match)
        elif isinstance(required_experience, str):
            keyword = required_experience.lower()
            
            for exp in experiences:
                if isinstance(exp, dict):
                    title = exp.get('title', '').lower()
                    company = exp.get('company', '').lower()
                    description = exp.get('description', '').lower()
                    exp_text = f"{title} {company} {description}"
                    
                    # Check if keyword exists
                    if keyword in exp_text:
                        return True
                    
                    # Fuzzy match
                    for word in exp_text.split():
                        if fuzz.ratio(keyword, word) >= 80:
                            return True
            
            return False
        
        return False
    
    def _check_skill(self, required_skill, profile):
        """Check if skill exists in skills list OR in experience"""
        if not required_skill:
            return True
        
        required_skill_lower = str(required_skill).lower()
        
        # Check in skills list first
        skills = profile.get('skills', [])
        for skill in skills:
            skill_name = ''
            if isinstance(skill, dict):
                skill_name = skill.get('name', '').lower()
            elif isinstance(skill, str):
                skill_name = skill.lower()
            
            if not skill_name or skill_name == 'n/a':
                continue
            
            # Exact or partial match
            if required_skill_lower in skill_name or skill_name in required_skill_lower:
                return True
            
            # Fuzzy match (70% threshold)
            if fuzz.ratio(required_skill_lower, skill_name) >= 70:
                return True
        
        # If not found in skills, check in experience (title, company, description)
        experiences = profile.get('experiences', [])
        for exp in experiences:
            if isinstance(exp, dict):
                title = exp.get('title', '').lower()
                company = exp.get('company', '').lower()
                description = exp.get('description', '').lower()
                exp_text = f"{title} {company} {description}"
                
                # Check if skill keyword exists in experience
                if required_skill_lower in exp_text:
                    return True
                
                # Fuzzy match on individual words
                for word in exp_text.split():
                    if len(word) > 3 and fuzz.ratio(required_skill_lower, word) >= 75:
                        return True
        
        return False
    
    def _check_education(self, required_education, profile):
        """Check if education level meets requirement"""
        if not required_education:
            return True
        
        education = profile.get('education', [])
        if not education:
            return False
        
        levels = {
            'high school': 1, 'sma': 1, 'smk': 1,
            'diploma': 2, 'associate': 2, 'd3': 2,
            'bachelor': 3, 's1': 3, 'sarjana': 3,
            'master': 4, 's2': 4, 'mba': 4,
            'doctoral': 5, 'phd': 5, 's3': 5
        }
        
        # Get candidate's highest education level
        highest = 0
        for edu in education:
            if isinstance(edu, dict):
                degree = edu.get('degree', '').lower()
                for level_name, level_val in levels.items():
                    if level_name in degree and level_val > highest:
                        highest = level_val
        
        # Get required education level
        required_level = 0
        required_education_lower = str(required_education).lower()
        for level_name, level_val in levels.items():
            if level_name in required_education_lower and level_val > required_level:
                required_level = level_val
        
        return highest >= required_level


def load_requirements(template_id):
    """Load requirements from Supabase search_templates table"""
    if not supabase:
        print("⚠ Supabase not configured")
        return None
    
    try:
        print(f"📥 Loading requirements from Supabase (template_id: {template_id})...")
        
        response = supabase.table('search_templates').select('requirements').eq('id', template_id).execute()
        
        if not response.data or len(response.data) == 0:
            print(f"⚠ Template not found: {template_id}")
            return None
        
        requirements = response.data[0].get('requirements')
        
        if not requirements:
            print(f"⚠ No requirements found in template: {template_id}")
            return None
        
        # Debug: Print requirements structure
        print(f"📋 Requirements structure: {type(requirements)}")
        if isinstance(requirements, dict):
            print(f"   Keys: {requirements.keys()}")
            if 'requirements' in requirements:
                print(f"   Requirements array length: {len(requirements.get('requirements', []))}")
        elif isinstance(requirements, list):
            print(f"   Requirements array length: {len(requirements)}")
        
        # If requirements is a list, wrap it in a dict with 'requirements' key
        if isinstance(requirements, list):
            print(f"⚠ Requirements is a list, wrapping in dict...")
            requirements = {'requirements': requirements}
        
        # Validate that requirements has the 'requirements' array
        if not isinstance(requirements, dict) or 'requirements' not in requirements:
            print(f"⚠ Invalid requirements structure. Expected dict with 'requirements' key")
            return None
        
        req_array = requirements.get('requirements', [])
        if not req_array or len(req_array) == 0:
            print(f"⚠ Requirements array is empty")
            return None
        
        print(f"✓ Requirements loaded from Supabase ({len(req_array)} items)")
        return requirements
    
    except Exception as e:
        print(f"✗ Error loading requirements from Supabase: {e}")
        import traceback
        traceback.print_exc()
        return None





def check_if_already_scored(profile_url, requirements_id, output_dir=OUTPUT_DIR):
    """Check if profile has already been scored for this requirement"""
    if not os.path.exists(output_dir):
        return False, None
    
    url_hash = get_profile_hash(profile_url)
    
    # Search for existing files with this URL hash and requirements_id
    pattern = os.path.join(output_dir, f"*_{requirements_id}_*_{url_hash}_score.json")
    existing_files = glob.glob(pattern)
    
    if existing_files:
        return True, existing_files[0]
    
    # Fallback: check by reading all score JSON files
    all_files = glob.glob(os.path.join(output_dir, "*_score.json"))
    for filepath in all_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                profile = data.get('profile', {})
                req_id = data.get('requirements_id', '')
                if profile.get('profile_url') == profile_url and req_id == requirements_id:
                    return True, filepath
        except:
            continue
    
    return False, None


def save_score_result(profile_data, score_result, requirements_id):
    """Save scoring result to JSON file (with duplicate prevention)"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    profile_url = profile_data.get('profile_url', '')
    
    # Check if already scored
    if profile_url:
        already_exists, existing_file = check_if_already_scored(profile_url, requirements_id)
        if already_exists:
            print(f"⚠ Score already exists: {existing_file}")
            print(f"  Skipping save to avoid duplication")
            return existing_file
    
    # Create filename with hash
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    name = profile_data.get('name', 'unknown')
    
    if not name or name == 'N/A' or len(name.strip()) == 0:
        name = 'unknown'
    
    # Clean name for filename
    name_slug = name.replace(' ', '_').replace('/', '_').replace('\\', '_').lower()
    name_slug = ''.join(c for c in name_slug if c.isalnum() or c in ('_', '-'))
    
    # Add URL hash to filename for uniqueness
    url_hash = get_profile_hash(profile_url) if profile_url else 'nohash'
    filename = f"{name_slug}_{requirements_id}_{timestamp}_{url_hash}_score.json"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # Prepare output
    output = {
        'profile': profile_data,
        'requirements_id': requirements_id,
        'score': score_result,
        'processed_at': datetime.now().isoformat()
    }
    
    # Save to file
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Score saved to: {filepath}")
    return filepath


def update_supabase_score(profile_url, percentage, profile_data=None, score_result=None):
    """Update score and profile data in Supabase leads_list table
    
    ALWAYS overwrites existing score with new score and updates scored_at to current date
    """
    try:
        print(f"📤 Updating Supabase...")
        
        # Check if lead exists first
        existing = supabase.table('leads_list').select('id, profile_data, score').eq('profile_url', profile_url).execute()
        
        # Prepare update data - ALWAYS update score and processed_at
        update_data = {
            'score': percentage,
            'processed_at': datetime.now().isoformat()
        }
        
        # Add scoring_data (checklist results) if provided
        if score_result:
            update_data['scoring_data'] = score_result
        
        # Add profile data if provided and not already in database
        if profile_data:
            # Update name if available
            if profile_data.get('name'):
                update_data['name'] = profile_data.get('name')
            
            # If profile_data doesn't exist in DB yet, save it
            if existing.data and len(existing.data) > 0:
                existing_profile_data = existing.data[0].get('profile_data')
                if not existing_profile_data or existing_profile_data == {}:
                    # No profile data yet, save it
                    update_data['profile_data'] = profile_data
                    print(f"  → Adding profile_data to existing lead")
            else:
                # Lead doesn't exist, will be created with profile data
                update_data['profile_data'] = profile_data
                update_data['date'] = datetime.now().date().isoformat()
                update_data['connection_status'] = 'scored'
        
        # Update or insert
        if existing.data and len(existing.data) > 0:
            # Update existing lead - OVERWRITE score
            old_score = existing.data[0].get('score')
            response = supabase.table('leads_list').update(update_data).eq('profile_url', profile_url).execute()
            
            if response.data:
                if old_score is not None:
                    print(f"✓ Supabase updated: {profile_url} → score: {old_score}% → {percentage}% (overwritten)")
                else:
                    print(f"✓ Supabase updated: {profile_url} → score: {percentage}% (new)")
                
                # Check if schedule is completed and send webhook if needed
                WebhookChecker.check_and_send_webhook(supabase, template_id)
                
                return True
            else:
                print(f"⚠ Failed to update Supabase")
                return False
        else:
            # Insert new lead (shouldn't happen if crawler ran first, but handle it)
            insert_data = {
                'profile_url': profile_url,
                'score': percentage,
                'processed_at': datetime.now().isoformat(),
                'date': datetime.now().date().isoformat(),
                'connection_status': 'scored'
            }
            
            if score_result:
                insert_data['scoring_data'] = score_result
            
            if profile_data:
                insert_data['name'] = profile_data.get('name', 'Unknown')
                insert_data['profile_data'] = profile_data
            
            response = supabase.table('leads_list').insert(insert_data).execute()
            
            if response.data:
                print(f"✓ Supabase inserted: {profile_url} → score: {percentage}%")
                return True
            else:
                print(f"⚠ Failed to insert to Supabase")
                return False
    
    except Exception as e:
        print(f"✗ Failed to update Supabase: {e}")
        import traceback
        traceback.print_exc()
        return False





def process_message(message_data):
    """Process a single scoring message"""
    try:
        profile_data = message_data.get('profile_data')
        template_id = message_data.get('template_id')
        requirements_id = message_data.get('requirements_id')  # Keep for backward compatibility
        profile_url = profile_data.get('profile_url', '') if profile_data else ''
        
        if not profile_data:
            print("✗ No profile data in message")
            return False
        
        # Use template_id if available, fallback to requirements_id
        req_id = template_id or requirements_id
        
        if not req_id:
            print("✗ No template_id or requirements_id in message")
            return False
        
        name = profile_data.get('name', 'Unknown')
        print(f"\n📥 Processing: {name}")
        print(f"   Template ID: {req_id}")
        
        # Check if already scored
        if profile_url:
            already_exists, existing_file = check_if_already_scored(profile_url, req_id)
            if already_exists:
                print(f"⊘ Already scored: {existing_file}")
                stats_manager.increment('skipped')
                return True  # Return True to ack message
        
        # Load requirements from Supabase templates table
        requirements = load_requirements(req_id)
        
        if not requirements:
            print(f"✗ Failed to load requirements from Supabase: {req_id}")
            return False
        
        # Calculate score
        print(f"🔢 Calculating score...")
        scorer = ChecklistScorer(requirements)
        score_result = scorer.score(profile_data)
        
        # Print result
        print(f"\n{'='*60}")
        print(f"SCORE RESULT: {name}")
        print(f"{'='*60}")
        print(f"Matched: {score_result['matched']}/{score_result['total_requirements']}")
        print(f"Percentage: {score_result['percentage']}%")
        
        print(f"\nRequirements Checklist:")
        for result in score_result['results']:
            status = "✓" if result['matched'] else "✗"
            label = result['label']
            candidate_val = result['candidate_value']
            print(f"  {status} {label}")
            if not result['matched'] and candidate_val != 'N/A':
                print(f"    → Candidate: {candidate_val}")
        print(f"{'='*60}")
        
        # Save result
        save_score_result(profile_data, score_result, req_id)
        
        # Update Supabase
        if supabase:
            profile_url = profile_data.get('profile_url', '')
            percentage = score_result.get('percentage', 0)
            if profile_url:
                if update_supabase_score(profile_url, percentage, profile_data, score_result):
                    stats_manager.increment('supabase_updated')
                else:
                    stats_manager.increment('supabase_failed')
                    with stats['lock']:
                        stats['supabase_failed'] += 1
        else:
            print("⚠ Supabase not configured, skipping database update")
        
        print(f"✓ Completed: {name} - Score: {score_result['percentage']}%")
        
        return True
    
    except Exception as e:
        print(f"✗ Error processing message: {e}")
        import traceback
        traceback.print_exc()
        return False


def worker_thread(worker_id):
    """Worker thread that continuously processes messages from RabbitMQ"""
    print(f"[Worker {worker_id}] Started")
    
    # Connect to RabbitMQ using common utility
    try:
        connection = create_rabbitmq_connection()
        channel = connection.channel()
        
        # Declare queue
        channel.queue_declare(queue=SCORING_QUEUE, durable=True)
        
        # Set QoS - only process 1 message at a time
        channel.basic_qos(prefetch_count=1)
        
        print(f"[Worker {worker_id}] Connected to RabbitMQ")
        print(f"[Worker {worker_id}] Listening to queue: {SCORING_QUEUE}")
        
    except Exception as e:
        print(f"[Worker {worker_id}] Failed to connect to RabbitMQ: {e}")
        return
    
    def callback(ch, method, properties, body):
        """Process each message"""
        try:
            stats_manager.increment('processing')
            
            # Parse message
            message_data = json.loads(body)
            
            # Process
            success = process_message(message_data)
            
            if success:
                stats_manager.increment('completed')
                ch.basic_ack(delivery_tag=method.delivery_tag)
            else:
                stats_manager.increment('failed')
                # Don't requeue to avoid infinite loop
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
            # Print stats
            stats_manager.print_stats("SCORING STATISTICS")
        
        except Exception as e:
            print(f"[Worker {worker_id}] Fatal error: {e}")
            stats_manager.increment('failed')
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        finally:
            stats_manager.decrement('processing')
    
    try:
        # Start consuming
        channel.basic_consume(
            queue=SCORING_QUEUE,
            on_message_callback=callback,
            auto_ack=False
        )
        
        print(f"[Worker {worker_id}] Waiting for messages...")
        channel.start_consuming()
    
    except KeyboardInterrupt:
        print(f"\n[Worker {worker_id}] Interrupted")
    except Exception as e:
        print(f"[Worker {worker_id}] Error: {e}")
    finally:
        try:
            connection.close()
        except:
            pass
        print(f"[Worker {worker_id}] Stopped")


def main():
    print("="*60)
    print("PROFILE SCORING CONSUMER")
    print("="*60)
    
    # Check Supabase connection
    if not supabase:
        print("\n✗ Supabase not configured!")
        print("  Please set SUPABASE_URL and SUPABASE_KEY in .env")
        return
    
    print(f"\n✓ Supabase connected")
    print(f"  Requirements will be loaded from 'search_templates' table")
    
    # Get number of workers (support non-interactive mode for Railway)
    num_workers = int(os.getenv('NUM_WORKERS', '2'))
    if num_workers < 1:
        num_workers = 2
    
    print(f"\n→ Configuration:")
    print(f"  - RabbitMQ: {RABBITMQ_HOST}:{RABBITMQ_PORT}")
    print(f"  - Queue: {SCORING_QUEUE}")
    print(f"  - Workers: {num_workers}")
    print(f"  - Output: {OUTPUT_DIR}/")
    
    # Test RabbitMQ connection
    print(f"\n→ Testing RabbitMQ connection...")
    try:
        connection = create_rabbitmq_connection()
        channel = connection.channel()
        
        # Declare queue
        result = channel.queue_declare(queue=SCORING_QUEUE, durable=True, passive=True)
        queue_size = result.method.message_count
        
        print(f"✓ Connected to RabbitMQ")
        print(f"  - Messages in queue: {queue_size}")
        
        connection.close()
    except Exception as e:
        print(f"✗ Failed to connect to RabbitMQ: {e}")
        print("\nMake sure RabbitMQ is running:")
        print("  docker-compose up -d")
        return
    
    # Start workers
    print(f"\n→ Starting {num_workers} workers...")
    print("  Press Ctrl+C to stop")
    
    threads = []
    for i in range(num_workers):
        t = threading.Thread(target=worker_thread, args=(i+1,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.5)
    
    print(f"\n✓ All {num_workers} workers are running!")
    print("  Waiting for messages from crawler...")
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted by user. Stopping all workers...")
        print("  (Workers will finish current tasks)")
    
    finally:
        # Wait for workers to finish
        time.sleep(2)
        
        # Final stats
        print("\n" + "="*60)
        print("FINAL RESULTS")
        print("="*60)
        current_stats = stats_manager.get_stats()
        print(f"✓ Completed: {current_stats['completed']}")
        print(f"✗ Failed: {current_stats['failed']}")
        print(f"⊘ Skipped (duplicates): {current_stats['skipped']}")
        if current_stats['completed'] + current_stats['failed'] > 0:
            success_rate = current_stats['completed'] / (current_stats['completed'] + current_stats['failed']) * 100
            print(f"📊 Success Rate: {success_rate:.1f}%")
        print("="*60)


if __name__ == "__main__":
    main()

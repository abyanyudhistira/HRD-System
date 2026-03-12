"""Supabase helper for storing crawled data"""
import os
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


class SupabaseManager:
    def __init__(self):
        """Initialize Supabase client"""
        self.url = os.getenv('SUPABASE_URL')
        self.key = os.getenv('SUPABASE_KEY')
        
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        
        self.client: Client = create_client(self.url, self.key)
        # Remove the print statement to avoid spam
        # print(f"✓ Supabase client initialized")
    
    def save_lead(self, profile_url, name, profile_data, connection_status='scraped', template_id=None):
        """
        Save crawled profile to leads_list table
        
        Args:
            profile_url: LinkedIn profile URL
            name: Person's name
            profile_data: Complete profile data as dict (will be stored in jsonb column)
            connection_status: Status (scraped, connected, message_sent, etc)
            template_id: Optional template ID for filtering
        
        Returns:
            bool: Success status
        """
        try:
            # Check if lead already exists
            existing = self.client.table('leads_list')\
                .select('id')\
                .eq('profile_url', profile_url)\
                .execute()
            
            if existing.data:
                # Update existing lead
                update_data = {
                    'name': name,
                    'profile_data': profile_data,
                    'connection_status': connection_status
                }
                
                result = self.client.table('leads_list')\
                    .update(update_data)\
                    .eq('profile_url', profile_url)\
                    .execute()
                
                print(f"  ✓ Updated existing lead: {name}")
            else:
                # Insert new lead
                insert_data = {
                    'profile_url': profile_url,
                    'name': name,
                    'profile_data': profile_data,
                    'connection_status': connection_status,
                    'date': datetime.now().date().isoformat()
                }
                
                if template_id:
                    insert_data['template_id'] = template_id
                
                result = self.client.table('leads_list')\
                    .insert(insert_data)\
                    .execute()
                
                print(f"  ✓ Saved new lead: {name}")
            
            return True
            
        except Exception as e:
            print(f"  ✗ Failed to save to Supabase: {e}")
            return False
    
    def update_connection_status(self, profile_url, status):
        """
        Update connection status for a lead
        
        Args:
            profile_url: LinkedIn profile URL
            status: New status (connection_sent, message_sent, etc)
        """
        try:
            result = self.client.table('leads_list')\
                .update({
                    'connection_status': status
                })\
                .eq('profile_url', profile_url)\
                .execute()
            
            print(f"  ✓ Updated status: {status}")
            return True
            
        except Exception as e:
            print(f"  ✗ Failed to update status: {e}")
            return False
    
    def update_outreach_status(self, profile_url, note_sent, status='success'):
        """
        Update lead after outreach (status + note + timestamp)
        
        Args:
            profile_url: LinkedIn profile URL
            note_sent: The personalized message that was sent
            status: Connection status (default: 'success')
        
        Returns:
            bool: Success status
        """
        try:
            # Check if lead exists first
            lead = self.get_lead(profile_url)
            
            if not lead:
                print(f"  ⚠️  Profile not found: {profile_url}")
                return False
            
            print(f"  ✓ Found profile: {lead.get('name', 'Unknown')}")
            
            # Update status, note, and sent_at timestamp
            result = self.client.table('leads_list')\
                .update({
                    'note_sent': note_sent,
                    'connection_status': status,
                    'sent_at': datetime.now().isoformat()
                })\
                .eq('profile_url', profile_url)\
                .execute()
            
            print(f"  ✓ Updated outreach status: {status} at {datetime.now().isoformat()}")
            return True
            
        except Exception as e:
            print(f"  ✗ Failed to update outreach: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def lead_exists(self, profile_url):
        """Check if lead already exists in database"""
        try:
            result = self.client.table('leads_list')\
                .select('id')\
                .eq('profile_url', profile_url)\
                .execute()
            
            return len(result.data) > 0
            
        except Exception as e:
            print(f"  ✗ Failed to check lead existence: {e}")
            return False
    
    def get_lead(self, profile_url):
        """Get lead data from database"""
        try:
            result = self.client.table('leads_list')\
                .select('*')\
                .eq('profile_url', profile_url)\
                .execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            print(f"  ✗ Failed to get lead: {e}")
            return None
    
    def update_lead_after_scrape(self, profile_url, profile_data):
        """
        Update lead after scraping (insert or update)
        
        Args:
            profile_url: LinkedIn profile URL
            profile_data: Complete scraped profile data
        
        Returns:
            bool: Success status
        """
        try:
            print(f"  → Checking if lead exists: {profile_url}")
            
            # Check if lead exists
            existing = self.client.table('leads_list')\
                .select('id, name, connection_status')\
                .eq('profile_url', profile_url)\
                .execute()
            
            print(f"  → Existing lead query result: {existing.data}")
            
            name = profile_data.get('name', 'Unknown')
            
            if existing.data and len(existing.data) > 0:
                # Update existing lead
                print(f"  → Updating existing lead: {existing.data[0]}")
                
                update_data = {
                    'name': name,
                    'profile_data': profile_data,
                    'connection_status': 'scraped',
                    'processed_at': datetime.now().isoformat()
                }
                
                result = self.client.table('leads_list')\
                    .update(update_data)\
                    .eq('profile_url', profile_url)\
                    .execute()
                
                print(f"  → Update result: {result.data}")
                
                if result.data:
                    print(f"  ✓ Updated existing lead: {name}")
                    return True
                else:
                    print(f"  ⚠️  Update returned empty data")
                    return False
            else:
                # Insert new lead
                print(f"  → Inserting new lead: {name}")
                
                insert_data = {
                    'profile_url': profile_url,
                    'name': name,
                    'profile_data': profile_data,
                    'connection_status': 'scraped',
                    'date': datetime.now().date().isoformat(),
                    'processed_at': datetime.now().isoformat()
                }
                
                result = self.client.table('leads_list')\
                    .insert(insert_data)\
                    .execute()
                
                print(f"  → Insert result: {result.data}")
                
                if result.data:
                    print(f"  ✓ Inserted new lead: {name}")
                    return True
                else:
                    print(f"  ⚠️  Insert returned empty data")
                    return False
            
        except Exception as e:
            print(f"  ✗ Failed to save to Supabase: {e}")
            print(f"  → Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_lead_by_url(self, profile_url):
        """Get lead by profile URL (alias for get_lead)"""
        return self.get_lead(profile_url)
    
    def get_template_by_id(self, template_id):
        """Get template data by ID"""
        try:
            result = self.client.table('search_templates')\
                .select('*')\
                .eq('id', template_id)\
                .execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            print(f"  ✗ Failed to get template: {e}")
            return None
    
    def get_all_templates(self):
        """Get all available templates"""
        try:
            result = self.client.table('search_templates')\
                .select('id, name')\
                .execute()
            
            return result.data or []
            
        except Exception as e:
            print(f"  ✗ Failed to get templates: {e}")
            return []
    
    def get_leads_by_template_id(self, template_id, limit=None):
        """Get all leads for a specific template_id with processing status"""
        try:
            query = self.client.table('leads_list')\
                .select('id, profile_url, name, template_id, profile_data, scoring_data, connection_status, score')\
                .eq('template_id', template_id)
            
            if limit:
                query = query.limit(limit)
            
            result = query.execute()
            
            if not result.data:
                return []
            
            # Classify leads by processing status
            leads_with_status = []
            for lead in result.data:
                connection_status = lead.get('connection_status', '')
                profile_data = lead.get('profile_data')
                scoring_data = lead.get('scoring_data')
                score = lead.get('score', 0)
                
                needs_processing = False
                status_reason = []
                
                # Check if data exists (not empty)
                has_profile_data = bool(profile_data and profile_data not in [None, '', '{}', {}])
                has_scoring_data = bool(scoring_data and scoring_data not in [None, '', '{}', {}])
                
                # RULE 1: Check connection_status first
                if connection_status == 'pending':
                    # Status pending = auto queue
                    needs_processing = True
                    status_reason.append("status_pending")
                    
                elif connection_status == 'scraped':
                    # Status scraped = check further
                    
                    # RULE 2: Check if profile_data is empty
                    if not has_profile_data:
                        needs_processing = True
                        status_reason.append("profile_data_empty")
                    
                    # RULE 3: Check if scoring_data is empty
                    if not has_scoring_data:
                        needs_processing = True
                        status_reason.append("scoring_data_empty")
                    
                    # RULE 4: If score is 0 or null, check if scoring_data exists
                    if score is None or score == 0:
                        if not has_scoring_data:
                            # Score 0/null AND no scoring data = need processing
                            needs_processing = True
                            if "scoring_data_empty" not in status_reason:
                                status_reason.append("score_zero_no_data")
                        # else: Score 0 but has scoring data = valid (kandidat tidak cocok), SKIP
                    
                    # If all data exists and score > 0, it's complete
                    if has_profile_data and has_scoring_data and score and score > 0:
                        needs_processing = False
                        status_reason = []
                        
                else:
                    # Other status (failed, etc) - check if needs retry
                    if not has_profile_data:
                        needs_processing = True
                        status_reason.append("profile_data_empty")
                    
                    if not has_scoring_data:
                        needs_processing = True
                        status_reason.append("scoring_data_empty")
                
                lead_info = {
                    'id': lead['id'],
                    'profile_url': lead['profile_url'],
                    'name': lead.get('name', 'Unknown'),
                    'template_id': lead['template_id'],
                    'connection_status': connection_status,
                    'score': score,
                    'has_profile': has_profile_data,
                    'has_scoring': has_scoring_data,
                    'score_percentage': score or 0,
                    'needs_processing': needs_processing,
                    'status_reason': status_reason
                }
                
                leads_with_status.append(lead_info)
            
            return leads_with_status
            
        except Exception as e:
            print(f"  ✗ Failed to get leads by template: {e}")
            return []

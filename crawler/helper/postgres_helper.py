"""PostgreSQL helper for storing crawled data"""
import os
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor, Json
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


class SupabaseManager:
    """PostgreSQL manager (keeping name for compatibility)"""
    
    def __init__(self):
        """Initialize PostgreSQL connection"""
        pass
    
    def save_lead(self, profile_url, name, profile_data, connection_status='scraped', template_id=None):
        """Save crawled profile to leads_list table"""
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Check if lead exists
                cur.execute("SELECT id FROM leads_list WHERE profile_url = %s", (profile_url,))
                existing = cur.fetchone()
                
                if existing:
                    # Update existing lead
                    cur.execute("""
                        UPDATE leads_list 
                        SET name = %s, profile_data = %s, connection_status = %s
                        WHERE profile_url = %s
                        RETURNING *
                    """, (name, Json(profile_data), connection_status, profile_url))
                    print(f"  ✓ Updated existing lead: {name}")
                else:
                    # Insert new lead
                    cur.execute("""
                        INSERT INTO leads_list 
                        (profile_url, name, profile_data, connection_status, template_id, date)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING *
                    """, (profile_url, name, Json(profile_data), connection_status, template_id, datetime.now().date()))
                    print(f"  ✓ Saved new lead: {name}")
                
                conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"  ✗ Failed to save to database: {e}")
            return False
    
    def update_connection_status(self, profile_url, status):
        """Update connection status for a lead"""
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE leads_list 
                    SET connection_status = %s
                    WHERE profile_url = %s
                """, (status, profile_url))
                conn.commit()
            conn.close()
            print(f"  ✓ Updated status: {status}")
            return True
        except Exception as e:
            print(f"  ✗ Failed to update status: {e}")
            return False
    
    def update_outreach_status(self, profile_url, note_sent, status='success'):
        """Update lead after outreach"""
        try:
            lead = self.get_lead(profile_url)
            if not lead:
                print(f"  ⚠️  Profile not found: {profile_url}")
                return False
            
            print(f"  ✓ Found profile: {lead.get('name', 'Unknown')}")
            
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE leads_list 
                    SET note_sent = %s, connection_status = %s, sent_at = %s
                    WHERE profile_url = %s
                """, (note_sent, status, datetime.now(), profile_url))
                conn.commit()
            conn.close()
            
            print(f"  ✓ Updated outreach status: {status}")
            return True
        except Exception as e:
            print(f"  ✗ Failed to update outreach: {e}")
            return False
    
    def lead_exists(self, profile_url):
        """Check if lead exists"""
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM leads_list WHERE profile_url = %s", (profile_url,))
                exists = cur.fetchone() is not None
            conn.close()
            return exists
        except Exception as e:
            print(f"  ✗ Failed to check lead existence: {e}")
            return False
    
    def get_lead(self, profile_url):
        """Get lead data from database"""
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM leads_list WHERE profile_url = %s", (profile_url,))
                lead = cur.fetchone()
            conn.close()
            return dict(lead) if lead else None
        except Exception as e:
            print(f"  ✗ Failed to get lead: {e}")
            return None
    
    def update_lead_after_scrape(self, profile_url, profile_data):
        """Update lead after scraping"""
        try:
            print(f"  → Checking if lead exists: {profile_url}")
            
            conn = get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, name, connection_status FROM leads_list WHERE profile_url = %s", (profile_url,))
                existing = cur.fetchone()
                
                name = profile_data.get('name', 'Unknown')
                
                if existing:
                    print(f"  → Updating existing lead: {dict(existing)}")
                    cur.execute("""
                        UPDATE leads_list 
                        SET name = %s, profile_data = %s, connection_status = 'scraped', processed_at = %s
                        WHERE profile_url = %s
                        RETURNING *
                    """, (name, Json(profile_data), datetime.now(), profile_url))
                    result = cur.fetchone()
                    print(f"  ✓ Updated existing lead: {name}")
                else:
                    print(f"  → Inserting new lead: {name}")
                    cur.execute("""
                        INSERT INTO leads_list 
                        (profile_url, name, profile_data, connection_status, date, processed_at)
                        VALUES (%s, %s, %s, 'scraped', %s, %s)
                        RETURNING *
                    """, (profile_url, name, Json(profile_data), datetime.now().date(), datetime.now()))
                    result = cur.fetchone()
                    print(f"  ✓ Inserted new lead: {name}")
                
                conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"  ✗ Failed to save to database: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_lead_by_url(self, profile_url):
        """Get lead by profile URL"""
        return self.get_lead(profile_url)
    
    def get_template_by_id(self, template_id):
        """Get template data by ID"""
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM search_templates WHERE id = %s", (template_id,))
                template = cur.fetchone()
            conn.close()
            return dict(template) if template else None
        except Exception as e:
            print(f"  ✗ Failed to get template: {e}")
            return None
    
    def get_all_templates(self):
        """Get all available templates"""
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, name FROM search_templates")
                templates = cur.fetchall()
            conn.close()
            return [dict(row) for row in templates]
        except Exception as e:
            print(f"  ✗ Failed to get templates: {e}")
            return []
    
    def get_leads_by_template_id(self, template_id, limit=None):
        """Get all leads for a specific template_id with processing status"""
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT id, profile_url, name, template_id, profile_data, 
                           scoring_data, connection_status, score
                    FROM leads_list
                    WHERE template_id = %s
                """
                if limit:
                    query += f" LIMIT {limit}"
                
                cur.execute(query, (template_id,))
                leads = cur.fetchall()
            conn.close()
            
            # Process leads with status
            leads_with_status = []
            for lead in leads:
                lead_dict = dict(lead)
                connection_status = lead_dict.get('connection_status', '')
                profile_data = lead_dict.get('profile_data')
                scoring_data = lead_dict.get('scoring_data')
                score = lead_dict.get('score', 0)
                
                needs_processing = False
                status_reason = []
                
                has_profile_data = bool(profile_data and profile_data not in [None, '', '{}', {}])
                has_scoring_data = bool(scoring_data and scoring_data not in [None, '', '{}', {}])
                
                if connection_status == 'pending':
                    needs_processing = True
                    status_reason.append("status_pending")
                elif connection_status == 'scraped':
                    if not has_profile_data:
                        needs_processing = True
                        status_reason.append("profile_data_empty")
                    if not has_scoring_data:
                        needs_processing = True
                        status_reason.append("scoring_data_empty")
                    if score is None or score == 0:
                        if not has_scoring_data:
                            needs_processing = True
                            if "scoring_data_empty" not in status_reason:
                                status_reason.append("score_zero_no_data")
                    if has_profile_data and has_scoring_data and score and score > 0:
                        needs_processing = False
                        status_reason = []
                else:
                    if not has_profile_data:
                        needs_processing = True
                        status_reason.append("profile_data_empty")
                    if not has_scoring_data:
                        needs_processing = True
                        status_reason.append("scoring_data_empty")
                
                lead_info = {
                    'id': lead_dict['id'],
                    'profile_url': lead_dict['profile_url'],
                    'name': lead_dict.get('name', 'Unknown'),
                    'template_id': lead_dict['template_id'],
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

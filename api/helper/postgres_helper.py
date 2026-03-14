"""
PostgreSQL Helper for API
Centralized database operations using psycopg2
"""
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import os
from datetime import datetime


def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        database=os.getenv('POSTGRES_DB', 'hrd_system'),
        user=os.getenv('POSTGRES_USER', 'hrd_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'hrd_password_change_me')
    )


class ScheduleManager:
    """Manage crawler schedules in PostgreSQL"""
    
    @staticmethod
    def get_all_simple() -> List[Dict]:
        """Get all schedules with template names (using JOIN)"""
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        cs.*,
                        st.id as template_id,
                        st.name as template_name
                    FROM crawler_schedules cs
                    LEFT JOIN search_templates st ON cs.template_id = st.id
                    ORDER BY cs.created_at DESC
                """)
                schedules = cur.fetchall()
            conn.close()
            return [dict(row) for row in schedules]
        except Exception as e:
            print(f"Error getting schedules: {e}")
            return []
    
    @staticmethod
    def get_by_id(schedule_id: str) -> Optional[Dict]:
        """Get schedule by ID"""
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        cs.*,
                        st.id as template_id,
                        st.name as template_name
                    FROM crawler_schedules cs
                    LEFT JOIN search_templates st ON cs.template_id = st.id
                    WHERE cs.id = %s
                """, (schedule_id,))
                schedule = cur.fetchone()
            conn.close()
            return dict(schedule) if schedule else None
        except Exception as e:
            print(f"Error getting schedule: {e}")
            return None
    
    @staticmethod
    def create(data: Dict) -> Dict:
        """Create new schedule"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO crawler_schedules 
                    (name, start_schedule, stop_schedule, status, profile_urls, max_workers, template_id)
                    VALUES (%(name)s, %(start_schedule)s, %(stop_schedule)s, %(status)s, %(profile_urls)s, %(max_workers)s, %(template_id)s)
                    RETURNING *
                """, data)
                schedule = cur.fetchone()
                conn.commit()
            return dict(schedule) if schedule else None
        finally:
            conn.close()
    
    @staticmethod
    def update(schedule_id: str, data: Dict) -> Dict:
        """Update schedule"""
        conn = get_db_connection()
        try:
            # Build SET clause dynamically
            set_parts = []
            values = []
            for key, value in data.items():
                set_parts.append(f"{key} = %s")
                values.append(value)
            
            values.append(schedule_id)
            
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(f"""
                    UPDATE crawler_schedules 
                    SET {', '.join(set_parts)}
                    WHERE id = %s
                    RETURNING *
                """, values)
                schedule = cur.fetchone()
                conn.commit()
            return dict(schedule) if schedule else None
        finally:
            conn.close()
    
    @staticmethod
    def delete(schedule_id: str) -> bool:
        """Delete schedule"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM crawler_schedules WHERE id = %s", (schedule_id,))
                deleted = cur.rowcount > 0
                conn.commit()
            return deleted
        except Exception as e:
            print(f"Error deleting schedule: {e}")
            raise e
        finally:
            conn.close()
    
    @staticmethod
    def template_exists(template_id: str) -> bool:
        """Check if template exists"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM search_templates WHERE id = %s", (template_id,))
                exists = cur.fetchone() is not None
            return exists
        finally:
            conn.close()
    
    @staticmethod
    def update_schedule_status(schedule_id: str, is_active: bool) -> bool:
        """Update schedule status (active/inactive)"""
        try:
            status = 'active' if is_active else 'paused'
            result = ScheduleManager.update(schedule_id, {'status': status})
            
            if result:
                print(f"✅ Schedule {schedule_id} status updated to: {status}")
                return True
            else:
                print(f"⚠️ No schedule found with ID: {schedule_id}")
                return False
        except Exception as e:
            print(f"❌ Error updating schedule status: {e}")
            return False


class LeadsManager:
    """Manage leads in PostgreSQL"""
    
    @staticmethod
    def get_by_template(template_id: str, limit: int = 100, offset: int = 0) -> Dict:
        """Get leads by template ID"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get leads
                cur.execute("""
                    SELECT * FROM leads_list
                    WHERE template_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (template_id, limit, offset))
                leads = cur.fetchall()
                
                # Get total count
                cur.execute("""
                    SELECT COUNT(*) as total FROM leads_list
                    WHERE template_id = %s
                """, (template_id,))
                total = cur.fetchone()['total']
                
                # Get template info
                cur.execute("""
                    SELECT * FROM search_templates WHERE id = %s
                """, (template_id,))
                template = cur.fetchone()
            
            return {
                'template': dict(template) if template else None,
                'leads': [dict(row) for row in leads],
                'total': total
            }
        finally:
            conn.close()


class SupabaseManager:
    """
    Lead management for API (PostgreSQL version)
    """
    def __init__(self):
        pass
    
    def get_leads_by_template_id(self, template_id: str, limit=None):
        """Get leads for a template with processing status"""
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT * FROM leads_list 
                    WHERE template_id = %s
                    ORDER BY created_at DESC
                """
                if limit:
                    query += f" LIMIT {limit}"
                
                cur.execute(query, (template_id,))
                leads = cur.fetchall()
            conn.close()
            
            # Add needs_processing flag
            result = []
            for lead in leads:
                lead_dict = dict(lead)
                profile_data = lead_dict.get('profile_data')
                scoring_data = lead_dict.get('scoring_data')
                connection_status = lead_dict.get('connection_status', '')
                score = lead_dict.get('score', 0)
                
                needs_processing = False
                
                if connection_status == 'pending':
                    needs_processing = True
                    lead_dict['status_reason'] = 'status_pending'
                elif connection_status == 'scraped':
                    if not profile_data or profile_data in [None, '', {}, '{}']:
                        needs_processing = True
                        lead_dict['status_reason'] = 'profile_data_empty'
                    elif not scoring_data or scoring_data in [None, '', {}, '{}']:
                        needs_processing = True
                        lead_dict['status_reason'] = 'scoring_data_empty'
                    elif score == 0 or score is None:
                        if not scoring_data or scoring_data in [None, '', {}, '{}']:
                            needs_processing = True
                            lead_dict['status_reason'] = 'score_zero_no_data'
                        else:
                            needs_processing = False
                            lead_dict['status_reason'] = 'score_zero_valid'
                    else:
                        needs_processing = False
                        lead_dict['status_reason'] = 'complete'
                else:
                    if not profile_data or profile_data in [None, '', {}, '{}']:
                        needs_processing = True
                        lead_dict['status_reason'] = 'profile_data_empty'
                    elif not scoring_data or scoring_data in [None, '', {}, '{}']:
                        needs_processing = True
                        lead_dict['status_reason'] = 'scoring_data_empty'
                
                lead_dict['needs_processing'] = needs_processing
                result.append(lead_dict)
            
            return result
        except Exception as e:
            print(f"Error getting leads: {e}")
            raise e
    
    def get_template_by_id(self, template_id: str):
        """Get template by ID"""
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM search_templates WHERE id = %s", (template_id,))
                template = cur.fetchone()
            conn.close()
            return dict(template) if template else None
        except Exception as e:
            print(f"Error getting template: {e}")
            return None
    
    def get_all_templates(self):
        """Get all templates"""
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM search_templates ORDER BY created_at DESC")
                templates = cur.fetchall()
            conn.close()
            return [dict(row) for row in templates]
        except Exception as e:
            print(f"Error getting templates: {e}")
            return []

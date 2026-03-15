"""
Database handler for scheduler using PostgreSQL
"""
import os
import psycopg2
import psycopg2.extras
from typing import Optional, Dict, List, Any
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from dotenv import load_dotenv
import json

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


class Database:
    def __init__(self):
        # Test connection
        try:
            conn = get_db_connection()
            conn.close()
        except Exception as e:
            raise ValueError(f"Failed to connect to PostgreSQL: {e}")
    
    def init_db(self):
        """Database schema is initialized via init-db/01-init.sql on container startup"""
        print("✓ Database schema ready (auto-initialized via Docker)")
    
    def create_schedule(
        self,
        name: str,
        start_schedule: str,
        stop_schedule: Optional[str] = None,
        profile_urls: List[str] = None,
        max_workers: int = 3,
        template_id: Optional[str] = None,
        external_source: Optional[str] = None,
        webhook_url: Optional[str] = None
    ) -> str:
        """Create new schedule"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO crawler_schedules 
                    (name, template_id, start_schedule, status, external_source, webhook_url)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    name, template_id, start_schedule, 'active', external_source, webhook_url
                ))
                
                result = cur.fetchone()
                conn.commit()
                
                if not result:
                    raise Exception("Failed to create schedule")
                
                return str(result['id'])
        finally:
            conn.close()
    
    def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """Get schedule by ID"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM crawler_schedules WHERE id = %s", (schedule_id,))
                schedule = cur.fetchone()
                
                if not schedule:
                    return None
                
                schedule_dict = dict(schedule)
                
                # Ensure template_id exists
                if 'template_id' not in schedule_dict or not schedule_dict['template_id']:
                    print(f"⚠️ Schedule {schedule_id} missing template_id")
                    return None
                
                return schedule_dict
        finally:
            conn.close()
    
    def get_all_schedules(self) -> List[Dict[str, Any]]:
        """Get all schedules"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM crawler_schedules ORDER BY created_at DESC")
                schedules = cur.fetchall()
            return [dict(row) for row in schedules]
        finally:
            conn.close()
    
    def get_active_schedules(self) -> List[Dict[str, Any]]:
        """Get only active schedules"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM crawler_schedules WHERE status = 'active'")
                schedules = cur.fetchall()
            
            schedules_list = [dict(row) for row in schedules]
            
            # Filter out schedules without template_id
            valid_schedules = [s for s in schedules_list if s.get('template_id')]
            
            if len(schedules_list) != len(valid_schedules):
                print(f"⚠️ Filtered out {len(schedules_list) - len(valid_schedules)} schedules without template_id")
            
            return valid_schedules
        finally:
            conn.close()
    
    def update_schedule(self, schedule_id: str, updates: Dict[str, Any]):
        """Update schedule"""
        conn = get_db_connection()
        try:
            # Build SET clause
            set_parts = []
            values = []
            for key, value in updates.items():
                set_parts.append(f"{key} = %s")
                values.append(value)
            
            # Add updated_at
            set_parts.append("updated_at = %s")
            values.append(datetime.now())
            values.append(schedule_id)
            
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE crawler_schedules 
                    SET {', '.join(set_parts)}
                    WHERE id = %s
                """, values)
                
                if cur.rowcount == 0:
                    raise Exception(f"Schedule {schedule_id} not found")
                
                conn.commit()
        finally:
            conn.close()
    
    def delete_schedule(self, schedule_id: str):
        """Delete schedule (cascade will delete history)"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM crawler_schedules WHERE id = %s", (schedule_id,))
                conn.commit()
        finally:
            conn.close()
    
    def update_last_run(self, schedule_id: str):
        """Update last run timestamp"""
        self.update_schedule(schedule_id, {"last_run": datetime.now()})
    
    def add_crawl_history(
        self,
        profile_url: str,
        status: str,
        schedule_id: Optional[str] = None,
        error_message: Optional[str] = None,
        output_file: Optional[str] = None
    ) -> str:
        """Add crawl history entry"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                completed_at = datetime.now() if status in ["completed", "failed"] else None
                
                cur.execute("""
                    INSERT INTO crawler_history 
                    (schedule_id, profile_url, status, error_message, output_file, completed_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (schedule_id, profile_url, status, error_message, output_file, completed_at))
                
                result = cur.fetchone()
                conn.commit()
                
                if not result:
                    raise Exception("Failed to create crawl history")
                
                return str(result['id'])
        finally:
            conn.close()
    
    def update_crawl_history(self, history_id: str, updates: Dict[str, Any]):
        """Update crawl history"""
        conn = get_db_connection()
        try:
            if "status" in updates and updates["status"] in ["completed", "failed"]:
                updates["completed_at"] = datetime.now()
            
            # Build SET clause
            set_parts = []
            values = []
            for key, value in updates.items():
                set_parts.append(f"{key} = %s")
                values.append(value)
            
            values.append(history_id)
            
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE crawler_history 
                    SET {', '.join(set_parts)}
                    WHERE id = %s
                """, values)
                conn.commit()
        finally:
            conn.close()
    
    def get_crawl_history(
        self,
        schedule_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get crawl history"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if schedule_id:
                    cur.execute("""
                        SELECT * FROM crawler_history 
                        WHERE schedule_id = %s
                        ORDER BY started_at DESC
                        LIMIT %s
                    """, (schedule_id, limit))
                else:
                    cur.execute("""
                        SELECT * FROM crawler_history 
                        ORDER BY started_at DESC
                        LIMIT %s
                    """, (limit,))
                
                history = cur.fetchall()
            return [dict(row) for row in history]
        finally:
            conn.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get crawler statistics"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Total schedules
                cur.execute("SELECT COUNT(*) as count FROM crawler_schedules")
                total_schedules = cur.fetchone()['count']
                
                # Active schedules
                cur.execute("SELECT COUNT(*) as count FROM crawler_schedules WHERE status = 'active'")
                active_schedules = cur.fetchone()['count']
                
                # Total crawls
                cur.execute("SELECT COUNT(*) as count FROM crawler_history")
                total_crawls = cur.fetchone()['count']
                
                # Successful crawls
                cur.execute("SELECT COUNT(*) as count FROM crawler_history WHERE status = 'completed'")
                successful_crawls = cur.fetchone()['count']
                
                # Failed crawls
                cur.execute("SELECT COUNT(*) as count FROM crawler_history WHERE status = 'failed'")
                failed_crawls = cur.fetchone()['count']
            
            return {
                "total_schedules": total_schedules,
                "active_schedules": active_schedules,
                "paused_schedules": total_schedules - active_schedules,
                "total_crawls": total_crawls,
                "successful_crawls": successful_crawls,
                "failed_crawls": failed_crawls,
                "success_rate": round(successful_crawls / total_crawls * 100, 1) if total_crawls > 0 else 0
            }
        finally:
            conn.close()
    
    # ============================================================================
    # SEARCH TEMPLATES METHODS
    # ============================================================================
    
    def get_all_templates(self) -> List[Dict[str, Any]]:
        """Get all search templates"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM search_templates ORDER BY created_at DESC")
                templates = cur.fetchall()
            return [dict(row) for row in templates]
        finally:
            conn.close()
    
    def get_template_by_id(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Get template by ID"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM search_templates WHERE id = %s", (template_id,))
                template = cur.fetchone()
                return dict(template) if template else None
        finally:
            conn.close()
    
    def create_template(self, template_data: Dict[str, Any]) -> str:
        """Create new search template"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO search_templates 
                    (company_id, name, job_title, url, note, job_description, requirements, external_source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    template_data.get('company_id'),
                    template_data.get('name'),
                    template_data.get('job_title'),
                    template_data.get('url'),
                    template_data.get('note'),
                    template_data.get('job_description'),
                    json.dumps(template_data.get('requirements', {})),
                    template_data.get('external_source')
                ))
                
                result = cur.fetchone()
                conn.commit()
                return str(result['id'])
        finally:
            conn.close()
    
    def update_template(self, template_id: str, updates: Dict[str, Any]):
        """Update search template"""
        conn = get_db_connection()
        try:
            set_parts = []
            values = []
            for key, value in updates.items():
                if key == 'requirements':
                    set_parts.append(f"{key} = %s")
                    values.append(json.dumps(value))
                else:
                    set_parts.append(f"{key} = %s")
                    values.append(value)
            
            values.append(template_id)
            
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE search_templates 
                    SET {', '.join(set_parts)}
                    WHERE id = %s
                """, values)
                
                if cur.rowcount == 0:
                    raise Exception(f"Template {template_id} not found")
                
                conn.commit()
        finally:
            conn.close()
    
    def get_template_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get template by name"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM search_templates WHERE name = %s", (name,))
                template = cur.fetchone()
                return dict(template) if template else None
        finally:
            conn.close()
    
    # ============================================================================
    # LEADS METHODS
    # ============================================================================
    
    def get_leads_by_template_id(self, template_id: str) -> List[Dict[str, Any]]:
        """Get leads by template ID"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM leads_list WHERE template_id = %s ORDER BY date DESC", (template_id,))
                leads = cur.fetchall()
            return [dict(row) for row in leads]
        finally:
            conn.close()
    
    def get_lead_by_url(self, profile_url: str) -> Optional[Dict[str, Any]]:
        """Get lead by profile URL"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM leads_list WHERE profile_url = %s", (profile_url,))
                lead = cur.fetchone()
                return dict(lead) if lead else None
        finally:
            conn.close()
    
    def update_lead(self, profile_url: str, updates: Dict[str, Any]):
        """Update lead by profile URL"""
        conn = get_db_connection()
        try:
            set_parts = []
            values = []
            for key, value in updates.items():
                if key in ['profile_data', 'scoring_data']:
                    set_parts.append(f"{key} = %s")
                    values.append(json.dumps(value))
                else:
                    set_parts.append(f"{key} = %s")
                    values.append(value)
            
            values.append(profile_url)
            
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE leads_list 
                    SET {', '.join(set_parts)}
                    WHERE profile_url = %s
                """, values)
                conn.commit()
        finally:
            conn.close()
    
    def create_lead(self, lead_data: Dict[str, Any]) -> str:
        """Create new lead"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO leads_list 
                    (template_id, date, name, note_sent, search_url, profile_url, connection_status, score, profile_data, scoring_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    lead_data.get('template_id'),
                    lead_data.get('date'),
                    lead_data.get('name'),
                    lead_data.get('note_sent'),
                    lead_data.get('search_url'),
                    lead_data.get('profile_url'),
                    lead_data.get('connection_status', 'pending'),
                    lead_data.get('score'),
                    json.dumps(lead_data.get('profile_data', {})),
                    json.dumps(lead_data.get('scoring_data', {}))
                ))
                
                result = cur.fetchone()
                conn.commit()
                return str(result['id'])
        finally:
            conn.close()
    # ============================================================================
    # STATS METHODS (for Dashboard)
    # ============================================================================
    
    def get_leads_count(self) -> int:
        """Get total count of leads"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM leads_list")
                return cur.fetchone()[0]
        finally:
            conn.close()
    
    def get_templates_count(self) -> int:
        """Get total count of templates"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM search_templates")
                return cur.fetchone()[0]
        finally:
            conn.close()
    
    def get_companies_count(self) -> int:
        """Get total count of companies"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM companies")
                return cur.fetchone()[0]
        finally:
            conn.close()
    
    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Get comprehensive dashboard statistics"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Basic counts
                cur.execute("""
                    SELECT 
                        (SELECT COUNT(*) FROM leads_list) as leads_count,
                        (SELECT COUNT(*) FROM search_templates) as templates_count,
                        (SELECT COUNT(*) FROM companies) as companies_count,
                        (SELECT COUNT(*) FROM crawler_schedules) as schedules_count
                """)
                counts = cur.fetchone()
                
                # Leads by status for charts
                cur.execute("""
                    SELECT connection_status, COUNT(*) as count 
                    FROM leads_list 
                    GROUP BY connection_status
                """)
                leads_by_status = {row['connection_status']: row['count'] for row in cur.fetchall()}
                
                # Recent leads (last 7 days)
                cur.execute("""
                    SELECT DATE(date) as date, COUNT(*) as count 
                    FROM leads_list 
                    WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                    GROUP BY DATE(date)
                    ORDER BY date
                """)
                recent_leads = [dict(row) for row in cur.fetchall()]
                
                return {
                    "counts": dict(counts),
                    "leads_by_status": leads_by_status,
                    "recent_leads": recent_leads
                }
        finally:
            conn.close()
    
    # ============================================================================
    # LEADS METHODS (Enhanced)
    # ============================================================================
    
    def get_all_leads(self, template_id: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all leads with optional filtering"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM leads_list"
                params = []
                
                if template_id:
                    query += " WHERE template_id = %s"
                    params.append(template_id)
                
                query += " ORDER BY date DESC"
                
                if limit:
                    query += " LIMIT %s"
                    params.append(limit)
                
                cur.execute(query, params)
                leads = cur.fetchall()
            return [dict(row) for row in leads]
        finally:
            conn.close()
    
    # ============================================================================
    # COMPANIES METHODS
    # ============================================================================
    
    def get_all_companies(self) -> List[Dict[str, Any]]:
        """Get all companies"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM companies ORDER BY name")
                companies = cur.fetchall()
            return [dict(row) for row in companies]
        finally:
            conn.close()
    
    def create_company(self, company_data: Dict[str, Any]) -> str:
        """Create new company"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO companies (name, code)
                    VALUES (%s, %s)
                    RETURNING id
                """, (
                    company_data.get('name'),
                    company_data.get('code')
                ))
                
                result = cur.fetchone()
                conn.commit()
                return str(result['id'])
        finally:
            conn.close()
    
    # ============================================================================
    # TEMPLATES METHODS (Enhanced)
    # ============================================================================
    
    def delete_template(self, template_id: str):
        """Delete search template"""
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM search_templates WHERE id = %s", (template_id,))
                
                if cur.rowcount == 0:
                    raise Exception(f"Template {template_id} not found")
                
                conn.commit()
        finally:
            conn.close()
    
    # ============================================================================
    # USER AUTHENTICATION METHODS
    # ============================================================================
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE email = %s AND is_active = true", (email,))
                user = cur.fetchone()
                return dict(user) if user else None
        finally:
            conn.close()
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, email, name, role, created_at FROM users WHERE id = %s AND is_active = true", (user_id,))
                user = cur.fetchone()
                return dict(user) if user else None
        finally:
            conn.close()
    
    def create_user(self, user_data: Dict[str, Any]) -> str:
        """Create new user"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO users (email, password_hash, name, role)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (
                    user_data.get('email'),
                    user_data.get('password_hash'),
                    user_data.get('name'),
                    user_data.get('role', 'user')
                ))
                
                result = cur.fetchone()
                conn.commit()
                return str(result['id'])
        finally:
            conn.close()
"""
Database handler for scheduler using PostgreSQL
"""
import os
from typing import Optional, Dict, List, Any
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
        max_workers: int = 3
    ) -> str:
        """Create new schedule"""
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO crawler_schedules 
                    (name, start_schedule, stop_schedule, status, profile_urls, max_workers)
                    VALUES (%s, %s, %s, 'active', %s, %s)
                    RETURNING id
                """, (name, start_schedule, stop_schedule, Json(profile_urls or []), max_workers))
                
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

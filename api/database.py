"""
Database handler for scheduler using PostgreSQL
Migrated from Supabase to PostgreSQL with psycopg2
"""
import os
import psycopg2
import psycopg2.extras
from typing import Optional, Dict, List, Any
from datetime import datetime
from dotenv import load_dotenv
import json

load_dotenv()


class Database:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('POSTGRES_DB', 'linkedin_crawler'),
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', 'password123')
        }
        
        # Test connection
        self._test_connection()
    
    def _test_connection(self):
        """Test database connection"""
        try:
            conn = psycopg2.connect(**self.db_config)
            conn.close()
            print("✓ PostgreSQL connection successful")
        except Exception as e:
            raise ValueError(f"Failed to connect to PostgreSQL: {e}")
    
    def _get_connection(self):
        """Get database connection"""
        return psycopg2.connect(**self.db_config)
    
    def init_db(self):
        """Database schema is initialized via init.sql in Docker"""
        print("✓ Database schema ready (initialized via Docker)")
    
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
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO crawler_schedules 
                    (name, template_id, start_schedule, stop_schedule, status, profile_urls, max_workers, external_source, webhook_url, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    name, template_id, start_schedule, stop_schedule, 'active',
                    json.dumps(profile_urls or []), max_workers, external_source, webhook_url,
                    datetime.now()
                ))
                
                result = cur.fetchone()
                conn.commit()
                return str(result['id'])
        finally:
            conn.close()
    
    def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """Get schedule by ID"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM crawler_schedules WHERE id = %s", (schedule_id,))
                result = cur.fetchone()
                
                if not result:
                    return None
                
                schedule = dict(result)
                
                # Ensure template_id exists (required for scheduler)
                if not schedule.get('template_id'):
                    print(f"⚠️ Schedule {schedule_id} missing template_id")
                    return None
                
                return schedule
        finally:
            conn.close()
    
    def get_all_schedules(self) -> List[Dict[str, Any]]:
        """Get all schedules"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM crawler_schedules ORDER BY created_at DESC")
                results = cur.fetchall()
                return [dict(row) for row in results]
        finally:
            conn.close()
    
    def get_active_schedules(self) -> List[Dict[str, Any]]:
        """Get only active schedules"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM crawler_schedules WHERE status = 'active'")
                results = cur.fetchall()
                schedules = [dict(row) for row in results]
                
                # Filter out schedules without template_id
                valid_schedules = [s for s in schedules if s.get('template_id')]
                
                if len(schedules) != len(valid_schedules):
                    print(f"⚠️ Filtered out {len(schedules) - len(valid_schedules)} schedules without template_id")
                
                return valid_schedules
        finally:
            conn.close()
    
    def update_schedule(self, schedule_id: str, updates: Dict[str, Any]):
        """Update schedule"""
        if not updates:
            return
        
        updates["updated_at"] = datetime.now()
        
        # Build dynamic UPDATE query
        set_clauses = []
        values = []
        
        for key, value in updates.items():
            set_clauses.append(f"{key} = %s")
            if key == 'profile_urls' and isinstance(value, list):
                values.append(json.dumps(value))
            else:
                values.append(value)
        
        values.append(schedule_id)
        
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                query = f"UPDATE crawler_schedules SET {', '.join(set_clauses)} WHERE id = %s"
                cur.execute(query, values)
                
                if cur.rowcount == 0:
                    raise Exception(f"Schedule {schedule_id} not found")
                
                conn.commit()
        finally:
            conn.close()
    
    def delete_schedule(self, schedule_id: str):
        """Delete schedule (cascade will delete history)"""
        conn = self._get_connection()
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
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                completed_at = datetime.now() if status in ["completed", "failed"] else None
                
                cur.execute("""
                    INSERT INTO crawler_history 
                    (schedule_id, profile_url, status, error_message, output_file, completed_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (schedule_id, profile_url, status, error_message, output_file, completed_at))
                
                result = cur.fetchone()
                conn.commit()
                return str(result['id'])
        finally:
            conn.close()
    
    def update_crawl_history(self, history_id: str, updates: Dict[str, Any]):
        """Update crawl history"""
        if "status" in updates and updates["status"] in ["completed", "failed"]:
            updates["completed_at"] = datetime.now()
        
        if not updates:
            return
        
        # Build dynamic UPDATE query
        set_clauses = []
        values = []
        
        for key, value in updates.items():
            set_clauses.append(f"{key} = %s")
            values.append(value)
        
        values.append(history_id)
        
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                query = f"UPDATE crawler_history SET {', '.join(set_clauses)} WHERE id = %s"
                cur.execute(query, values)
                conn.commit()
        finally:
            conn.close()
    
    def get_crawl_history(
        self,
        schedule_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get crawl history"""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
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
                
                results = cur.fetchall()
                return [dict(row) for row in results]
        finally:
            conn.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get crawler statistics"""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Total schedules
                cur.execute("SELECT COUNT(*) FROM crawler_schedules")
                total_schedules = cur.fetchone()[0]
                
                # Active schedules
                cur.execute("SELECT COUNT(*) FROM crawler_schedules WHERE status = 'active'")
                active_schedules = cur.fetchone()[0]
                
                # Total crawls
                cur.execute("SELECT COUNT(*) FROM crawler_history")
                total_crawls = cur.fetchone()[0]
                
                # Successful crawls
                cur.execute("SELECT COUNT(*) FROM crawler_history WHERE status = 'completed'")
                successful_crawls = cur.fetchone()[0]
                
                # Failed crawls
                cur.execute("SELECT COUNT(*) FROM crawler_history WHERE status = 'failed'")
                failed_crawls = cur.fetchone()[0]
                
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

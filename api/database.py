"""
Database handler for scheduler using Supabase
"""
import os
from typing import Optional, Dict, List, Any
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


class Database:
    def __init__(self):
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        
        self.client: Client = create_client(supabase_url, supabase_key)
    
    def init_db(self):
        """
        Initialize database tables
        Run this SQL in Supabase SQL Editor:
        
        -- Schedules table
        CREATE TABLE IF NOT EXISTS crawler_schedules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            start_schedule TEXT NOT NULL,
            stop_schedule TEXT,
            status TEXT DEFAULT 'active',
            profile_urls JSONB DEFAULT '[]'::jsonb,
            max_workers INTEGER DEFAULT 3,
            last_run TIMESTAMPTZ,
            next_run TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        
        -- Crawl history table
        CREATE TABLE IF NOT EXISTS crawler_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            schedule_id UUID REFERENCES crawler_schedules(id) ON DELETE CASCADE,
            profile_url TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TIMESTAMPTZ DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            error_message TEXT,
            output_file TEXT
        );
        
        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_schedules_status ON crawler_schedules(status);
        CREATE INDEX IF NOT EXISTS idx_history_schedule ON crawler_history(schedule_id);
        CREATE INDEX IF NOT EXISTS idx_history_status ON crawler_history(status);
        
        -- RLS Policies (optional, adjust based on your needs)
        ALTER TABLE crawler_schedules ENABLE ROW LEVEL SECURITY;
        ALTER TABLE crawler_history ENABLE ROW LEVEL SECURITY;
        
        -- Allow service role to do everything
        CREATE POLICY "Service role can do everything on schedules"
            ON crawler_schedules FOR ALL
            USING (true)
            WITH CHECK (true);
            
        CREATE POLICY "Service role can do everything on history"
            ON crawler_history FOR ALL
            USING (true)
            WITH CHECK (true);
        """
        print("✓ Database schema ready (run SQL in Supabase if tables don't exist)")
    
    def create_schedule(
        self,
        name: str,
        start_schedule: str,
        stop_schedule: Optional[str] = None,
        profile_urls: List[str] = None,
        max_workers: int = 3
    ) -> str:
        """Create new schedule"""
        data = {
            "name": name,
            "start_schedule": start_schedule,
            "stop_schedule": stop_schedule,
            "status": "active",
            "profile_urls": profile_urls or [],
            "max_workers": max_workers,
            "updated_at": datetime.now().isoformat()
        }
        
        result = self.client.table("crawler_schedules").insert(data).execute()
        
        if not result.data:
            raise Exception("Failed to create schedule")
        
        return result.data[0]["id"]
    
    def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """Get schedule by ID"""
        result = self.client.table("crawler_schedules").select("*").eq("id", schedule_id).execute()
        
        if not result.data:
            return None
        
        schedule = result.data[0]
        
        # Ensure template_id exists (required for scheduler)
        if 'template_id' not in schedule or not schedule['template_id']:
            print(f"⚠️ Schedule {schedule_id} missing template_id")
            return None
        
        return schedule
    
    def get_all_schedules(self) -> List[Dict[str, Any]]:
        """Get all schedules"""
        result = self.client.table("crawler_schedules").select("*").order("created_at", desc=True).execute()
        return result.data or []
    
    def get_active_schedules(self) -> List[Dict[str, Any]]:
        """Get only active schedules"""
        result = self.client.table("crawler_schedules").select("*").eq("status", "active").execute()
        schedules = result.data or []
        
        # Filter out schedules without template_id
        valid_schedules = [s for s in schedules if s.get('template_id')]
        
        if len(schedules) != len(valid_schedules):
            print(f"⚠️ Filtered out {len(schedules) - len(valid_schedules)} schedules without template_id")
        
        return valid_schedules
    
    def update_schedule(self, schedule_id: str, updates: Dict[str, Any]):
        """Update schedule"""
        updates["updated_at"] = datetime.now().isoformat()
        
        result = self.client.table("crawler_schedules").update(updates).eq("id", schedule_id).execute()
        
        if not result.data:
            raise Exception(f"Schedule {schedule_id} not found")
    
    def delete_schedule(self, schedule_id: str):
        """Delete schedule (cascade will delete history)"""
        self.client.table("crawler_schedules").delete().eq("id", schedule_id).execute()
    
    def update_last_run(self, schedule_id: str):
        """Update last run timestamp"""
        now = datetime.now().isoformat()
        self.update_schedule(schedule_id, {"last_run": now})
    
    def add_crawl_history(
        self,
        profile_url: str,
        status: str,
        schedule_id: Optional[str] = None,
        error_message: Optional[str] = None,
        output_file: Optional[str] = None
    ) -> str:
        """Add crawl history entry"""
        data = {
            "schedule_id": schedule_id,
            "profile_url": profile_url,
            "status": status,
            "error_message": error_message,
            "output_file": output_file
        }
        
        if status in ["completed", "failed"]:
            data["completed_at"] = datetime.now().isoformat()
        
        result = self.client.table("crawler_history").insert(data).execute()
        
        if not result.data:
            raise Exception("Failed to create crawl history")
        
        return result.data[0]["id"]
    
    def update_crawl_history(self, history_id: str, updates: Dict[str, Any]):
        """Update crawl history"""
        if "status" in updates and updates["status"] in ["completed", "failed"]:
            updates["completed_at"] = datetime.now().isoformat()
        
        self.client.table("crawler_history").update(updates).eq("id", history_id).execute()
    
    def get_crawl_history(
        self,
        schedule_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get crawl history"""
        query = self.client.table("crawler_history").select("*")
        
        if schedule_id:
            query = query.eq("schedule_id", schedule_id)
        
        result = query.order("started_at", desc=True).limit(limit).execute()
        return result.data or []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get crawler statistics"""
        # Total schedules
        schedules_result = self.client.table("crawler_schedules").select("id", count="exact").execute()
        total_schedules = schedules_result.count or 0
        
        # Active schedules
        active_result = self.client.table("crawler_schedules").select("id", count="exact").eq("status", "active").execute()
        active_schedules = active_result.count or 0
        
        # Total crawls
        crawls_result = self.client.table("crawler_history").select("id", count="exact").execute()
        total_crawls = crawls_result.count or 0
        
        # Successful crawls
        success_result = self.client.table("crawler_history").select("id", count="exact").eq("status", "completed").execute()
        successful_crawls = success_result.count or 0
        
        # Failed crawls
        failed_result = self.client.table("crawler_history").select("id", count="exact").eq("status", "failed").execute()
        failed_crawls = failed_result.count or 0
        
        return {
            "total_schedules": total_schedules,
            "active_schedules": active_schedules,
            "paused_schedules": total_schedules - active_schedules,
            "total_crawls": total_crawls,
            "successful_crawls": successful_crawls,
            "failed_crawls": failed_crawls,
            "success_rate": round(successful_crawls / total_crawls * 100, 1) if total_crawls > 0 else 0
        }

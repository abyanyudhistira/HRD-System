"""
FastAPI Backend for LinkedIn Crawler Scheduler
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
import pytz
import os
import sys
import json
import re
import time
import uuid
import logging
from pathlib import Path

# Add crawler to path
sys.path.append(str(Path(__file__).parent.parent / "crawler"))

from scheduler_service import SchedulerService
from database import Database
from helper.rabbitmq_helper import queue_publisher
from helper.postgres_helper import ScheduleManager, LeadsManager
from helper.auth_helper import hash_password, verify_password, create_jwt_token, verify_jwt_token, get_token_from_header
# Remove Supabase imports - migrating to PostgreSQL
# from helper.postgres_helper import ScheduleManager, LeadsManager, SupabaseManager

# Try to import query optimizer (optional) - will be updated for PostgreSQL later
try:
    # from helper.query_optimizer import QueryOptimizer
    # query_optimizer = QueryOptimizer(supabase)
    query_optimizer = None
    QUERY_OPTIMIZER_AVAILABLE = False
    print("⚠ Query optimizer disabled during PostgreSQL migration")
except ImportError:
    query_optimizer = None
    QUERY_OPTIMIZER_AVAILABLE = False
    print("⚠ Query optimizer not available")

# Setup logging
logger = logging.getLogger(__name__)

# Global variable to track current crawl session
current_crawl_session = {
    'is_active': False,
    'source': None,  # 'manual' or 'scheduled'
    'schedule_id': None,
    'schedule_name': None,
    'template_id': None,
    'template_name': None,
    'started_at': None,
    'leads_queued': 0
}

# Error handling decorator
def handle_api_errors(func):
    """Decorator to handle common API errors"""
    from functools import wraps
    
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return wrapper

app = FastAPI(
    title="LinkedIn Crawler API", 
    version="1.0.0",
    description="API for LinkedIn profile crawling, scheduling, and requirements generation",
    tags_metadata=[
        {
            "name": "Health",
            "description": "Health check and system status endpoints"
        },
        {
            "name": "Schedules",
            "description": "Crawler schedule management - create, update, delete, and execute schedules"
        },
        {
            "name": "Scraping",
            "description": "Direct scraping operations and crawler status monitoring"
        },
        {
            "name": "Requirements",
            "description": "Job requirements generation and management for candidate scoring"
        },
        {
            "name": "External Integration",
            "description": "External platform integration endpoints (Nara, etc.)"
        },
        {
            "name": "Outreach",
            "description": "Candidate outreach and messaging operations"
        }
    ]
)

# CORS - Allow Vercel and localhost
ALLOWED_ORIGINS = [
    os.getenv("FRONTEND_URL", "http://localhost:3000"),  # From env or default
    "http://localhost:3000",  # Local dev primary
    "http://localhost:3001",  # Local dev alternate
    "https://*.vercel.app",  # All Vercel preview deployments
]

# Parse CORS_ORIGINS from env (comma-separated)
cors_origins_env = os.getenv("CORS_ORIGINS", "")
if cors_origins_env:
    ALLOWED_ORIGINS.extend([origin.strip() for origin in cors_origins_env.split(",") if origin.strip()])

# Filter out empty strings and duplicates
ALLOWED_ORIGINS = list(set([origin for origin in ALLOWED_ORIGINS if origin]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",  # Regex for Vercel domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
db = None
scheduler = None
background_task_running = False

# Security
security = HTTPBearer()

# Current crawl session tracking
current_crawl_session = {
    'is_running': False,
    'template_id': None,
    'template_name': None,
    'started_at': None,
    'leads_queued': 0
}

# ============================================================================
# AUTHENTICATION DEPENDENCY
# ============================================================================

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Dependency to get current authenticated user"""
    token = credentials.credentials
    user_data = verify_jwt_token(token)
    
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    # Get fresh user data from database
    user = db.get_user_by_id(user_data['user_id'])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

# Auth Models
class LoginRequest(BaseModel):
    email: str = Field(..., json_schema_extra={"example": "admin@hrd.com"})
    password: str = Field(..., json_schema_extra={"example": "admin123"})

class LoginResponse(BaseModel):
    success: bool
    token: str
    user: Dict[str, Any]

class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str]
    role: str
    created_at: str

# Stats Models
class DashboardStats(BaseModel):
    leads_count: int
    templates_count: int
    companies_count: int
    schedules_count: int
    leads_by_status: Dict[str, int]
    recent_leads: List[Dict[str, Any]]

# Company Models
class CompanyCreate(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "PT Example"})
    code: Optional[str] = Field(None, json_schema_extra={"example": "EXAMPLE"})

async def session_monitor_task():
    """Background task to monitor session completion"""
    global background_task_running
    background_task_running = True
    
    print("🔄 Session monitor task started")
    
    try:
        while background_task_running:
            await asyncio.sleep(10)  # Check every 10 seconds
            await check_and_complete_session()
    except asyncio.CancelledError:
        print("🛑 Session monitor task cancelled")
    except Exception as e:
        print(f"❌ Session monitor task error: {e}")
    finally:
        background_task_running = False
        print("🔄 Session monitor task stopped")

# Try to initialize database and scheduler, but continue without them if it fails
def init_services():
    global db, scheduler
    try:
        db = Database()
        scheduler = SchedulerService(db)
        print("✓ Database and Scheduler initialized")
        return True
    except Exception as e:
        print(f"⚠ Database initialization failed: {e}")
        print("  Running in limited mode (requirements generator only)")
        db = None
        scheduler = None
        return False

# Pydantic models
class RequirementsGenerateRequest(BaseModel):
    job_description: str = Field(
        ...,
        example="We are looking for a debt collector with 2+ years experience in BPR or financial institutions. Requirements: Male/Female, Age 25-35, Education minimum SMA, Experience in debt collection, Good communication skills, Placement in Jakarta.",
        description="Job description text containing requirements"
    )
    position: str = Field(
        ...,
        example="Debt Collector",
        description="Job position title"
    )

class RequirementsSaveRequest(BaseModel):
    requirements: Dict = Field(
        ...,
        example={
            "position": "Debt Collector",
            "requirements": [
                {"id": "req_1", "label": "2+ years experience", "type": "experience", "value": 2}
            ]
        },
        description="Requirements data to save"
    )
    filename: str = Field(
        ...,
        example="debt_collector_requirements",
        description="Filename to save (without .json extension)"
    )

class OutreachRequest(BaseModel):
    leads: List[Dict[str, str]] = Field(
        ...,
        example=[
            {
                "id": "lead-123",
                "name": "John Doe",
                "profile_url": "https://linkedin.com/in/johndoe"
            }
        ],
        description="List of leads to send outreach messages"
    )
    message: str = Field(
        ...,
        example="Hi {name}, we have an exciting opportunity for you...",
        description="Outreach message template (use {name} for personalization)"
    )
    dry_run: bool = Field(
        True,
        example=False,
        description="If true, only simulate sending (for testing)"
    )

class WebhookLeadInsert(BaseModel):
    """Webhook payload from Supabase trigger"""
    type: str = Field(
        ...,
        example="INSERT",
        description="Database operation type"
    )
    table: str = Field(
        ...,
        example="leads_list",
        description="Table name"
    )
    record: Dict = Field(
        ...,
        example={
            "id": "lead-123",
            "name": "John Doe",
            "profile_url": "https://linkedin.com/in/johndoe",
            "template_id": "38a1699d-ad54-4f05-9483-e3d35142d35f"
        },
        description="New lead data"
    )
    old_record: Optional[Dict] = Field(
        None,
        description="Previous record data (for UPDATE operations)"
    )

class ReQueueRequest(BaseModel):
    """Request to re-queue failed leads"""
    template_id: Optional[str] = Field(
        None,
        example="38a1699d-ad54-4f05-9483-e3d35142d35f",
        description="Template ID to filter leads (optional, if not provided will check all)"
    )
    check_profile_data: bool = Field(
        True,
        example=True,
        description="Check for missing profile_data"
    )
    check_scoring_data: bool = Field(
        True,
        example=True,
        description="Check for missing scoring_data"
    )
    dry_run: bool = Field(
        False,
        example=False,
        description="If true, only show what would be re-queued (for testing)"
    )


class InstantCrawlRequest(BaseModel):
    """Request for instant crawling of a single profile"""
    profile_url: str = Field(
        ...,
        example="https://linkedin.com/in/johndoe",
        description="LinkedIn profile URL to crawl"
    )
    template_id: Optional[str] = Field(
        None,
        example="38a1699d-ad54-4f05-9483-e3d35142d35f",
        description="Template ID for scoring (optional)"
    )


class ScrapingRequest(BaseModel):
    """Simple scraping request"""
    template_id: str = Field(..., description="Template ID to scrape", example="38a1699d-ad54-4f05-9483-e3d35142d35f")


class ScrapingResponse(BaseModel):
    """Simple scraping response"""
    success: bool = Field(..., description="Request success", example=True)
    message: str = Field(..., description="Response message", example="25 leads queued for scraping")
    leads_queued: int = Field(..., description="Number of leads queued", example=25)
    batch_id: str = Field(..., description="Batch ID", example="20260305_143022")


class CrawlerStatusResponse(BaseModel):
    """Crawler status response"""
    is_running: bool = Field(..., description="Whether crawler is currently processing")
    queue_size: int = Field(..., description="Number of items in queue")
    template_id: Optional[str] = Field(None, description="Current template being processed")
    template_name: Optional[str] = Field(None, description="Current template name")
    processed_count: int = Field(0, description="Number of leads processed in current batch")


@app.on_event("startup")
async def startup_event():
    """Initialize database and start scheduler"""
    global background_task_running
    
    print("🚀 Starting up API...")
    init_success = init_services()
    print(f"   Database init: {'✓ Success' if init_success else '✗ Failed'}")
    
    if db and scheduler:
        print("   Initializing database tables...")
        db.init_db()
        print("   Starting scheduler service...")
        scheduler.start()
        print("✓ Scheduler started and running")
        print(f"   Scheduler is_running: {scheduler.is_running()}")
    else:
        print("⚠ Running without scheduler (database not available)")
        print(f"   db object: {db}")
        print(f"   scheduler object: {scheduler}")
    
    # Start session monitor background task
    if not background_task_running:
        asyncio.create_task(session_monitor_task())
        print("✓ Session monitor task started")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop scheduler gracefully"""
    global background_task_running
    
    # Stop session monitor task
    background_task_running = False
    print("✓ Session monitor task stopped")
    
    if scheduler:
        scheduler.stop()
        print("✓ Scheduler stopped")


# Health check
@app.get("/", tags=["Health"])
async def root():
    return {
        "message": "LinkedIn Crawler API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "scheduler_running": scheduler.is_running() if scheduler else False,
        "database_available": db is not None,
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# CRAWLER SCHEDULE ENDPOINTS (Direct Supabase Access)
# ============================================================================

class CrawlerScheduleCreate(BaseModel):
    name: str = Field(
        ..., 
        example="Daily Morning Crawl",
        description="Name of the schedule"
    )
    start_schedule: str = Field(
        ..., 
        example="0 9 * * *",
        description="Cron expression (e.g., '0 9 * * *' for daily at 9 AM)"
    )
    template_id: str = Field(
        ...,
        example="38a1699d-ad54-4f05-9483-e3d35142d35f",
        description="Template ID to use for scraping"
    )
    status: Optional[str] = Field(
        default='active',
        example="active",
        description="Schedule status: 'active' or 'inactive'"
    )

class CrawlerScheduleUpdate(BaseModel):
    name: Optional[str] = Field(
        None, 
        example="Updated Schedule Name",
        description="Name of the schedule"
    )
    start_schedule: Optional[str] = Field(
        None, 
        example="0 10 * * *",
        description="Cron expression (e.g., '0 10 * * *' for daily at 10 AM)"
    )
    template_id: Optional[str] = Field(
        None,
        example="38a1699d-ad54-4f05-9483-e3d35142d35f",
        description="Template ID to use for scraping"
    )
    status: Optional[str] = Field(
        None,
        example="inactive",
        description="Schedule status: 'active' or 'inactive'"
    )


class ExternalScheduleRequest(BaseModel):
    job_title: str = Field(
        ...,
        example="Senior Fullstack Engineering",
        description="Job title"
    )
    job_description: str = Field(
        ...,
        description="Full job description text (will be used for both requirements generation and search template description)"
    )
    schedule_date: str = Field(
        ...,
        example="2026-03-15",
        description="Schedule date in YYYY-MM-DD format"
    )
    schedule_time: Optional[str] = Field(
        "09:00",
        example="09:00",
        description="Schedule time in HH:MM format (default: 09:00 - working hours)"
    )
    timezone: Optional[str] = Field(
        "Asia/Jakarta",
        example="Asia/Jakarta",
        description="Timezone for scheduling"
    )
    requirements: Optional[Dict] = Field(
        None,
        example={
            "position": "Senior Fullstack Engineer",
            "min_experience": 3,
            "skills": ["React", "Node.js", "Python"],
            "location": "Jakarta"
        },
        description="Job requirements for scoring"
    )
    webhook_url: Optional[str] = Field(
        None,
        example="https://nara.ai/api/scraping-results",
        description="Webhook URL to send results"
    )
    external_source: Optional[str] = Field(
        "nara",
        example="nara",
        description="Source platform identifier"
    )


@app.get("/api/schedules", tags=["Schedules"])
async def get_schedules(external_source: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    """Get schedules with optional filtering by external_source"""
    try:
        print(f"\n📋 SCHEDULES REQUEST")
        print(f"   External source filter: {external_source}")
        
        # Use PostgreSQL Database class instead of Supabase
        schedules = db.get_all_schedules()
        
        # Filter by external_source
        if external_source == "internal":
            # Internal schedules only (external_source is NULL)
            schedules = [s for s in schedules if not s.get('external_source')]
        elif external_source == "external":
            # All external schedules (external_source is NOT NULL)
            schedules = [s for s in schedules if s.get('external_source')]
        elif external_source:
            # Specific external source (e.g., "nara")
            schedules = [s for s in schedules if s.get('external_source') == external_source]
        # If external_source is None, return all schedules
        
        print(f"   Found {len(schedules)} schedules")
        
        # Format response based on external_source
        formatted_schedules = []
        for schedule in schedules:
            external_metadata = schedule.get('external_metadata', {})
            is_external = bool(schedule.get('external_source'))
            
            if is_external:
                # External schedule format - FIX: Use same key structure as internal
                # Determine execution status based on last_run
                execution_status = "pending"
                if schedule.get('last_run'):
                    execution_status = "completed"  # Assume completed if has last_run
                
                formatted_schedule = {
                    "id": schedule['id'],  # FIX: Use 'id' not 'schedule_id' for consistency
                    "name": schedule['name'],
                    "start_schedule": schedule.get('start_schedule'),
                    "template_id": schedule.get('template_id'),
                    "status": schedule['status'],
                    "last_run": schedule.get('last_run'),
                    "created_at": schedule.get('created_at'),
                    "external_source": schedule.get('external_source'),
                    "external_metadata": external_metadata,
                    "webhook_url": schedule.get('webhook_url'),
                    # Additional external fields for compatibility
                    "job_title": external_metadata.get('job_title') if isinstance(external_metadata, dict) else None,
                    "execution_status": execution_status,
                    "scheduled_for": external_metadata.get('schedule_datetime') if isinstance(external_metadata, dict) else None
                }
                
                print(f"🌐 External schedule: {schedule['name']} (ID: {schedule['id']})")
            else:
                # Internal schedule format (existing format)
                formatted_schedule = {
                    "id": schedule['id'],
                    "name": schedule['name'],
                    "start_schedule": schedule['start_schedule'],
                    "template_id": schedule.get('template_id'),
                    "status": schedule['status'],
                    "last_run": schedule.get('last_run'),
                    "next_run": schedule.get('next_run'),
                    "created_at": schedule.get('created_at'),
                    "external_source": None
                }
                
                print(f"🏠 Internal schedule: {schedule['name']} (ID: {schedule['id']})")
            
            formatted_schedules.append(formatted_schedule)
        
        print(f"✅ Found {len(formatted_schedules)} schedules")
        if external_source:
            print(f"   Filtered by external_source: {external_source}")
        
        return {
            "success": True,
            "count": len(formatted_schedules),
            "schedules": formatted_schedules
        }
        
    except Exception as e:
        print(f"❌ Schedules request failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/schedules/{schedule_id}", tags=["Schedules"])
@handle_api_errors
async def get_schedule(schedule_id: str, current_user: dict = Depends(get_current_user)):
    """Get specific schedule by ID"""
    schedule = ScheduleManager.get_by_id(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    return {"success": True, "schedule": schedule}


@app.post("/api/schedules", tags=["Schedules"])
async def create_schedule(schedule: CrawlerScheduleCreate, current_user: dict = Depends(get_current_user)):
    """Create new schedule with validation"""
    try:
        # Validate cron expression first
        if scheduler:
            validation = scheduler.validate_cron_expression(schedule.start_schedule)
            if not validation['valid']:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid cron expression '{schedule.start_schedule}': {validation['error']}"
                )
        
        # Validate template exists
        template = db.get_template_by_id(schedule.template_id)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template with ID {schedule.template_id} not found")
        
        # Create schedule with template_id
        data = {
            'name': schedule.name,
            'start_schedule': schedule.start_schedule,
            'template_id': schedule.template_id,
            'status': schedule.status,
            'created_at': datetime.now().isoformat()
        }
        
        created = ScheduleManager.create(data)
        if not created:
            raise HTTPException(status_code=500, detail="Failed to create schedule")
        
        # CRITICAL: Add new schedule to scheduler service
        if scheduler and created['status'] == 'active':
            try:
                scheduler.add_job(created['id'])
                print(f"✅ Added schedule to scheduler: {created['name']}")
            except Exception as e:
                print(f"⚠️ Failed to add schedule to scheduler: {e}")
                # Don't fail the request, schedule will be loaded on next restart
        
        # Get next run times for confirmation
        next_runs = []
        if scheduler:
            validation = scheduler.validate_cron_expression(schedule.start_schedule)
            if validation.get('valid') and validation.get('next_runs'):
                next_runs = validation['next_runs'][:3]  # Show next 3 runs
        
        return {
            "success": True,
            "message": "Schedule created successfully",
            "schedule_id": created['id'],
            "schedule": created,
            "next_runs": next_runs,
            "timezone": str(scheduler.get_scheduler_timezone()) if scheduler else "Unknown"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/schedules/{schedule_id}", tags=["Schedules"])
async def update_schedule(schedule_id: str, schedule: CrawlerScheduleUpdate, current_user: dict = Depends(get_current_user)):
    """Update existing schedule"""
    try:
        # Check if schedule exists
        if not ScheduleManager.get_by_id(schedule_id):
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        # Build update data
        update_data = schedule.dict(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Validate template if provided
        if 'template_id' in update_data:
            template = db.get_template_by_id(update_data['template_id'])
            if not template:
                raise HTTPException(status_code=404, detail=f"Template with ID {update_data['template_id']} not found")
        
        # Update schedule
        updated = ScheduleManager.update(schedule_id, update_data)
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update schedule")
        
        # CRITICAL: Reschedule job if cron or status changed
        if scheduler:
            try:
                if 'start_schedule' in update_data or 'status' in update_data:
                    scheduler.reschedule_job(schedule_id)
                    print(f"✅ Rescheduled job: {schedule_id}")
            except Exception as e:
                print(f"⚠️ Failed to reschedule job: {e}")
        
        return {
            "success": True,
            "message": "Schedule updated successfully",
            "schedule": updated
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/schedules/{schedule_id}", tags=["Schedules"])
async def delete_schedule(schedule_id: str, current_user: dict = Depends(get_current_user)):
    """Delete schedule"""
    try:
        # Check if schedule exists
        schedule = ScheduleManager.get_by_id(schedule_id)
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        # CRITICAL: Remove from scheduler first
        if scheduler:
            try:
                scheduler.remove_job(schedule_id)
                print(f"✅ Removed job from scheduler: {schedule_id}")
            except Exception as e:
                print(f"⚠️ Failed to remove job from scheduler: {e}")
        
        # Delete schedule
        success = ScheduleManager.delete(schedule_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete schedule - no rows affected")
        
        return {
            "success": True,
            "message": f"Schedule '{schedule['name']}' deleted successfully",
            "schedule_id": schedule_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete schedule: {str(e)}")


@app.patch("/api/schedules/{schedule_id}/toggle", tags=["Schedules"])
async def toggle_schedule(schedule_id: str, current_user: dict = Depends(get_current_user)):
    """Toggle schedule status between 'active' and 'inactive'"""
    try:
        # Get current schedule
        schedule = ScheduleManager.get_by_id(schedule_id)
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        # Toggle status
        current_status = schedule['status']
        new_status = 'inactive' if current_status == 'active' else 'active'
        
        # Update status
        updated = ScheduleManager.update(schedule_id, {'status': new_status})
        
        # CRITICAL: Pause/resume job in scheduler
        if scheduler:
            try:
                if new_status == 'active':
                    # Resume or add job
                    try:
                        scheduler.resume_job(schedule_id)
                        print(f"✅ Resumed job: {schedule_id}")
                    except:
                        # Job doesn't exist, add it
                        scheduler.add_job(schedule_id)
                        print(f"✅ Added job: {schedule_id}")
                else:
                    # Pause job
                    scheduler.pause_job(schedule_id)
                    print(f"✅ Paused job: {schedule_id}")
            except Exception as e:
                print(f"⚠️ Failed to toggle job in scheduler: {e}")
        
        return {
            "success": True,
            "message": f"Schedule status changed to '{new_status}'",
            "schedule_id": schedule_id,
            "old_status": current_status,
            "new_status": new_status,
            "schedule": updated
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# QUEUE AND EXECUTION ENDPOINTS
# ============================================================================

@app.get("/api/schedules/queue/status", tags=["Schedules"])
@handle_api_errors
async def get_queue_status(current_user: dict = Depends(get_current_user)):
    """Get RabbitMQ queue status"""
    try:
        from helper.rabbitmq_helper import queue_publisher
        queue_info = queue_publisher.get_queue_info()
        return queue_info or {"queue": "linkedin_profiles", "messages": 0, "consumers": 0}
    except Exception as e:
        logger.error(f"Error getting queue status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/schedules/{schedule_id}/execute", tags=["Schedules"])
@handle_api_errors
async def execute_schedule_manually(schedule_id: str, current_user: dict = Depends(get_current_user)):
    """Execute schedule manually"""
    global current_crawl_session
    
    try:
        print(f"🚀 Execute request for schedule_id: '{schedule_id}'")
        
        # Validate schedule_id first
        if not schedule_id or schedule_id in ["undefined", "null", None]:
            print(f"❌ Invalid schedule_id received: '{schedule_id}'")
            return {
                "success": False,
                "message": f"Invalid schedule_id: '{schedule_id}'. Please select a valid schedule.",
                "schedule_id": schedule_id,
                "leads_queued": 0
            }
        
        # Get schedule details
        schedule = db.get_schedule(schedule_id)
        
        if not schedule:
            print(f"❌ Schedule not found: {schedule_id}")
            raise HTTPException(status_code=404, detail="Schedule not found")
        template_id = schedule.get("template_id")
        
        print(f"📋 Manual execution for schedule: {schedule.get('name')}")
        print(f"📋 Template ID: {template_id}")
        
        # Validate template_id before any database operations
        if not template_id or template_id in ["undefined", "null", None]:
            print(f"❌ Invalid template_id: '{template_id}'")
            return {
                "success": False,
                "message": f"Schedule has invalid template_id: '{template_id}'. Please check schedule configuration.",
                "schedule_id": schedule_id,
                "template_id": template_id,
                "leads_queued": 0
            }
        
        print(f"📋 Manual execution for schedule: {schedule.get('name')}")
        print(f"📋 Template ID: {template_id}")
        
        # Get leads for this template
        try:
            leads = db.get_leads_by_template_id(template_id)
            print(f"📊 Found {len(leads) if leads else 0} leads for template")
        except Exception as e:
            print(f"❌ Error getting leads: {e}")
            return {
                "success": False,
                "message": f"Error getting leads: {str(e)}",
                "schedule_id": schedule_id,
                "template_id": template_id,
                "leads_queued": 0
            }
        
        if not leads:
            print(f"⚠️ No leads found for template {template_id}")
            
            # Auto-deactivate schedule if no leads exist
            try:
                from helper.postgres_helper import ScheduleManager
                schedule_manager = ScheduleManager()
                schedule_manager.update_schedule_status(schedule_id, False)
                print(f"✅ Auto-deactivated schedule '{schedule['name']}' - no leads found")
            except Exception as e:
                print(f"⚠️ Failed to auto-deactivate schedule: {e}")
            
            return {
                "success": True,
                "message": f"No leads found for schedule '{schedule['name']}'. Schedule auto-deactivated.",
                "schedule_id": schedule_id,
                "template_id": template_id,
                "leads_queued": 0,
                "schedule_deactivated": True
            }
        
        # Filter leads that need processing
        needs_processing = [lead for lead in leads if lead.get('needs_processing', False)]
        
        print(f"📊 Leads analysis:")
        print(f"   - Total leads: {len(leads)}")
        print(f"   - Need processing: {len(needs_processing)}")
        print(f"   - Already complete: {len(leads) - len(needs_processing)}")
        
        if not needs_processing:
            # Auto-deactivate schedule if no leads need processing
            try:
                from helper.postgres_helper import ScheduleManager
                schedule_manager = ScheduleManager()
                schedule_manager.update_schedule_status(schedule_id, False)
                print(f"✅ Auto-deactivated schedule '{schedule['name']}' - all leads complete")
            except Exception as e:
                print(f"⚠️ Failed to auto-deactivate schedule: {e}")
            
            return {
                "success": True,
                "message": f"All {len(leads)} leads already complete for schedule '{schedule['name']}'. Schedule auto-deactivated.",
                "schedule_id": schedule_id,
                "template_id": template_id,
                "leads_queued": 0,
                "schedule_deactivated": True
            }
        
        # Use same method as scheduler for consistency
        from helper.rabbitmq_helper import queue_publisher
        
        queued_count = 0
        failed_count = 0
        
        print(f"📤 Manual execution: Queueing {len(needs_processing)} leads...")
        
        for lead in needs_processing:
            success = queue_publisher.publish_crawler_job(
                profile_url=lead['profile_url'],
                template_id=template_id
            )
            if success:
                queued_count += 1
            else:
                failed_count += 1
        
        if queued_count > 0:
            # Update session to mark as manual execution
            current_crawl_session.update({
                'is_active': True,
                'source': 'manual',
                'schedule_id': schedule_id,
                'schedule_name': schedule['name'],
                'template_id': template_id,
                'template_name': schedule.get('name', 'Unknown Template'),
                'started_at': datetime.now().isoformat(),
                'leads_queued': queued_count
            })
            print(f"✅ Updated session for manual execution: {schedule['name']} (ID: {schedule_id})")
        
        return {
            "success": True,
            "message": f"Schedule '{schedule['name']}' executed manually - {queued_count} leads queued",
            "schedule_id": schedule_id,
            "template_id": template_id,
            "leads_queued": queued_count,
            "failed_count": failed_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error executing schedule manually {schedule_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SCRAPING ENDPOINTS
# ============================================================================

@app.post("/api/scraping/start", tags=["Scraping"])
@handle_api_errors
async def start_scraping(request: ScrapingRequest, current_user: dict = Depends(get_current_user)):
    """Start scraping process"""
    global current_crawl_session
    
    try:
        from helper.rabbitmq_helper import queue_publisher
        # Remove Supabase import - using PostgreSQL Database class now
        
        # Get template details first
        template = db.get_template_by_id(request.template_id)
        
        if not template:
            return ScrapingResponse(
                success=False,
                message="Template not found",
                leads_queued=0,
                batch_id=f"manual_{request.template_id}_{int(time.time())}"
            )
        
        template_name = template.get('name', 'Unknown Template')
        
        # Get leads that need processing
        leads = db.get_leads_by_template_id(request.template_id)
        
        if not leads:
            return ScrapingResponse(
                success=False,
                message=f"No leads found for template '{template_name}'",
                leads_queued=0,
                batch_id=f"manual_{request.template_id}_{int(time.time())}"
            )
        
        needs_processing = [lead for lead in leads if lead.get('needs_processing', False)]
        
        if not needs_processing:
            return ScrapingResponse(
                success=True,
                message=f"All {len(leads)} leads already complete for template '{template_name}'",
                leads_queued=0,
                batch_id=f"manual_{request.template_id}_{int(time.time())}"
            )
        
        # Queue individual leads
        queued_count = 0
        for lead in needs_processing:
            success = queue_publisher.publish_crawler_job(
                profile_url=lead['profile_url'],
                template_id=request.template_id
            )
            if success:
                queued_count += 1
        
        # Update session like execute_schedule_manually does
        current_crawl_session.update({
            'is_active': True,
            'source': 'manual',
            'template_id': request.template_id,
            'template_name': template_name,
            'started_at': datetime.now().isoformat(),
            'leads_queued': queued_count
        })
        
        return ScrapingResponse(
            success=True,
            message=f"Scraping started successfully for template '{template_name}'",
            leads_queued=queued_count,  # Real count
            batch_id=f"manual_{request.template_id}_{int(time.time())}"
        )
        
    except Exception as e:
        logger.error(f"Error starting scraping: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scraping/analyze/{template_id}", tags=["Scraping"])
@handle_api_errors
async def analyze_lead(template_id: str, current_user: dict = Depends(get_current_user)):
    """Analyze lead completion for template"""
    try:
        # Use Database to get leads with proper validation logic
        leads = db.get_leads_by_template_id(template_id)
        
        if not leads:
            return {
                "total": 0,
                "complete": 0,
                "needProcessing": 0,
                "completionRate": 0
            }
        
        total = len(leads)
        need_processing = len([lead for lead in leads if lead.get('needs_processing', False)])
        complete = total - need_processing
        completion_rate = (complete / total * 100) if total > 0 else 0
        
        return {
            "total": total,
            "complete": complete,
            "needProcessing": need_processing,
            "completionRate": completion_rate
        }
        
    except Exception as e:
        logger.error(f"Error analyzing lead {template_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scraping/status", tags=["Scraping"])
@handle_api_errors
async def get_crawler_status(current_user: dict = Depends(get_current_user)):
    """Get current crawler status"""
    try:
        from helper.rabbitmq_helper import queue_publisher
        queue_info = queue_publisher.get_queue_info()
        
        return CrawlerStatusResponse(
            is_running=(queue_info.get("messages", 0) if queue_info else 0) > 0,
            queue_size=queue_info.get("messages", 0) if queue_info else 0,
            processed_count=0  # This would need to be tracked separately
        )
        
    except Exception as e:
        logger.error(f"Error getting crawler status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scraping/session", tags=["Scraping"])
@handle_api_errors
async def get_crawl_session(current_user: dict = Depends(get_current_user)):
    """Get detailed crawl session information"""
    global current_crawl_session
    
    try:
        # Auto-complete session if needed
        await check_and_complete_session()
        
        # Get current queue size
        queue_size = 0
        try:
            queue_info = queue_publisher.get_queue_info()
            queue_size = queue_info.get('messages', 0) if queue_info else 0
        except Exception as e:
            print(f"Error getting queue info: {e}")
        
        return {
            **current_crawl_session,
            'current_queue_size': queue_size
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# OUTREACH ENDPOINTS
# ============================================================================

# ============================================================================
# REQUIREMENTS ENDPOINTS
# ============================================================================

@app.get("/api/requirements/templates", tags=["Requirements"])
async def get_templates(current_user: dict = Depends(get_current_user)):
    """Get all requirements templates - OPTIMIZED"""
    try:
        print("📥 Fetching templates...")
        
        # Use PostgreSQL Database class instead of Supabase
        templates = db.get_all_templates()
        
        # Format templates for compatibility
        formatted_templates = []
        for template in templates:
            formatted_templates.append({
                'id': template['id'],
                'name': template['name'],
                'created_at': template['created_at']
            })
        
        print(f"✅ Templates fetched: {len(formatted_templates)}")
        
        return {
            "success": True,
            "templates": formatted_templates
        }
    except Exception as e:
        print(f"❌ Error fetching templates: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "templates": [],
            "error": str(e)
        }
@app.get("/api/templates/{template_id}/requirements")
async def get_template_requirements(
    template_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get requirements for a specific template"""
    try:
        requirements = db.get_template_requirements(template_id)
        return {
            "success": True,
            "requirements": requirements
        }
    except Exception as e:
        print(f"❌ Template requirements error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get template requirements: {str(e)}")


@app.post("/api/requirements/generate", tags=["Requirements"])
async def generate_requirements(request: RequirementsGenerateRequest, current_user: dict = Depends(get_current_user)):
    """Generate requirements from job description text - Uses requirements_generator.py"""
    try:
        # Import from same directory (API folder)
        from requirements_generator import generate_requirements_from_text
        
        print(f"📝 Processing job description for position: {request.position}")
        print(f"📄 Text length: {len(request.job_description)} characters")
        
        # Use the existing requirements generator function
        requirements_result = generate_requirements_from_text(
            job_description=request.job_description,
            position_title=request.position
        )
        
        print(f"✅ Generated {len(requirements_result['requirements'])} requirements for {request.position}")
        
        # Return with proper structure: {"position": "", "requirements": []}
        return {
            'success': True,
            'position': requirements_result.get('position', request.position),
            'requirements': requirements_result.get('requirements', []),
            'total_requirements': len(requirements_result.get('requirements', [])),
            'source': 'requirements_generator.py'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error generating requirements: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
async def generate_and_save_requirements(request: RequirementsGenerateRequest):
    """Generate requirements from job description and auto-save to file - Uses requirements_generator.py"""
    try:
        # Import from same directory (API folder)
        from requirements_generator import generate_requirements_from_text

        print(f"🤖 AUTO-GENERATING AND SAVING requirements for: {request.position}")
        print(f"📄 Text length: {len(request.job_description)} characters")

        # Use the existing requirements generator function
        requirements_result = generate_requirements_from_text(
            job_description=request.job_description,
            position_title=request.position
        )

        requirements_array = requirements_result['requirements']
        print(f"✅ Generated {len(requirements_array)} requirements using requirements_generator")

        # Build requirements structure with metadata
        requirements = {
            'position': request.position,
            'requirements': requirements_array,
            'metadata': {
                'total_requirements': len(requirements_array),
                'generated_from': 'job_description_manual',
                'created_at': datetime.utcnow().isoformat(),
                'auto_generated': True,
                'generator_version': 'requirements_generator.py'
            }
        }

        # Save to database instead of file
        try:
            # For manual generation, we need template_id from request
            # Since we don't have template_id in current request model, 
            # we'll create a new template or update existing one by name
            
            # Generate template name from position
            template_name = f"{request.position} - Auto Generated"
            
            # Check if template already exists
            existing_template = db.get_template_by_name(template_name)
            
            if existing_template:
                # Update existing template
                template_id = existing_template['id']
                db.update_template(template_id, {
                    "requirements": requirements_array
                })
                
                print(f"✅ Updated existing template: {template_name}")
                print(f"💾 Template ID: {template_id}")
                
                return {
                    'success': True,
                    'requirements': requirements,
                    'total_requirements': len(requirements_array),
                    'source': 'requirements_generator.py',
                    'template_id': template_id,
                    'template_name': template_name,
                    'action': 'updated',
                        'message': f'Requirements updated in template: {template_name}'
                    }
            else:
                # Create new template
                template_data = {
                    "name": template_name,
                    "job_title": request.position,
                    "job_description": request.job_description,
                    "requirements": requirements_array,
                    "created_at": datetime.utcnow().isoformat()
                }
                
                template_id = db.create_template(template_data)
                
                print(f"✅ Created new template: {template_name}")
                print(f"💾 Template ID: {template_id}")
                
                return {
                    'success': True,
                    'requirements': requirements,
                    'total_requirements': len(requirements_array),
                    'source': 'requirements_generator.py',
                    'template_id': template_id,
                    'template_name': template_name,
                    'action': 'created',
                    'message': f'Requirements saved in new template: {template_name}'
                }
            
            raise Exception("Failed to save to database")
                
        except Exception as db_error:
            print(f"❌ Database save failed: {db_error}")
            # Return success anyway since generation worked
            return {
                'success': True,
                'requirements': requirements,
                'total_requirements': len(requirements_array),
                'source': 'requirements_generator.py',
                'template_id': None,
                'template_name': None,
                'action': 'failed',
                'message': f'Requirements generated but failed to save to database: {str(db_error)}'
            }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error generating and saving requirements: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
def generate_requirements_simple(job_description, position_title):
    """Simple requirements generation fallback - same logic as requirements_generator.py"""

    def extract_bullet_points(text):
        """Extract bullet points from text"""
        if not text:
            return []

        bullets = []
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        # Remove heading line if present
        if lines and any(keyword in lines[0].lower() for keyword in ['kualifikasi', 'persyaratan', 'requirements', 'syarat']):
            lines = lines[1:]

        for line in lines:
            # Skip if too short
            if len(line) < 5:
                continue

            # Clean bullet markers
            line_clean = re.sub(r'^[•\-\*○\d+\.\)]\s*', '', line).strip()

            if line_clean and len(line_clean) >= 5:
                bullets.append(line_clean)

        return bullets

    def classify_requirement(text, req_id):
        """Classify a single requirement and extract structured value"""
        text_lower = text.lower()

        # Priority 1: Gender
        if any(word in text_lower for word in ['pria', 'wanita', 'laki-laki', 'perempuan', 'male', 'female']):
            # Determine gender value
            if 'pria / wanita' in text_lower or 'pria/wanita' in text_lower or ('pria' in text_lower and 'wanita' in text_lower):
                gender_value = 'any'
            elif any(word in text_lower for word in ['wanita', 'perempuan', 'female']):
                gender_value = 'female'
            elif any(word in text_lower for word in ['pria', 'laki-laki', 'male']):
                gender_value = 'male'
            else:
                gender_value = 'any'

            return {
                'id': f'req_{req_id}',
                'label': text,
                'type': 'gender',
                'value': gender_value
            }

        # Priority 2: Age
        if any(word in text_lower for word in ['usia', 'umur', 'age']):
            # Extract age range
            age_patterns = [
                r'(\d+)\s*-\s*(\d+)\s*tahun',
                r'(\d+)\s*sampai\s*(\d+)\s*tahun',
                r'maksimal\s*(\d+)\s*tahun',
                r'max\s*(\d+)\s*tahun'
            ]

            age_value = {'min': 18, 'max': 35}  # default

            for pattern in age_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    if match.lastindex >= 2:
                        age_value = {
                            'min': int(match.group(1)),
                            'max': int(match.group(2))
                        }
                    else:
                        age_value = {
                            'min': 18,
                            'max': int(match.group(1))
                        }
                    break

            return {
                'id': f'req_{req_id}',
                'label': text,
                'type': 'age',
                'value': age_value
            }

        # Priority 3: Education
        if any(word in text_lower for word in ['pendidikan', 'education', 'lulusan', 'ijazah', 'sma', 'smk', 'diploma', 's1', 'sarjana']):
            # Determine education level
            if any(word in text_lower for word in ['sarjana', 's1', 's-1', 'bachelor']):
                edu_value = 'bachelor'
            elif any(word in text_lower for word in ['diploma', 'd3', 'd-3']):
                edu_value = 'diploma'
            elif any(word in text_lower for word in ['sma', 'smk', 'high school', 'slta']):
                edu_value = 'high school'
            else:
                edu_value = 'high school'  # default

            return {
                'id': f'req_{req_id}',
                'label': text,
                'type': 'education',
                'value': edu_value
            }

        # Priority 4: Location
        if any(word in text_lower for word in ['penempatan', 'lokasi', 'domisili', 'location', 'ditempatkan']):
            # Extract location name
            location_match = re.search(r'(?:penempatan|lokasi|domisili|location|ditempatkan)\s*:?\s*([A-Za-z\s]+)', text, re.IGNORECASE)
            if location_match:
                location_value = location_match.group(1).strip()
                # Remove trailing words like "atau", "dan"
                location_value = re.sub(r'\s+(atau|or|dan|and)\s+.*', '', location_value, flags=re.IGNORECASE).strip()
            else:
                location_value = 'any'

            return {
                'id': f'req_{req_id}',
                'label': text,
                'type': 'location',
                'value': location_value.lower()
            }

        # Priority 5: Experience (with years)
        if any(word in text_lower for word in ['pengalaman', 'experience', 'berpengalaman']):
            # Extract years
            exp_patterns = [
                r'(?:minimal|minimum|min\.?)\s*(\d+)\s*(?:tahun|years?)',
                r'(\d+)\s*(?:tahun|years?)\s*(?:pengalaman|experience)',
                r'(\d+)\+?\s*(?:tahun|years?)'
            ]

            exp_value = 1  # default

            for pattern in exp_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    exp_value = int(match.group(1))
                    break

            return {
                'id': f'req_{req_id}',
                'label': text,
                'type': 'experience',
                'value': exp_value
            }

        # Default: Skill
        return {
            'id': f'req_{req_id}',
            'label': text,
            'type': 'skill',
            'value': text.lower()
        }

    # Extract bullet points from job description
    bullets = extract_bullet_points(job_description)

    # Classify each bullet point
    requirements_array = []
    for i, bullet in enumerate(bullets):
        req = classify_requirement(bullet, i + 1)
        requirements_array.append(req)

    # Add default requirements if none found
    if len(requirements_array) == 0:
        requirements_array = [
            {
                'id': 'req_1',
                'label': 'Minimum 1 year experience',
                'type': 'experience',
                'value': 1
            },
            {
                'id': 'req_2',
                'label': 'Education: High School',
                'type': 'education',
                'value': 'high school'
            }
        ]

    # Build final output - same format as requirements_generator.py
    return {
        'position': position_title,
        'requirements': requirements_array
    }






@app.post("/api/requirements/save", tags=["Requirements"])
async def save_requirements(request: RequirementsSaveRequest, current_user: dict = Depends(get_current_user)):
    """Save requirements to JSON file"""
    try:
        # Ensure requirements directory exists
        requirements_dir = Path(__file__).parent.parent / "scoring" / "requirements"
        requirements_dir.mkdir(parents=True, exist_ok=True)
        
        # Clean filename
        filename = request.filename
        if not filename.endswith('.json'):
            filename += '.json'
        
        # Save to file
        filepath = requirements_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(request.requirements, f, indent=2, ensure_ascii=False)
        
        return {
            'success': True,
            'message': 'Requirements saved successfully',
            'filepath': str(filepath)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EXTERNAL INTEGRATION ENDPOINTS
# ============================================================================

@app.post("/api/external/schedule-scraping", tags=["External Integration"])
async def create_external_schedule(request: ExternalScheduleRequest, current_user: dict = Depends(get_current_user)):
    """Create comprehensive schedule for external platform integration - distributes data to multiple services"""
    try:
        # Generate unique job ID for Nara
        job_id = f"nara_{uuid.uuid4().hex[:8]}"
        
        print(f"\n🌐 EXTERNAL SCHEDULE REQUEST from {request.external_source}")
        print(f"   Job: {request.job_title}")
        print(f"   Generated Job ID: {job_id}")
        print(f"   Schedule: {request.schedule_date} {request.schedule_time}")
        print(f"   Job Description Preview: {request.job_description[:100]}...")
        print(f"   Note: Candidates will be taken from existing leads list")
        
        # ============================================================================
        # STEP 1: USE EXISTING NARA COMPANY ID
        # ============================================================================
        # Hardcode company_id Nara yang sudah ada
        company_id = "3bb96963-2c83-4ce4-b7a7-237adfc7c962"
        print(f"✅ Using existing Nara company: {company_id}")
        
        # ============================================================================
        # STEP 2: CREATE SEARCH TEMPLATE
        # ============================================================================
        template_id = str(uuid.uuid4())
        template_name = f"{request.job_title} - Nara"
        
        # Create search template entry
        template_created = False
        try:
            template_data = {
                "id": template_id,
                "name": template_name,
                "job_title": request.job_title,
                "job_description": request.job_description,
                "company_id": company_id,
                "external_source": request.external_source,
                "created_at": datetime.utcnow().isoformat()
            }
            
            print(f"🔄 Attempting to create template: {template_name}")
            print(f"📊 Template data: {template_data}")
            
            # Insert to search_templates table
            template_id = db.create_template(template_data)
            
            print(f"📊 Created template with ID: {template_id}")
            
            template_created = True
            print(f"✅ Created search template successfully!")
            print(f"   ID: {template_id}")
            print(f"   Name: {template_data.get('name')}")
            
            # Verify template was actually saved
            verify_result = db.get_template_by_id(template_id)
            print(f"🔍 Verification result: {verify_result}")
            
        except Exception as e:
            print(f"❌ Template creation failed with exception: {e}")
            print(f"📊 Template data attempted: {template_data}")
            import traceback
            traceback.print_exc()
            # Continue without template if creation fails
        
        # ============================================================================
        # STEP 2: AUTO-GENERATE REQUIREMENTS (INTEGRATED)
        # ============================================================================
        requirements_data = None
        requirements_generated = False
        
        print(f"🤖 AUTO-GENERATING REQUIREMENTS (integrated approach)...")
        print(f"📝 Job description length: {len(request.job_description)} characters")
        
        try:
            # Method 1: Try to use requirements_generator.py
            requirements_result = None
            method_used = "unknown"
            
            try:
                import sys
                from pathlib import Path
                
                # Try to import from shared module first
                shared_path = Path(__file__).parent.parent / "shared"
                shared_path_str = str(shared_path.absolute())
                
                if shared_path_str not in sys.path:
                    sys.path.insert(0, shared_path_str)
                
                from requirements_utils import generate_requirements_from_text
                
                print(f"✅ Using shared requirements_utils module")
                
                requirements_result = generate_requirements_from_text(
                    job_description=request.job_description,
                    position_title=request.job_title
                )
                
                method_used = "shared_requirements_utils"
                print(f"✅ Used shared requirements_utils successfully")
                
            except Exception as import_error:
                print(f"⚠️ Shared module failed: {import_error}")
                
                # Fallback: Try original requirements_generator.py
                try:
                    scoring_path = Path(__file__).parent.parent / "scoring"
                    scoring_path_str = str(scoring_path.absolute())
                    
                    if scoring_path_str not in sys.path:
                        sys.path.insert(0, scoring_path_str)
                    
                    from requirements_generator import generate_requirements_from_text
                    
                    requirements_result = generate_requirements_from_text(
                        job_description=request.job_description,
                        position_title=request.job_title
                    )
                    
                    method_used = "requirements_generator.py"
                    print(f"✅ Used requirements_generator.py fallback")
                    
                except Exception as fallback_error:
                    print(f"⚠️ All imports failed, using inline logic")
                    
                    # Final fallback: inline logic
                    bullets = []
                    lines = [line.strip() for line in request.job_description.split('\n') if line.strip()]
                    
                    if lines and any(keyword in lines[0].lower() for keyword in ['kualifikasi', 'persyaratan', 'requirements', 'syarat']):
                        lines = lines[1:]
                    
                    for line in lines:
                        if len(line) >= 5:
                            line_clean = re.sub(r'^[•\-\*○\d+\.\)]\s*', '', line).strip()
                            if line_clean and len(line_clean) >= 5:
                                bullets.append(line_clean)
                    
                    requirements_array = []
                    for i, bullet in enumerate(bullets):
                        text_lower = bullet.lower()
                        req_id = i + 1
                        
                        if any(word in text_lower for word in ['pengalaman', 'experience']):
                            exp_patterns = [r'(\d+)\s*(?:tahun|years?)']
                            exp_value = 1
                            for pattern in exp_patterns:
                                match = re.search(pattern, text_lower)
                                if match:
                                    exp_value = int(match.group(1))
                                    break
                            req = {'id': f'req_{req_id}', 'label': bullet, 'type': 'experience', 'value': exp_value}
                        elif any(word in text_lower for word in ['pendidikan', 'education', 's1', 'sarjana', 'diploma']):
                            edu_value = 'bachelor' if any(word in text_lower for word in ['s1', 'sarjana']) else 'high school'
                            req = {'id': f'req_{req_id}', 'label': bullet, 'type': 'education', 'value': edu_value}
                        else:
                            req = {'id': f'req_{req_id}', 'label': bullet, 'type': 'skill', 'value': bullet.lower()}
                        
                        requirements_array.append(req)
                    
                    if len(requirements_array) == 0:
                        requirements_array = [
                            {'id': 'req_1', 'label': f'Experience in {request.job_title}', 'type': 'experience', 'value': 1},
                            {'id': 'req_2', 'label': 'Good communication skills', 'type': 'skill', 'value': 'communication'}
                        ]
                    
                    requirements_result = {
                        'position': request.job_title,
                        'requirements': requirements_array
                    }
                    
                    method_used = "inline_final_fallback"
                    print(f"✅ Used inline final fallback - generated {len(requirements_array)} requirements")
            
            if requirements_result and 'requirements' in requirements_result:
                requirements_array = requirements_result['requirements']
                
                # Create requirements data structure
                requirements_data = {
                    'position': request.job_title,
                    'company': 'Nara',
                    'job_id': job_id,
                    'requirements': requirements_array,
                    'metadata': {
                        'total_requirements': len(requirements_array),
                        'generated_from': 'integrated_nara',
                        'external_source': request.external_source,
                        'created_at': datetime.utcnow().isoformat(),
                        'auto_generated': True,
                        'method_used': method_used
                    }
                }
                
                # Save requirements to template instead of separate storage
                try:
                    # Save complete requirements structure with position
                    requirements_to_save = {
                        'position': request.job_title,
                        'requirements': requirements_array
                    }
                    
                    # Update the template that was created earlier with requirements
                    db.update_template(template_id, {
                        "requirements": requirements_to_save
                    })
                    
                    requirements_generated = True
                    print(f"✅ Generated {len(requirements_array)} requirements")
                    print(f"✅ Updated template {template_id} with requirements")
                    print(f"📊 Method used: {method_used}")
                    
                    # Update requirements_data with template info
                    requirements_data['template_id'] = template_id
                    requirements_data['template_name'] = template_name
                        
                except Exception as db_error:
                    print(f"❌ Template update failed: {db_error}")
                    requirements_generated = False
                
                # Log requirements breakdown
                type_counts = {}
                for req in requirements_array:
                    req_type = req.get('type', 'unknown')
                    type_counts[req_type] = type_counts.get(req_type, 0) + 1
                
                print(f"📊 Requirements breakdown:")
                for req_type, count in type_counts.items():
                    print(f"   - {req_type}: {count} items")
            
            else:
                print("❌ No requirements generated from either method")
                requirements_generated = False
        
        except Exception as e:
            print(f"❌ Requirements generation failed: {e}")
            import traceback
            traceback.print_exc()
            requirements_generated = False
        
        # Fallback: Add default requirements if all methods failed
        if not requirements_generated:
            print("🔄 Adding default requirements as final fallback...")
            try:
                default_requirements = [
                    {
                        'id': 'req_1',
                        'label': f'Experience in {request.job_title}',
                        'type': 'experience',
                        'value': 1
                    },
                    {
                        'id': 'req_2',
                        'label': 'Good communication skills',
                        'type': 'skill',
                        'value': 'communication'
                    },
                    {
                        'id': 'req_3',
                        'label': 'Education: High School or equivalent',
                        'type': 'education',
                        'value': 'high school'
                    }
                ]
                
                requirements_data = {
                    'position': request.job_title,
                    'company': 'Nara',
                    'job_id': job_id,
                    'requirements': default_requirements,
                    'metadata': {
                        'total_requirements': len(default_requirements),
                        'generated_from': 'default_fallback',
                        'external_source': request.external_source,
                        'created_at': datetime.utcnow().isoformat(),
                        'auto_generated': True,
                        'method_used': 'default_fallback'
                    }
                }
                
                # Save default requirements to template with position wrapper
                try:
                    default_requirements_to_save = {
                        'position': request.job_title,
                        'requirements': default_requirements
                    }
                    
                    db.update_template(template_id, {
                        "requirements": default_requirements_to_save
                    })
                    
                    requirements_generated = True
                    print(f"✅ Default requirements saved to template {template_id}")
                    
                    # Update requirements_data with template info
                    requirements_data['template_id'] = template_id
                    requirements_data['template_name'] = template_name
                        
                except Exception as db_error:
                    print(f"❌ Template update failed for default requirements: {db_error}")
                    requirements_generated = False
                
            except Exception as fallback_error:
                print(f"❌ Even default requirements failed: {fallback_error}")
                requirements_generated = False
        
        # ============================================================================
        # STEP 3: CREATE SCHEDULE
        # ============================================================================
        
        # Parse schedule datetime
        try:
            schedule_datetime_str = f"{request.schedule_date} {request.schedule_time}"
            schedule_dt = datetime.strptime(schedule_datetime_str, "%Y-%m-%d %H:%M")
            
            # Convert to one-time cron expression (specific date and time)
            # Format: minute hour day month * (for specific date execution)
            cron_expression = f"{schedule_dt.minute} {schedule_dt.hour} {schedule_dt.day} {schedule_dt.month} *"
            
            print(f"✅ Generated one-time cron: {cron_expression} for {schedule_datetime_str}")
            
        except Exception as e:
            print(f"⚠️ Schedule parsing failed: {e}")
            # Default to today at 9 AM if parsing fails
            today = datetime.now()
            cron_expression = f"0 9 {today.day} {today.month} *"
            print(f"✅ Using fallback cron: {cron_expression}")
        
        # Create external metadata
        external_metadata = {
            "job_id": job_id,
            "company": "Nara",
            "company_id": company_id,
            "job_title": request.job_title,
            "job_description": request.job_description,
            "schedule_datetime": f"{request.schedule_date} {request.schedule_time}",
            "timezone": request.timezone,
            "template_id": template_id,
            "template_name": template_name,
            "requirements_file": requirements_data.get('template_name') if requirements_generated else None,
            "requirements_generated": requirements_generated,
            "note": "Candidates will be taken from existing leads list"
        }
        
        # Create schedule
        schedule_data = {
            "name": f"[NARA] {request.job_title}",
            "start_schedule": cron_expression,  # PENTING: Simpan cron expression
            "template_id": template_id,
            "status": "active",
            "external_source": request.external_source,
            "external_metadata": external_metadata,
            "webhook_url": request.webhook_url,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Insert schedule to database
        schedule_id = db.create_schedule(
            name=schedule_data['name'],
            start_schedule=schedule_data['start_schedule'],
            template_id=schedule_data['template_id'],
            external_source=schedule_data['external_source'],
            webhook_url=schedule_data.get('webhook_url')
        )
        
        print(f"✅ Created schedule: {schedule_id}")
        
        # ============================================================================
        # STEP 4: ADD TO SCHEDULER SERVICE (CRITICAL FOR EXECUTE & AUTO-TRIGGER)
        # ============================================================================
        
        scheduler_added = False
        print(f"🔍 Checking scheduler service availability...")
        print(f"   Scheduler object: {scheduler}")
        print(f"   Scheduler type: {type(scheduler)}")
        
        try:
            if scheduler:
                print(f"✅ Scheduler service available, adding job...")
                result = scheduler.add_job(schedule_id)
                print(f"📊 Add job result: {result}")
                scheduler_added = True
                print(f"✅ Added external schedule to scheduler service - can execute & auto-trigger")
            else:
                print(f"❌ Scheduler service not available - schedule created but won't auto-trigger")
        except Exception as e:
            print(f"❌ Failed to add to scheduler service: {e}")
            print(f"   Schedule created but manual execute may not work")
            import traceback
            traceback.print_exc()
        
        # ============================================================================
        # RESPONSE
        # ============================================================================
        
        return {
            "success": True,
            "message": "Nara schedule created successfully with distributed data",
            "data": {
                "schedule_id": schedule_id,
                "template_id": template_id,
                "job_id": job_id,
                "company": "Nara",
                "external_source": request.external_source,
                "job_title": request.job_title,
                "status": "active",
                "schedule_status": "active",
                "cron_expression": cron_expression,
                "webhook_url": request.webhook_url,
                "created_at": schedule.get("created_at"),
                "note": "Candidates will be taken from existing leads list",
                "requirements": {
                    "position": request.job_title,
                    "requirements": requirements_data.get('requirements', []) if requirements_data else []
                },
                "services_updated": {
                    "search_template": template_id,
                    "company_linked": True,
                    "requirements_generated": requirements_generated,
                    "requirements_template_id": template_id,
                    "requirements_template_name": template_name,
                    "requirements_count": len(requirements_data.get('requirements', [])) if requirements_data else 0,
                    "schedule_created": schedule_id,
                    "scheduler_service_added": scheduler_added,
                    "can_execute": scheduler_added,
                    "can_auto_trigger": scheduler_added
                },
                "debug_info": {
                    "job_description_length": len(request.job_description),
                    "requirements_generation_attempted": True,
                    "requirements_generation_success": requirements_generated,
                    "requirements_data_exists": requirements_data is not None,
                    "requirements_array_length": len(requirements_data.get('requirements', [])) if requirements_data else 0
                }
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ External schedule creation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create external schedule: {str(e)}")


# Duplicate endpoints removed - using the tagged versions above


async def check_and_complete_session():
    """Check if crawl session should be automatically completed"""
    global current_crawl_session
    
    # Only check if session is currently active
    if not current_crawl_session.get('is_active', False):
        return
    
    try:
        # Get current queue size
        queue_info = queue_publisher.get_queue_info()
        queue_size = queue_info.get('messages', 0) if queue_info else 0
        
        # If queue is empty, session should be completed
        if queue_size == 0:
            print("🏁 Queue is empty - completing crawl session")
            
            # Check if this was triggered by a schedule
            schedule_id = current_crawl_session.get('schedule_id')
            schedule_name = current_crawl_session.get('schedule_name')
            was_scheduled = current_crawl_session.get('source') == 'scheduled' and schedule_id
            
            # If triggered by scheduler (automatic), deactivate the schedule
            if was_scheduled:
                try:
                    schedule_manager = ScheduleManager()
                    schedule_manager.update_schedule_status(schedule_id, False)
                    print(f"✅ Auto-deactivated schedule: {schedule_name} (ID: {schedule_id}) - crawling completed")
                except Exception as e:
                    print(f"⚠️ Failed to auto-deactivate schedule {schedule_id}: {e}")
            
            # Clear the crawl session
            current_crawl_session = {
                'is_active': False,
                'source': None,
                'schedule_id': None,
                'schedule_name': None,
                'template_id': None,
                'template_name': None,
                'started_at': None,
                'leads_queued': 0
            }
            
            print(f"✅ Crawl session auto-completed - status now idle")
            
    except Exception as e:
        print(f"❌ Error checking session completion: {e}")


@app.post("/api/scraping/stop", tags=["Scraping"])
@handle_api_errors
async def stop_scraping(current_user: dict = Depends(get_current_user)):
    """Stop scraping by purging the RabbitMQ queue"""
    global current_crawl_session
    
    try:
        print("🛑 Stop scraping requested - purging queue")
        
        # Get current queue size before purging
        queue_info = queue_publisher.get_queue_info()
        queue_size = queue_info.get('messages', 0) if queue_info else 0
        
        # Check if this was triggered by a schedule
        schedule_id = current_crawl_session.get('schedule_id')
        schedule_name = current_crawl_session.get('schedule_name')
        
        # Purge the queue (use default queue name)
        queue_purged = queue_publisher.purge_queue()
        
        if queue_purged:
            # Always deactivate schedule if it was running (both manual and automatic)
            if schedule_id:
                try:
                    from helper.postgres_helper import ScheduleManager
                    schedule_manager = ScheduleManager()
                    schedule_manager.update_schedule_status(schedule_id, False)
                    print(f"✅ Deactivated schedule: {schedule_name} (ID: {schedule_id})")
                except Exception as e:
                    print(f"⚠️ Failed to deactivate schedule {schedule_id}: {e}")
            
            # Clear the crawl session to set is_active = False
            current_crawl_session = {
                'is_active': False,
                'source': None,
                'schedule_id': None,
                'schedule_name': None,
                'template_id': None,
                'template_name': None,
                'started_at': None,
                'leads_queued': 0
            }
            
            print(f"✅ Crawler session cleared - status now idle")
            
            message = f"Crawler stopped. {queue_size} jobs removed from queue."
            if schedule_id:
                message += f" Schedule '{schedule_name}' has been deactivated."
            
            return {
                "success": True,
                "message": message,
                "jobs_removed": queue_size,
                "schedule_deactivated": bool(schedule_id)
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to purge queue")
    
    except Exception as e:
        print(f"❌ Error in stop_scraping: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# OUTREACH ENDPOINTS
# ============================================================================

@app.post("/api/outreach/send", tags=["Outreach"])
async def send_outreach(request: OutreachRequest, current_user: dict = Depends(get_current_user)):
    """Send outreach request to LavinMQ queue"""
    try:
        print("\n" + "="*60)
        print("📥 OUTREACH REQUEST RECEIVED")
        print("="*60)
        print(f"Total leads: {len(request.leads)}")
        print(f"Dry run: {request.dry_run}")
        print(f"Message: {request.message}")
        
        # Debug environment variables
        outreach_queue = os.getenv('OUTREACH_QUEUE')
        rabbitmq_host = os.getenv('RABBITMQ_HOST')
        print(f"OUTREACH_QUEUE env: {outreach_queue}")
        print(f"RABBITMQ_HOST env: {rabbitmq_host}")
        
        # Validate leads
        valid_leads = [
            lead for lead in request.leads
            if lead.get('name') and lead.get('profile_url')
        ]
        
        if not valid_leads:
            raise HTTPException(status_code=400, detail="No valid leads provided")
        
        print(f"✅ Valid leads: {len(valid_leads)}/{len(request.leads)}")
        
        # Debug each lead
        for i, lead in enumerate(valid_leads[:3]):  # Show first 3 leads
            print(f"  Lead {i+1}: {lead.get('name')} - {lead.get('profile_url')}")
        
        # Send each lead as separate message
        batch_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        queued_count = 0
        failed_count = 0
        
        for lead in valid_leads:
            print(f"\n📤 Attempting to queue: {lead['name']}")
            success = queue_publisher.publish_outreach_job(
                lead=lead,
                message_text=request.message,
                dry_run=request.dry_run,
                batch_id=batch_id
            )
            
            if success:
                queued_count += 1
                print(f"  ✓ Queued: {lead['name']}")
            else:
                failed_count += 1
                print(f"  ✗ Failed: {lead['name']}")
        
        print(f"\n📊 OUTREACH SUMMARY:")
        print(f"   Total leads: {len(request.leads)}")
        print(f"   Valid leads: {len(valid_leads)}")
        print(f"   Successfully queued: {queued_count}")
        print(f"   Failed to queue: {failed_count}")
        print(f"   Batch ID: {batch_id}")
        print("="*60 + "\n")
        
        return {
            "status": "success",
            "message": "Outreach messages queued successfully",
            "total_leads": len(request.leads),
            "valid_leads": len(valid_leads),
            "queued": queued_count,
            "failed": failed_count,
            "batch_id": batch_id,
            "dry_run": request.dry_run,
            "queue": outreach_queue
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/external/status/{schedule_id}", tags=["External Integration"])
async def get_external_schedule_status(schedule_id: str, current_user: dict = Depends(get_current_user)):
    """Get status of external schedule"""
    try:
        print(f"\n📊 EXTERNAL STATUS CHECK: {schedule_id}")
        
        # Get schedule
        schedule = ScheduleManager.get_by_id(schedule_id)
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        # Check if it's an external schedule
        if not schedule.get('external_source'):
            raise HTTPException(status_code=400, detail="Not an external schedule")
        
        external_metadata = schedule.get('external_metadata', {})
        
        # Determine current status
        current_status = schedule['status']
        execution_status = "pending"
        
        # Simple status check based on last_run
        if schedule.get('last_run'):
            execution_status = "completed"
        
        # Check if schedule time has passed
        schedule_datetime_str = external_metadata.get('schedule_datetime')
        is_past_due = False
        if schedule_datetime_str:
            schedule_dt = datetime.fromisoformat(schedule_datetime_str.replace('Z', '+00:00'))
            is_past_due = datetime.now(schedule_dt.tzinfo) > schedule_dt
        
        response_data = {
            "success": True,
            "schedule_id": schedule_id,
            "external_source": schedule.get('external_source'),
            "job_title": external_metadata.get('job_title'),
            "status": current_status,  # FIX: Use 'status' instead of 'schedule_status' for frontend compatibility
            "schedule_status": current_status,  # Keep for backward compatibility
            "execution_status": execution_status,
            "scheduled_for": external_metadata.get('schedule_datetime'),
            "is_past_due": is_past_due,
            "last_run": schedule.get('last_run'),
            "candidates_count": 0,  # Uses existing leads list
            "webhook_url": schedule.get('webhook_url'),
            "created_at": schedule.get('created_at')
        }
        
        print(f"✅ Status retrieved: {execution_status}")
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Status check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# ============================================================================
# AUTHENTICATION DEPENDENCY
# ============================================================================

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.post("/api/auth/login", tags=["Authentication"])
async def login(request: LoginRequest):
    """Login with email and password"""
    try:
        # Get user by email
        user = db.get_user_by_email(request.email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Verify password
        if not verify_password(request.password, user['password_hash']):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Create JWT token
        token = create_jwt_token(user)
        
        # Remove password hash from response
        user_response = {
            'id': user['id'],
            'email': user['email'],
            'name': user['name'],
            'role': user['role'],
            'created_at': user['created_at'].isoformat() if user['created_at'] else None
        }
        
        return {
            "success": True,
            "token": token,
            "user": user_response
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@app.get("/api/auth/me", tags=["Authentication"])
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    return {
        "success": True,
        "user": {
            'id': current_user['id'],
            'email': current_user['email'],
            'name': current_user['name'],
            'role': current_user['role'],
            'created_at': current_user['created_at'].isoformat() if current_user['created_at'] else None
        }
    }

@app.post("/api/auth/logout", tags=["Authentication"])
async def logout():
    """Logout (client-side token removal)"""
    return {
        "success": True,
        "message": "Logged out successfully"
    }

# ============================================================================
# DASHBOARD STATS ENDPOINTS
# ============================================================================

@app.get("/api/stats", tags=["Dashboard"])
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    """Get comprehensive dashboard statistics"""
    try:
        stats = db.get_dashboard_stats()
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        print(f"❌ Stats error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")

async def get_leads(
    template_id: Optional[str] = None,
    limit: Optional[int] = None,
    page: Optional[int] = Query(None, ge=1, description="Page number (starts from 1)"),
    per_page: Optional[int] = Query(None, ge=1, le=100, description="Items per page (max 100)"),
    search: Optional[str] = Query(None, description="Search in name, company, email"),
    sort: Optional[str] = Query(None, description="Sort field: name, company, email, date, connection_status"),
    order: Optional[str] = Query(None, description="Sort order: asc or desc"),
    current_user: dict = Depends(get_current_user)
):
    """Get all leads with optional filtering, pagination, search and sorting"""
    try:
        result = db.get_all_leads(
            template_id=template_id,
            limit=limit,
            page=page,
            per_page=per_page,
            search=search,
            sort=sort,
            order=order
        )
        return {
            "success": True,
            "count": len(result['leads']),
            "leads": result['leads'],
            "pagination": result['pagination']
        }
    except Exception as e:
        print(f"❌ Leads error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get leads: {str(e)}")

@app.get("/api/stats/templates", tags=["Dashboard"])
async def get_templates_count(current_user: dict = Depends(get_current_user)):
    """Get total templates count"""
    try:
        count = db.get_templates_count()
        return {
            "success": True,
            "count": count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get templates count: {str(e)}")

async def get_companies(
    page: Optional[int] = Query(None, ge=1, description="Page number (starts from 1)"),
    per_page: Optional[int] = Query(None, ge=1, le=100, description="Items per page (max 100)"),
    search: Optional[str] = Query(None, description="Search in company name or domain"),
    sort: Optional[str] = Query(None, description="Sort field: name, domain, created_at"),
    order: Optional[str] = Query(None, description="Sort order: asc or desc"),
    current_user: dict = Depends(get_current_user)
):
    """Get all companies with optional pagination, search and sorting"""
    try:
        result = db.get_all_companies(
            page=page,
            per_page=per_page,
            search=search,
            sort=sort,
            order=order
        )
        return {
            "success": True,
            "count": len(result['companies']),
            "companies": result['companies'],
            "pagination": result['pagination']
        }
    except Exception as e:
        print(f"❌ Companies error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get companies: {str(e)}")

# ============================================================================
# LEADS ENDPOINTS
# ============================================================================

@app.get("/api/leads", tags=["Leads"])
async def get_leads(
    template_id: Optional[str] = None,
    limit: Optional[int] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get all leads with optional filtering"""
    try:
        leads = db.get_all_leads(template_id=template_id, limit=limit)
        return {
            "success": True,
            "count": len(leads),
            "leads": leads
        }
    except Exception as e:
        print(f"❌ Leads error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get leads: {str(e)}")

# ============================================================================
# COMPANIES ENDPOINTS
# ============================================================================

@app.get("/api/companies", tags=["Companies"])
async def get_companies(current_user: dict = Depends(get_current_user)):
    """Get all companies"""
    try:
        companies = db.get_all_companies()
        return {
            "success": True,
            "count": len(companies),
            "companies": companies
        }
    except Exception as e:
        print(f"❌ Companies error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get companies: {str(e)}")

@app.get("/api/companies/{company_id}/templates", tags=["Companies"])
async def get_company_templates(
    company_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all templates belonging to a specific company"""
    try:
        templates = db.get_templates_by_company(company_id)
        return {
            "success": True,
            "company_id": company_id,
            "count": len(templates),
            "templates": templates
        }
    except Exception as e:
        print(f"❌ Get company templates error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get templates: {str(e)}")

@app.post("/api/companies", tags=["Companies"])
async def create_company(    company: CompanyCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create new company"""
    try:
        company_id = db.create_company({
            'name': company.name,
            'code': company.code
        })
        
        return {
            "success": True,
            "message": "Company created successfully",
            "company_id": company_id
        }
    except Exception as e:
        print(f"❌ Create company error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create company: {str(e)}")

# ============================================================================
# TEMPLATES CRUD ENDPOINTS
# ============================================================================

@app.get("/api/templates/{template_id}", tags=["Templates"])
async def get_template(
    template_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get single template by ID"""
    try:
        template = db.get_template_by_id(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        return {
            "success": True,
            "template": template
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Get template error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get template: {str(e)}")

@app.delete("/api/templates/{template_id}", tags=["Templates"])
async def delete_template(
    template_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete template"""
    try:
        db.delete_template(template_id)
        return {
            "success": True,
            "message": "Template deleted successfully"
        }
    except Exception as e:
        print(f"❌ Delete template error: {e}")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Template not found")
        raise HTTPException(status_code=500, detail=f"Failed to delete template: {str(e)}")

@app.put("/api/templates/{template_id}", tags=["Templates"])
async def update_template(
    template_id: str,
    updates: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Update template"""
    try:
        db.update_template(template_id, updates)
        return {
            "success": True,
            "message": "Template updated successfully"
        }
    except Exception as e:
        print(f"❌ Update template error: {e}")
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Template not found")
        raise HTTPException(status_code=500, detail=f"Failed to update template: {str(e)}")

# ============================================================================
# SERVER STARTUP
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Initialize services
    init_services()
    
    # Start server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
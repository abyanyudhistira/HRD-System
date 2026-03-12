"""
Supabase Helper for API
Centralized database operations
"""
from typing import Dict, List, Optional
from supabase import create_client, Client
import os

# Supabase client
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)


class ScheduleManager:
    """Manage crawler schedules in Supabase"""
    
    @staticmethod
    def get_all_simple() -> List[Dict]:
        """Get all schedules with template names (using FK relationship)"""
        try:
            response = supabase.table('crawler_schedules').select('''
                *,
                search_templates (
                    id,
                    name
                )
            ''').order('created_at', desc=True).execute()
            
            return response.data or []
            
        except Exception as e:
            print(f"Error getting schedules with JOIN: {e}")
            # Fallback: get without template names if FK not ready yet
            response = supabase.table('crawler_schedules')\
                .select('*')\
                .order('created_at', desc=True)\
                .execute()
            
            return response.data or []
    
    @staticmethod
    def get_by_id(schedule_id: str) -> Optional[Dict]:
        """Get schedule by ID"""
        try:
            response = supabase.table('crawler_schedules').select('''
                *,
                search_templates (
                    id,
                    name
                )
            ''').eq('id', schedule_id).execute()
            
            return response.data[0] if response.data else None
            
        except Exception as e:
            print(f"Error getting schedule with JOIN: {e}")
            # Fallback: get without template names if FK not ready yet
            response = supabase.table('crawler_schedules')\
                .select('*')\
                .eq('id', schedule_id)\
                .execute()
            
            return response.data[0] if response.data else None
    
    @staticmethod
    def create(data: Dict) -> Dict:
        """Create new schedule"""
        response = supabase.table('crawler_schedules').insert(data).execute()
        return response.data[0] if response.data else None
    
    @staticmethod
    def update(schedule_id: str, data: Dict) -> Dict:
        """Update schedule"""
        response = supabase.table('crawler_schedules').update(data).eq('id', schedule_id).execute()
        return response.data[0] if response.data else None
    
    @staticmethod
    def delete(schedule_id: str) -> bool:
        """Delete schedule"""
        try:
            response = supabase.table('crawler_schedules').delete().eq('id', schedule_id).execute()
            # Check if any rows were affected
            if not response.data:
                return False
            return True
        except Exception as e:
            print(f"Error deleting schedule: {e}")
            raise e
    
    @staticmethod
    def template_exists(template_id: str) -> bool:
        """Check if template exists"""
        response = supabase.table('search_templates').select('id').eq('id', template_id).execute()
        return bool(response.data)
    
    @staticmethod
    def update_schedule_status(schedule_id: str, is_active: bool) -> bool:
        """Update schedule status (active/inactive)"""
        try:
            status = 'active' if is_active else 'inactive'
            response = supabase.table('crawler_schedules').update({
                'status': status
            }).eq('id', schedule_id).execute()
            
            if response.data:
                print(f"✅ Schedule {schedule_id} status updated to: {status}")
                return True
            else:
                print(f"⚠️ No schedule found with ID: {schedule_id}")
                return False
                
        except Exception as e:
            print(f"❌ Error updating schedule status: {e}")
            return False


class CompanyManager:
    """Manage companies in Supabase"""
    
    @staticmethod
    def get_all(platform: Optional[str] = None) -> List[Dict]:
        """Get all companies, optionally filtered by platform"""
        query = supabase.table('companies').select('*')
        
        if platform:
            query = query.ilike('platform', f'%{platform}%')
        
        response = query.order('created_at', desc=True).execute()
        return response.data or []
    
    @staticmethod
    def get_by_id(company_id: str) -> Optional[Dict]:
        """Get company by ID"""
        response = supabase.table('companies').select('*').eq('id', company_id).execute()
        return response.data[0] if response.data else None


class LeadsManager:
    """Manage leads in Supabase"""
    
    @staticmethod
    def get_by_platform(platform: str, limit: int = 100, offset: int = 0) -> Dict:
        """Get leads by platform"""
        # Get companies by platform
        companies = supabase.table('companies').select('id, name, code, platform')\
            .ilike('platform', f'%{platform}%').execute()
        
        if not companies.data:
            return {'companies': [], 'templates': [], 'leads': [], 'total': 0}
        
        company_ids = [c['id'] for c in companies.data]
        
        # Get templates by company_ids
        templates = supabase.table('search_templates').select('id, name, company_id')\
            .in_('company_id', company_ids).execute()
        
        if not templates.data:
            return {
                'companies': companies.data,
                'templates': [],
                'leads': [],
                'total': 0
            }
        
        template_ids = [t['id'] for t in templates.data]
        
        # Get leads by template_ids
        leads = supabase.table('leads_list').select('*')\
            .in_('template_id', template_ids)\
            .order('date', desc=True)\
            .range(offset, offset + limit - 1).execute()
        
        # Get total count
        count = supabase.table('leads_list').select('id', count='exact')\
            .in_('template_id', template_ids).execute()
        
        return {
            'companies': companies.data,
            'templates': templates.data,
            'leads': leads.data or [],
            'total': count.count or 0
        }
    
    @staticmethod
    def get_by_company(company_id: str, limit: int = 100, offset: int = 0) -> Dict:
        """Get leads by company ID"""
        # Get templates by company_id
        templates = supabase.table('search_templates').select('id, name, company_id')\
            .eq('company_id', company_id).execute()
        
        if not templates.data:
            return {'templates': [], 'leads': [], 'total': 0}
        
        template_ids = [t['id'] for t in templates.data]
        
        # Get leads by template_ids
        leads = supabase.table('leads_list').select('*')\
            .in_('template_id', template_ids)\
            .order('date', desc=True)\
            .range(offset, offset + limit - 1).execute()
        
        # Get total count
        count = supabase.table('leads_list').select('id', count='exact')\
            .in_('template_id', template_ids).execute()
        
        return {
            'templates': templates.data,
            'leads': leads.data or [],
            'total': count.count or 0
        }


class ReQueueManager:
    """Manage re-queueing of failed leads"""
    
    @staticmethod
    def get_failed_leads(template_id: Optional[str] = None, check_profile_data: bool = True, check_scoring_data: bool = True) -> List[Dict]:
        """Get leads that failed scraping or scoring"""
        query = supabase.table('leads_list').select('*')
        
        # Filter by template if provided
        if template_id:
            query = query.eq('template_id', template_id)
        
        # Get all leads and filter in Python since Supabase OR with null checks can be tricky
        response = query.select('*, connection_status').execute()
        leads = response.data or []
        
        # Filter leads with missing data or 0 score - SIMPLIFIED LOGIC
        failed_leads = []
        for lead in leads:
            profile_data = lead.get('profile_data')
            scoring_data = lead.get('scoring_data')
            connection_status = lead.get('connection_status', '')
            
            needs_scraping = False
            needs_scoring = False
            should_requeue = False
            
            # SIMPLE VALIDATION LOGIC:
            # 1. Profile data kosong = perlu scraping
            if check_profile_data and (not profile_data or profile_data in [None, '', {}]):
                needs_scraping = True
                should_requeue = True
            
            # 2. Scoring data kosong ATAU score 0% = perlu scoring
            if check_scoring_data:
                if not scoring_data or scoring_data in [None, '', {}]:
                    needs_scoring = True
                    should_requeue = True
                else:
                    # Check for 0% score in existing scoring data
                    try:
                        if isinstance(scoring_data, dict):
                            score_data = scoring_data.get('score', {})
                            if isinstance(score_data, dict) and score_data.get('percentage', -1) == 0:
                                needs_scoring = True
                                should_requeue = True
                        elif isinstance(scoring_data, str):
                            import json
                            parsed_data = json.loads(scoring_data)
                            score_data = parsed_data.get('score', {})
                            if isinstance(score_data, dict) and score_data.get('percentage', -1) == 0:
                                needs_scoring = True
                                should_requeue = True
                    except:
                        # Invalid JSON = needs reprocessing
                        needs_scoring = True
                        should_requeue = True
            
            # 3. OVERRIDE: connection_status "scraped" tapi data kosong = tetap perlu scraping/scoring
            if connection_status == 'scraped':
                if not profile_data or profile_data in [None, '', {}]:
                    needs_scraping = True
                    should_requeue = True
                if not scoring_data or scoring_data in [None, '', {}]:
                    needs_scoring = True
                    should_requeue = True
            
            if should_requeue:
                # Add metadata about what needs processing
                lead_info = lead.copy()
                lead_info['needs_scraping'] = needs_scraping
                lead_info['needs_scoring'] = needs_scoring
                failed_leads.append(lead_info)
        
        return failed_leads


class SupabaseManager:
    """
    Lead management for API
    Simplified version without importing from crawler
    """
    def __init__(self):
        self.supabase = supabase
    
    def get_leads_by_template_id(self, template_id: str, limit=None):
        """Get leads for a template with processing status"""
        try:
            query = self.supabase.table('leads_list').select('*').eq('template_id', template_id)
            
            if limit:
                query = query.limit(limit)
            
            response = query.execute()
            leads = response.data or []
            
            # Add needs_processing flag based on validation logic
            for lead in leads:
                profile_data = lead.get('profile_data')
                scoring_data = lead.get('scoring_data')
                connection_status = lead.get('connection_status', '')
                score = lead.get('score', 0)
                
                needs_processing = False
                
                # Validation logic:
                # 1. Status pending → queue
                if connection_status == 'pending':
                    needs_processing = True
                    lead['status_reason'] = 'status_pending'
                
                # 2. Status scraped → check data
                elif connection_status == 'scraped':
                    # Check if profile_data or scoring_data is empty
                    if not profile_data or profile_data in [None, '', {}, '{}']:
                        needs_processing = True
                        lead['status_reason'] = 'profile_data_empty'
                    elif not scoring_data or scoring_data in [None, '', {}, '{}']:
                        needs_processing = True
                        lead['status_reason'] = 'scoring_data_empty'
                    elif score == 0 or score is None:
                        # Score 0 with no scoring_data → needs scoring
                        if not scoring_data or scoring_data in [None, '', {}, '{}']:
                            needs_processing = True
                            lead['status_reason'] = 'score_zero_no_data'
                        # Score 0 with scoring_data → valid (candidate not suitable), skip
                        else:
                            needs_processing = False
                            lead['status_reason'] = 'score_zero_valid'
                    else:
                        needs_processing = False
                        lead['status_reason'] = 'complete'
                
                # 3. Other status → check if data is empty
                else:
                    if not profile_data or profile_data in [None, '', {}, '{}']:
                        needs_processing = True
                        lead['status_reason'] = 'profile_data_empty'
                    elif not scoring_data or scoring_data in [None, '', {}, '{}']:
                        needs_processing = True
                        lead['status_reason'] = 'scoring_data_empty'
                
                lead['needs_processing'] = needs_processing
            
            return leads
            
        except Exception as e:
            print(f"Error getting leads: {e}")
            raise e
    
    def get_template_by_id(self, template_id: str):
        """Get template by ID"""
        try:
            response = self.supabase.table('search_templates').select('*').eq('id', template_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error getting template: {e}")
            return None
    
    def get_all_templates(self):
        """Get all templates"""
        try:
            response = self.supabase.table('search_templates').select('*').order('created_at', desc=True).execute()
            return response.data or []
        except Exception as e:
            print(f"Error getting templates: {e}")
            return []

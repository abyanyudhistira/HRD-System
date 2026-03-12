"""
Query Optimizer Helper - Optimized database queries with caching
"""
from typing import List, Dict, Optional, Any
from functools import lru_cache
import time
from datetime import datetime, timedelta


class QueryOptimizer:
    """Helper class for optimized database queries"""
    
    def __init__(self, supabase_client):
        self.client = supabase_client
        self._cache = {}
        self._cache_ttl = {}
    
    def _get_cache_key(self, table: str, filters: Dict) -> str:
        """Generate cache key from table and filters"""
        filter_str = "_".join([f"{k}={v}" for k, v in sorted(filters.items())])
        return f"{table}_{filter_str}"
    
    def _is_cache_valid(self, key: str, ttl_seconds: int = 60) -> bool:
        """Check if cache is still valid"""
        if key not in self._cache_ttl:
            return False
        
        cache_time = self._cache_ttl[key]
        return (time.time() - cache_time) < ttl_seconds
    
    def _set_cache(self, key: str, data: Any):
        """Set cache with timestamp"""
        self._cache[key] = data
        self._cache_ttl[key] = time.time()
    
    def _get_cache(self, key: str) -> Optional[Any]:
        """Get cached data if valid"""
        if key in self._cache:
            return self._cache[key]
        return None
    
    def clear_cache(self, table: Optional[str] = None):
        """Clear cache for specific table or all"""
        if table:
            # Clear only keys for this table
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(f"{table}_")]
            for key in keys_to_delete:
                del self._cache[key]
                del self._cache_ttl[key]
        else:
            # Clear all cache
            self._cache.clear()
            self._cache_ttl.clear()
    
    # ========================================================================
    # OPTIMIZED QUERIES - SCHEDULES
    # ========================================================================
    
    def get_schedules_optimized(
        self, 
        status: Optional[str] = None,
        external_source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        use_cache: bool = True,
        cache_ttl: int = 30
    ) -> List[Dict]:
        """
        Get schedules with optimized query and optional caching
        Uses indexes: idx_crawler_schedules_status, idx_crawler_schedules_external_source
        """
        # Build cache key
        cache_key = self._get_cache_key('schedules', {
            'status': status,
            'external_source': external_source,
            'limit': limit,
            'offset': offset
        })
        
        # Check cache
        if use_cache and self._is_cache_valid(cache_key, cache_ttl):
            cached_data = self._get_cache(cache_key)
            if cached_data is not None:
                return cached_data
        
        # Build query - select only needed columns
        query = self.client.table('crawler_schedules').select(
            'id, name, status, start_schedule, stop_schedule, last_run, '
            'template_id, company_id, external_source, created_at'
        )
        
        # Apply filters
        if status:
            query = query.eq('status', status)
        
        if external_source is not None:
            if external_source == 'null':
                query = query.is_('external_source', 'null')
            else:
                query = query.eq('external_source', external_source)
        
        # Order and limit
        query = query.order('created_at', desc=True).limit(limit).offset(offset)
        
        # Execute
        result = query.execute()
        data = result.data or []
        
        # Cache result
        if use_cache:
            self._set_cache(cache_key, data)
        
        return data
    
    def get_active_schedules_optimized(self, use_cache: bool = True) -> List[Dict]:
        """
        Get active schedules - heavily cached since this is called frequently
        Uses index: idx_crawler_schedules_status
        """
        return self.get_schedules_optimized(
            status='active',
            use_cache=use_cache,
            cache_ttl=60  # Cache for 1 minute
        )
    
    # ========================================================================
    # OPTIMIZED QUERIES - LEADS
    # ========================================================================
    
    def get_leads_by_template_optimized(
        self,
        template_id: str,
        connection_status: Optional[str] = None,
        has_profile_data: Optional[bool] = None,
        has_score: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        Get leads with optimized filtering
        Uses indexes: idx_leads_template_id, idx_leads_connection_status, idx_leads_unscraped
        """
        # Select only needed columns
        query = self.client.table('leads_list').select(
            'id, name, profile_url, connection_status, score, processed_at, created_at'
        )
        
        # Filter by template
        query = query.eq('template_id', template_id)
        
        # Filter by connection status
        if connection_status:
            query = query.eq('connection_status', connection_status)
        
        # Filter by profile data existence
        if has_profile_data is not None:
            if has_profile_data:
                query = query.not_.is_('profile_data', 'null')
            else:
                query = query.is_('profile_data', 'null')
        
        # Filter by score existence
        if has_score is not None:
            if has_score:
                query = query.not_.is_('score', 'null')
            else:
                query = query.is_('score', 'null')
        
        # Order by score (best first) then created_at
        if has_score:
            query = query.order('score', desc=True, nulls_last=True)
        query = query.order('created_at', desc=True)
        
        # Limit and offset
        query = query.limit(limit).offset(offset)
        
        # Execute
        result = query.execute()
        return result.data or []
    
    def get_unscraped_leads_optimized(
        self,
        template_id: str,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get leads that haven't been scraped yet
        Uses index: idx_leads_unscraped (optimized for profile_data IS NULL)
        """
        return self.get_leads_by_template_optimized(
            template_id=template_id,
            has_profile_data=False,
            limit=limit
        )
    
    def check_lead_exists_optimized(self, profile_url: str) -> Optional[Dict]:
        """
        Check if lead exists by profile URL
        Uses index: idx_leads_profile_url (most critical index)
        """
        # Select only needed columns for existence check
        result = self.client.table('leads_list').select(
            'id, profile_url, connection_status, profile_data, score'
        ).eq('profile_url', profile_url).limit(1).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
    
    # ========================================================================
    # OPTIMIZED QUERIES - TEMPLATES
    # ========================================================================
    
    def get_templates_optimized(
        self,
        company_id: Optional[str] = None,
        external_source: Optional[str] = None,
        use_cache: bool = True,
        cache_ttl: int = 300  # 5 minutes
    ) -> List[Dict]:
        """
        Get templates with caching
        Uses indexes: idx_search_templates_company_id, idx_search_templates_external_source
        """
        # Build cache key
        cache_key = self._get_cache_key('templates', {
            'company_id': company_id,
            'external_source': external_source
        })
        
        # Check cache
        if use_cache and self._is_cache_valid(cache_key, cache_ttl):
            cached_data = self._get_cache(cache_key)
            if cached_data is not None:
                return cached_data
        
        # Build query
        query = self.client.table('search_templates').select(
            'id, name, job_title, company_id, external_source, created_at'
        )
        
        # Apply filters
        if company_id:
            query = query.eq('company_id', company_id)
        
        if external_source is not None:
            if external_source == 'null':
                query = query.is_('external_source', 'null')
            else:
                query = query.eq('external_source', external_source)
        
        # Order by created_at
        query = query.order('created_at', desc=True)
        
        # Execute
        result = query.execute()
        data = result.data or []
        
        # Cache result
        if use_cache:
            self._set_cache(cache_key, data)
        
        return data
    
    def get_template_by_id_optimized(
        self,
        template_id: str,
        use_cache: bool = True,
        cache_ttl: int = 300
    ) -> Optional[Dict]:
        """
        Get template by ID with caching
        """
        cache_key = f"template_{template_id}"
        
        # Check cache
        if use_cache and self._is_cache_valid(cache_key, cache_ttl):
            cached_data = self._get_cache(cache_key)
            if cached_data is not None:
                return cached_data
        
        # Query
        result = self.client.table('search_templates').select('*').eq('id', template_id).limit(1).execute()
        
        if result.data and len(result.data) > 0:
            data = result.data[0]
            if use_cache:
                self._set_cache(cache_key, data)
            return data
        
        return None
    
    # ========================================================================
    # OPTIMIZED QUERIES - STATISTICS
    # ========================================================================
    
    def get_stats_optimized(self, use_cache: bool = True, cache_ttl: int = 60) -> Dict:
        """
        Get dashboard statistics with caching
        Uses count queries with indexes for fast aggregation
        """
        cache_key = "stats_dashboard"
        
        # Check cache
        if use_cache and self._is_cache_valid(cache_key, cache_ttl):
            cached_data = self._get_cache(cache_key)
            if cached_data is not None:
                return cached_data
        
        # Run parallel count queries (fast with indexes)
        stats = {}
        
        # Total schedules
        result = self.client.table('crawler_schedules').select('id', count='exact').execute()
        stats['total_schedules'] = result.count or 0
        
        # Active schedules (uses idx_crawler_schedules_status)
        result = self.client.table('crawler_schedules').select('id', count='exact').eq('status', 'active').execute()
        stats['active_schedules'] = result.count or 0
        
        # Total leads
        result = self.client.table('leads_list').select('id', count='exact').execute()
        stats['total_leads'] = result.count or 0
        
        # Scored leads (uses idx_leads_scored)
        result = self.client.table('leads_list').select('id', count='exact').not_.is_('score', 'null').execute()
        stats['scored_leads'] = result.count or 0
        
        # Total templates
        result = self.client.table('search_templates').select('id', count='exact').execute()
        stats['total_templates'] = result.count or 0
        
        # Cache result
        if use_cache:
            self._set_cache(cache_key, stats)
        
        return stats
    
    # ========================================================================
    # BATCH OPERATIONS
    # ========================================================================
    
    def batch_update_leads(self, updates: List[Dict]) -> bool:
        """
        Batch update leads for better performance
        """
        try:
            for update in updates:
                profile_url = update.pop('profile_url')
                self.client.table('leads_list').update(update).eq('profile_url', profile_url).execute()
            
            # Clear leads cache after batch update
            self.clear_cache('leads')
            return True
        except Exception as e:
            print(f"Batch update error: {e}")
            return False

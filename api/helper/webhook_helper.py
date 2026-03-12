"""
Webhook Helper - Send notifications to external systems
"""
import requests
import time
import json
from datetime import datetime
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class WebhookNotifier:
    """Helper class for sending webhook notifications with retry logic"""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 2.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
    
    def send_completion_notification(
        self,
        webhook_url: str,
        schedule_id: str,
        schedule_data: Dict,
        results: Dict,
        timeout: int = 30
    ) -> bool:
        """
        Send completion notification to webhook URL with retry logic
        
        Args:
            webhook_url: URL to send notification to
            schedule_id: Schedule ID
            schedule_data: Schedule information
            results: Scraping results
            timeout: Request timeout in seconds
            
        Returns:
            bool: True if notification sent successfully, False otherwise
        """
        if not webhook_url:
            logger.warning(f"No webhook URL provided for schedule {schedule_id}")
            return False
        
        # Prepare notification payload
        payload = self._prepare_payload(schedule_id, schedule_data, results)
        
        # Send with retry logic
        return self._send_with_retry(webhook_url, payload, timeout)
    
    def _prepare_payload(
        self,
        schedule_id: str,
        schedule_data: Dict,
        results: Dict
    ) -> Dict[str, Any]:
        """Prepare webhook notification payload"""
        
        external_metadata = schedule_data.get('external_metadata', {})
        
        payload = {
            "schedule_id": schedule_id,
            "status": "completed",
            "started_at": schedule_data.get('created_at'),
            "completed_at": datetime.now().isoformat(),
            "results": {
                "total_leads": results.get('total_leads', 0),
                "scraped_profiles": results.get('scraped_profiles', 0),
                "scored_profiles": results.get('scored_profiles', 0),
                "failed_profiles": results.get('failed_profiles', 0),
                "success_rate": results.get('success_rate', '0%')
            },
            "external_metadata": external_metadata,
            "webhook_sent_at": datetime.now().isoformat()
        }
        
        # Add job-specific info if available
        if external_metadata:
            payload["job_info"] = {
                "job_title": external_metadata.get('job_title'),
                "external_job_id": external_metadata.get('external_job_id'),
                "schedule_datetime": external_metadata.get('schedule_datetime')
            }
        
        return payload
    
    def _send_with_retry(
        self,
        webhook_url: str,
        payload: Dict,
        timeout: int
    ) -> bool:
        """Send webhook with exponential backoff retry logic"""
        
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'LinkedIn-Scraper-Webhook/1.0'
        }
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Sending webhook notification (attempt {attempt}/{self.max_retries})")
                logger.info(f"URL: {webhook_url}")
                logger.info(f"Payload: {json.dumps(payload, indent=2)}")
                
                response = requests.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout
                )
                
                # Check if request was successful
                if response.status_code in [200, 201, 202, 204]:
                    logger.info(f"✅ Webhook sent successfully (status: {response.status_code})")
                    logger.info(f"Response: {response.text[:200]}")
                    return True
                else:
                    logger.warning(f"⚠ Webhook failed with status {response.status_code}")
                    logger.warning(f"Response: {response.text[:200]}")
                    
                    # Don't retry for client errors (4xx)
                    if 400 <= response.status_code < 500:
                        logger.error(f"❌ Client error {response.status_code}, not retrying")
                        return False
            
            except requests.exceptions.Timeout:
                logger.warning(f"⚠ Webhook timeout (attempt {attempt}/{self.max_retries})")
            
            except requests.exceptions.ConnectionError:
                logger.warning(f"⚠ Webhook connection error (attempt {attempt}/{self.max_retries})")
            
            except requests.exceptions.RequestException as e:
                logger.warning(f"⚠ Webhook request error: {e} (attempt {attempt}/{self.max_retries})")
            
            except Exception as e:
                logger.error(f"❌ Unexpected webhook error: {e} (attempt {attempt}/{self.max_retries})")
            
            # Wait before retry (exponential backoff)
            if attempt < self.max_retries:
                delay = self.retry_delay * (2 ** (attempt - 1))  # 2s, 4s, 8s
                logger.info(f"⏳ Waiting {delay}s before retry...")
                time.sleep(delay)
        
        logger.error(f"❌ Webhook failed after {self.max_retries} attempts")
        return False
    
    def send_error_notification(
        self,
        webhook_url: str,
        schedule_id: str,
        schedule_data: Dict,
        error_message: str,
        timeout: int = 30
    ) -> bool:
        """Send error notification to webhook URL"""
        
        if not webhook_url:
            return False
        
        external_metadata = schedule_data.get('external_metadata', {})
        
        payload = {
            "schedule_id": schedule_id,
            "status": "failed",
            "started_at": schedule_data.get('created_at'),
            "failed_at": datetime.now().isoformat(),
            "error": {
                "message": error_message,
                "timestamp": datetime.now().isoformat()
            },
            "external_metadata": external_metadata,
            "webhook_sent_at": datetime.now().isoformat()
        }
        
        return self._send_with_retry(webhook_url, payload, timeout)


# Global webhook notifier instance
webhook_notifier = WebhookNotifier(max_retries=3, retry_delay=2.0)


def check_schedule_completion(supabase_client, schedule_id: str) -> Optional[Dict]:
    """
    Check if a schedule is completed and return completion statistics
    
    Args:
        supabase_client: Supabase client instance
        schedule_id: Schedule ID to check
        
    Returns:
        Dict with completion stats if completed, None if still in progress
    """
    try:
        # Get schedule info
        schedule_result = supabase_client.table('crawler_schedules').select('*').eq('id', schedule_id).execute()
        
        if not schedule_result.data:
            logger.warning(f"Schedule {schedule_id} not found")
            return None
        
        schedule = schedule_result.data[0]
        template_id = schedule.get('template_id')
        
        if not template_id:
            logger.warning(f"No template_id for schedule {schedule_id}")
            return None
        
        # Get all leads for this template
        leads_result = supabase_client.table('leads_list').select('*').eq('template_id', template_id).execute()
        
        if not leads_result.data:
            logger.info(f"No leads found for template {template_id}")
            return None
        
        leads = leads_result.data
        total_leads = len(leads)
        
        # Count completion status
        scraped_profiles = 0
        scored_profiles = 0
        failed_profiles = 0
        
        for lead in leads:
            profile_data = lead.get('profile_data')
            score = lead.get('score')
            connection_status = lead.get('connection_status', '')
            
            # Check if scraped
            if profile_data and profile_data not in [None, '', '{}', {}]:
                scraped_profiles += 1
            
            # Check if scored
            if score is not None and score != 0:
                scored_profiles += 1
            
            # Check if failed
            if connection_status == 'failed':
                failed_profiles += 1
        
        # Calculate completion percentage
        completion_rate = (scraped_profiles / total_leads * 100) if total_leads > 0 else 0
        success_rate = f"{completion_rate:.1f}%"
        
        # Consider completed if 90% or more profiles are processed
        is_completed = completion_rate >= 90.0
        
        results = {
            'total_leads': total_leads,
            'scraped_profiles': scraped_profiles,
            'scored_profiles': scored_profiles,
            'failed_profiles': failed_profiles,
            'success_rate': success_rate,
            'completion_rate': completion_rate,
            'is_completed': is_completed
        }
        
        logger.info(f"Schedule {schedule_id} completion check: {results}")
        
        return results if is_completed else None
    
    except Exception as e:
        logger.error(f"Error checking schedule completion: {e}")
        return None


def send_completion_webhook(supabase_client, schedule_id: str) -> bool:
    """
    Check if schedule is completed and send webhook notification if needed
    
    Args:
        supabase_client: Supabase client instance
        schedule_id: Schedule ID to check
        
    Returns:
        bool: True if webhook sent or not needed, False if error
    """
    try:
        # Get schedule info
        schedule_result = supabase_client.table('crawler_schedules').select('*').eq('id', schedule_id).execute()
        
        if not schedule_result.data:
            logger.warning(f"Schedule {schedule_id} not found")
            return False
        
        schedule = schedule_result.data[0]
        webhook_url = schedule.get('webhook_url')
        
        # Skip if no webhook URL
        if not webhook_url:
            logger.info(f"No webhook URL for schedule {schedule_id}, skipping notification")
            return True
        
        # Check if already notified
        external_metadata = schedule.get('external_metadata', {})
        if external_metadata.get('webhook_sent'):
            logger.info(f"Webhook already sent for schedule {schedule_id}")
            return True
        
        # Check completion status
        results = check_schedule_completion(supabase_client, schedule_id)
        
        if not results:
            logger.info(f"Schedule {schedule_id} not yet completed")
            return True
        
        # Send webhook notification
        success = webhook_notifier.send_completion_notification(
            webhook_url=webhook_url,
            schedule_id=schedule_id,
            schedule_data=schedule,
            results=results
        )
        
        if success:
            # Mark as webhook sent
            external_metadata['webhook_sent'] = True
            external_metadata['webhook_sent_at'] = datetime.now().isoformat()
            
            supabase_client.table('crawler_schedules').update({
                'external_metadata': external_metadata
            }).eq('id', schedule_id).execute()
            
            logger.info(f"✅ Webhook notification sent for schedule {schedule_id}")
        else:
            logger.error(f"❌ Failed to send webhook for schedule {schedule_id}")
        
        return success
    
    except Exception as e:
        logger.error(f"Error sending completion webhook: {e}")
        return False
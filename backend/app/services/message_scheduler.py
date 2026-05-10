"""
Simplified message scheduler without ARQ.
Messages are sent directly without background job queueing.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List
import asyncio
import redis.asyncio as redis
from app.config import REDIS_URL
from app.logger import get_logger
from app.services.whatsapp_service import send_template_message

logger = get_logger(__name__)

# ✅ Global Redis client for message deduplication
_redis_client: Optional[redis.Redis] = None

async def _get_redis_client() -> redis.Redis:
    """Get or create Redis client for message deduplication."""
    global _redis_client
    if _redis_client is None:
        _redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def _to_dt(v: Any) -> Optional[datetime]:
    """Convert various datetime formats to datetime object."""
    try:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        to_dt = getattr(v, "to_datetime", None)
        if callable(to_dt):
            return to_dt()
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


# ✅ MESSAGE DEDUPLICATION HELPER
async def _is_message_already_sent(phone: str, template_name: str) -> bool:
    """Check if message was already sent (Redis cache)."""
    try:
        redis_client = await _get_redis_client()
        message_key = f"message:{phone}:{template_name}"
        result = await redis_client.get(message_key)
        return result is not None
    except Exception as e:
        logger.error(f"Failed to check message cache: {e}")
        return False


async def _mark_message_sent(phone: str, template_name: str, ttl_seconds: int = 86400) -> None:
    """Mark message as sent in Redis (24 hour TTL by default)."""
    try:
        redis_client = await _get_redis_client()
        message_key = f"message:{phone}:{template_name}"
        await redis_client.setex(message_key, ttl_seconds, "sent")
        logger.info(f"Marked message as sent: {message_key}")
    except Exception as e:
        logger.error(f"Failed to mark message as sent: {e}")


async def schedule_at(
    run_at: datetime,
    template_name: str,
    token_context: Dict[str, Any],
    params: List[str],
) -> None:
    """Schedule a message to be sent at a specific time.
    
    ✅ NO ARQ - sends directly with asyncio.sleep() delay
    """
    try:
        patient_phone = token_context.get("patient_phone", "")
        
        # ✅ CHECK IF MESSAGE ALREADY SENT
        if await _is_message_already_sent(patient_phone, template_name):
            logger.info(f"Message already sent, skipping: {template_name} to {patient_phone}")
            return
        
        # Calculate delay
        now = datetime.now(timezone.utc)
        try:
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)
            else:
                run_at = run_at.astimezone(timezone.utc)
        except Exception:
            run_at = now
        
        delay_seconds = (run_at - now).total_seconds()
        
        if delay_seconds <= 0:
            # Send immediately
            logger.info(f"Sending message immediately: {template_name} to {patient_phone}")
            await send_template_message(patient_phone, template_name, params)
            await _mark_message_sent(patient_phone, template_name)
        else:
            # Schedule with asyncio.sleep()
            logger.info(f"Scheduling message in {delay_seconds}s: {template_name} to {patient_phone}")
            
            async def delayed_send():
                try:
                    await asyncio.sleep(delay_seconds)
                    logger.info(f"Sending scheduled message: {template_name} to {patient_phone}")
                    await send_template_message(patient_phone, template_name, params)
                    await _mark_message_sent(patient_phone, template_name)
                except Exception as e:
                    logger.error(f"Failed to send scheduled message: {e}")
            
            # Fire and forget - don't wait for completion
            asyncio.create_task(delayed_send())
            
    except Exception as e:
        logger.error(f"Failed to schedule message: {e}")


async def schedule_messages(token: Dict[str, Any], is_webhook_trigger: bool = False) -> None:
    """Schedule reminder messages for a token.
    
    ✅ NO ARQ - uses asyncio tasks directly
    
    Args:
        token: Token dictionary with patient info
        is_webhook_trigger: True if called from webhook (patient replied YES)
    """
    try:
        patient_phone = token.get("patient_phone", "")
        token_id = token.get("id", "")
        estimated_wait_time = token.get("estimated_wait_time", 0)
        
        # ✅ CHECK IF MESSAGES ALREADY SCHEDULED
        key_message = "queue_update_alert"
        if await _is_message_already_sent(patient_phone, key_message):
            logger.info(f"Messages already scheduled for token {token_id}, skipping")
            return
        
        logger.info(f"Scheduling messages for token {token_id}, phone: {patient_phone}")
        
        # Mark key message as sent to prevent duplicates
        await _mark_message_sent(patient_phone, key_message)
        
        # Schedule follow-up messages based on estimated wait time
        if estimated_wait_time > 0:
            # Schedule final alert at 80% of estimated wait time
            final_alert_delay = int(estimated_wait_time * 0.8)
            if final_alert_delay > 0:
                run_at = datetime.now(timezone.utc) + timedelta(minutes=final_alert_delay)
                await schedule_at(
                    run_at,
                    "final_alert",
                    token,
                    [
                        token.get("patient_name", "Patient"),
                        token.get("token_number", "0")
                    ]
                )
        
        logger.info(f"Message scheduling completed for token {token_id}")
        
    except Exception as e:
        logger.error(f"Failed to schedule messages: {e}")


async def schedule_confirmation_checks(
    token_id: str,
    first_delay_minutes: int = 15,
    second_delay_minutes: int = 15,
) -> None:
    """Send confirmation check messages."""
    try:
        # This would send reminder messages to patient to confirm attendance
        # For now, just log it
        logger.info(f"Confirmation check scheduled for token {token_id}")
        logger.info(f"  First check in {first_delay_minutes}m, second in {second_delay_minutes}m")
        
        # You could implement actual sending here if needed
        
    except Exception as e:
        logger.error(f"Failed to schedule confirmation checks: {e}")


async def schedule_skip_messages(token_id: str) -> None:
    """Send skip notification."""
    try:
        logger.info(f"Skip notification scheduled for token {token_id}")
        
        # You could implement actual sending here if needed
        
    except Exception as e:
        logger.error(f"Failed to schedule skip message: {e}")


# ✅ CLEANUP FUNCTION
async def close_redis():
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        try:
            await _redis_client.close()
            _redis_client = None
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis: {e}")
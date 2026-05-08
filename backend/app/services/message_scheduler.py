"""Message scheduling via arq (Async Redis Queue) for distributed task processing.

Enqueues background jobs to the arq worker pool instead of running in-memory
with asyncio.sleep or APScheduler. Jobs persist in Redis and survive app restarts.

These functions enqueue jobs; execution happens in the separate `arq` worker process.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from arq import create_pool

from app.config import REDIS_URL
from app.logger import get_logger

logger = get_logger(__name__)


async def _get_arq_pool():
    """Get or create arq connection pool."""
    return await create_pool(REDIS_URL)


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


async def schedule_at(
    run_at: datetime,
    template_name: str,
    token_context: Dict[str, Any],
    params: List[str],
) -> None:
    """Enqueue a message to be sent at a specific time via arq."""
    try:
        now = datetime.now(timezone.utc)
        run_at_utc = run_at

        try:
            if run_at_utc.tzinfo is None:
                run_at_utc = run_at_utc.replace(tzinfo=timezone.utc)
            else:
                run_at_utc = run_at_utc.astimezone(timezone.utc)
        except Exception:
            run_at_utc = now

        pool = await _get_arq_pool()
        job = await pool.enqueue_job(
            "send_message_delayed",
            token_context,
            template_name,
            params,
            _defer_until=run_at_utc,
        )
        logger.debug(f"Enqueued job {job.id}: {template_name} at {run_at_utc}")
        await pool.close()
    except Exception as e:
        logger.error(f"Failed to enqueue message job: {e}")
        raise


async def schedule_messages(token: Dict[str, Any], is_webhook_trigger: bool = False) -> None:
    """Enqueue reminder-message orchestration job for a token."""
    try:
        pool = await _get_arq_pool()
        job = await pool.enqueue_job(
            "schedule_messages_job",
            token,
            is_webhook_trigger,
        )
        logger.info(f"Enqueued schedule_messages_job: {job.id}")
        await pool.close()
    except Exception as e:
        logger.error(f"Failed to enqueue schedule_messages_job: {e}")
        raise


async def schedule_confirmation_checks(
    token_id: str,
    first_delay_minutes: int = 15,
    second_delay_minutes: int = 15,
) -> None:
    """Enqueue confirmation check job via arq."""
    try:
        pool = await _get_arq_pool()
        job = await pool.enqueue_job(
            "check_confirmation_job",
            token_id,
            first_delay_minutes,
            second_delay_minutes,
        )
        logger.info(f"Enqueued check_confirmation_job: {job.id} for token {token_id}")
        await pool.close()
    except Exception as e:
        logger.error(f"Failed to enqueue check_confirmation_job: {e}")
        raise


async def schedule_skip_messages(token_id: str) -> None:
    """Enqueue skip notification job via arq."""
    try:
        pool = await _get_arq_pool()
        job = await pool.enqueue_job(
            "schedule_skip_message_job",
            token_id,
        )
        logger.info(f"Enqueued schedule_skip_message_job: {job.id} for token {token_id}")
        await pool.close()
    except Exception as e:
        logger.error(f"Failed to enqueue schedule_skip_message_job: {e}")
        raise

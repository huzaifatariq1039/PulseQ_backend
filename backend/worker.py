"""Async Redis Queue (arq) worker for background tasks.

Define job functions that will run in a separate worker process
connected to Upstash serverless Redis.

Jobs are enqueued from FastAPI routes/services and executed by the
worker pool running alongside the main app.

Usage:
    arq backend.worker.WorkerSettings
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.logger import get_logger
from app.services.whatsapp_service import send_template_message
from app.config import REDIS_URL, REDIS_SOCKET_TIMEOUT, REDIS_SOCKET_CONNECT_TIMEOUT
from app.database import get_db

logger = get_logger(__name__)


# ============================================================================
# JOB: send_message_delayed
# ============================================================================
async def send_message_delayed(ctx: Dict[str, Any], template_name: str, params: List[str]) -> None:
    """Send a WhatsApp template message to a patient.

    Args:
        ctx: Token/appointment context dict with patient_phone, etc.
        template_name: Name of WhatsApp template
        params: Template parameters
    """
    try:
        to = str(ctx.get("patient_phone") or "").strip()
        if not to:
            logger.warning(f"No phone number in context for template {template_name}")
            return
        
        await send_template_message(to, template_name, params)
        logger.info(f"✅ Sent {template_name} to {to}")
    except Exception as e:
        logger.error(f"❌ Failed to send {template_name}: {e}")
        raise


# ============================================================================
# JOB: schedule_messages_job
# ============================================================================
async def schedule_messages_job(
    token: Dict[str, Any],
    is_webhook_trigger: bool = False
) -> None:
    """Enqueue multiple confirmation/reminder messages for a token.

    This job builds the patient/doctor/hospital context and enqueues
    individual send_message_delayed jobs at appropriate times.

    Args:
        token: Token dict with appointment_date, patient info, etc.
        is_webhook_trigger: If True, skip initial confirmation (webhook YES reply)
    """
    from arq import create_pool
    
    logger.info(f"Processing schedule_messages_job for token")
    
    try:
        # Helper to convert various datetime formats to UTC datetime
        def _to_dt(v: Any) -> Optional[datetime]:
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

        # Build context from token
        ctx: Dict[str, Any] = dict(token or {})

        appt = _to_dt(ctx.get("appointment_time")) or _to_dt(ctx.get("appointment_date"))
        if appt is None:
            logger.warning("No appointment time found in token")
            return

        try:
            if appt.tzinfo is None:
                appt = appt.replace(tzinfo=timezone.utc)
            else:
                appt = appt.astimezone(timezone.utc)
        except Exception:
            pass

        now = datetime.now(timezone.utc)

        try:
            est_wait_time = float(ctx.get("estimated_wait_time") or 0)
        except (ValueError, TypeError):
            est_wait_time = 0.0

        expected_appt = appt + timedelta(minutes=est_wait_time)
        true_wait_minutes = (expected_appt - now).total_seconds() / 60.0

        phone = str(ctx.get("patient_phone") or "").strip()
        if not phone:
            logger.warning("No phone in token context")
            return

        # Connect to arq pool for enqueueing sub-jobs
        pool = await create_pool(REDIS_URL)

        # Send initial booking confirmation (unless webhook trigger)
        if not is_webhook_trigger:
            confirm_params = [
                str(ctx.get("doctor_name") or "Doctor"),
                str(ctx.get("patient_name") or "Patient"),
                str(ctx.get("hospital_name") or "Hospital"),
                str(ctx.get("department") or "General"),
                str(int(true_wait_minutes) if true_wait_minutes > 0 else "0"),
            ]
            await pool.enqueue_job(
                "send_message_delayed",
                ctx,
                "token_number",
                confirm_params,
                _defer_until=now  # Send immediately
            )

        # Skip scheduling if appointment is imminent (< 5 min)
        if true_wait_minutes < 5:
            logger.info(f"Skipping reminder scheduling: appointment in {true_wait_minutes:.0f} min")
            await pool.close()
            return

        patient_name = str(ctx.get("patient_name") or "Patient")
        token_number = str(ctx.get("token_number") or "")
        hospital_name = str(ctx.get("hospital_name") or "Clinic")

        # Schedule reminder messages based on wait time
        if true_wait_minutes > 60:
            # Case 1: Long wait (> 60 min) - 3 messages
            await pool.enqueue_job(
                "send_message_delayed",
                ctx,
                "queue_update_alert",
                [patient_name, "1", str(int(true_wait_minutes - 60)), hospital_name, token_number],
                _defer_until=expected_appt - timedelta(minutes=60)
            )
            await pool.enqueue_job(
                "send_message_delayed",
                ctx,
                "final_alert",
                [patient_name, token_number],
                _defer_until=expected_appt - timedelta(minutes=30)
            )
            await pool.enqueue_job(
                "send_message_delayed",
                ctx,
                "patient_call_alert",
                [patient_name],
                _defer_until=expected_appt - timedelta(minutes=10)
            )
            logger.info(f"Scheduled 3 messages (long wait: {true_wait_minutes:.0f} min)")

        elif 30 < true_wait_minutes <= 60:
            # Case 2: Medium wait (30-60 min) - 2 messages
            await pool.enqueue_job(
                "send_message_delayed",
                ctx,
                "final_alert",
                [patient_name, token_number],
                _defer_until=expected_appt - timedelta(minutes=30)
            )
            await pool.enqueue_job(
                "send_message_delayed",
                ctx,
                "patient_call_alert",
                [patient_name],
                _defer_until=expected_appt - timedelta(minutes=10)
            )
            logger.info(f"Scheduled 2 messages (medium wait: {true_wait_minutes:.0f} min)")

        else:
            # Case 3: Short wait (5-30 min) - 2 messages
            await pool.enqueue_job(
                "send_message_delayed",
                ctx,
                "final_alert",
                [patient_name, token_number],
                _defer_until=now + timedelta(minutes=2)
            )
            await pool.enqueue_job(
                "send_message_delayed",
                ctx,
                "patient_call_alert",
                [patient_name],
                _defer_until=expected_appt - timedelta(minutes=2)
            )
            logger.info(f"Scheduled 2 messages (short wait: {true_wait_minutes:.0f} min)")

        await pool.close()

    except Exception as e:
        logger.error(f"❌ schedule_messages_job failed: {e}")
        raise


# ============================================================================
# JOB: check_confirmation_job
# ============================================================================
async def check_confirmation_job(
    token_id: str,
    first_delay_minutes: int = 15,
    second_delay_minutes: int = 15
) -> None:
    """Check if token was confirmed and send reminders/cancel if not.

    1. Wait first_delay_minutes
    2. If still pending, send reminder
    3. Wait second_delay_minutes more
    4. If still pending, cancel and send cancellation messages

    Args:
        token_id: Token ID to check
        first_delay_minutes: Minutes before sending first reminder (default 15)
        second_delay_minutes: Minutes before auto-cancel (default 15)
    """
    import asyncio
    from arq import create_pool
    
    try:
        db = next(get_db())

        # First check
        await asyncio.sleep(first_delay_minutes * 60)

        from app.db_models import Token

        token = db.query(Token).filter(Token.id == token_id).first()
        if not token:
            logger.warning(f"Token {token_id} not found")
            return

        if token.status == "pending":
            phone = token.patient_phone
            patient_name = token.patient_name or "Patient"

            if phone:
                await send_template_message(phone, "reminder_for_confirmation", [])
                logger.info(f"Sent confirmation reminder to {phone}")

            # Second check
            await asyncio.sleep(second_delay_minutes * 60)
            db.refresh(token)

            if token.status == "pending":
                # Auto-cancel
                token.status = "cancelled"
                token.cancelled_at = datetime.utcnow()
                token.updated_at = datetime.utcnow()
                db.commit()
                logger.info(f"Auto-cancelled token {token_id}")

                if phone:
                    await send_template_message(phone, "cancelled", [patient_name])
                    logger.info(f"Sent cancellation message to {phone}")

                try:
                    from app.services.queue_management_service import QueueManagementService
                    await QueueManagementService.recalculate_positions(
                        token.doctor_id, token.hospital_id, token.appointment_date
                    )
                except Exception as e:
                    logger.error(f"Error recalculating positions: {e}")

                await asyncio.sleep(2 * 60)

                if phone:
                    await send_template_message(phone, "template", [])
                    logger.info(f"Sent thank-you template to {phone}")

    except Exception as e:
        logger.error(f"❌ check_confirmation_job failed: {e}")
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass


# ============================================================================
# JOB: schedule_skip_message_job
# ============================================================================
async def schedule_skip_message_job(token_id: str) -> None:
    """Send skip notification 10 minutes after token is skipped.

    Args:
        token_id: Token ID that was skipped
    """
    import asyncio

    try:
        await asyncio.sleep(10 * 60)

        db = next(get_db())

        from app.db_models import Token

        token = db.query(Token).filter(Token.id == token_id).first()
        if not token:
            logger.warning(f"Token {token_id} not found for skip notification")
            return

        current_status = str(
            token.status.value if hasattr(token.status, "value") else token.status
        ).lower()

        if current_status == "skipped":
            phone = token.patient_phone
            patient_name = token.patient_name or "Patient"
            token_number = str(token.display_code or token.token_number or "")

            if phone:
                await send_template_message(phone, "skipped", [patient_name, token_number])
                logger.info(f"Sent skip notification to {phone}")
                await asyncio.sleep(2 * 60)

                if phone:
                    await send_template_message(phone, "template", [])
                    logger.info(f"Sent thank-you template to {phone}")

    except Exception as e:
        logger.error(f"❌ schedule_skip_message_job failed: {e}")
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass


# ============================================================================
# ARQ WORKER CONFIGURATION
# ============================================================================
class WorkerSettings:
    """Configuration for arq worker pool."""

    # Redis connection: auto-detect SSL from rediss:// scheme
    redis_pool = REDIS_URL

    # Job functions this worker handles
    functions = [
        send_message_delayed,
        schedule_messages_job,
        check_confirmation_job,
        schedule_skip_message_job,
    ]

    # Job timeout (seconds)
    job_timeout = 3600  # 1 hour

    # Number of concurrent jobs per worker
    max_concurrent = 100

    # Keep Redis connections alive
    keep_result = 600  # 10 min result retention

    # Log level
    log_level = logging.INFO

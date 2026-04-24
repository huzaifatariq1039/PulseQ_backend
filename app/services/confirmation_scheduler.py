from datetime import datetime, timedelta
import logging

from app.database import SessionLocal
from app.db_models import Token
from app.services.app_scheduler import get_scheduler
from app.services.whatsapp_service import send_template_message

logger = logging.getLogger(__name__)


async def _reminder_job(token_id: str) -> None:
    token_id = str(token_id or "").strip()
    if not token_id:
        logger.warning("[REMINDER] No token_id provided, skipping.")
        return

    db = SessionLocal()
    try:
        token = db.query(Token).filter(Token.id == token_id).first()
        if not token:
            logger.warning(f"[REMINDER] Token {token_id} not found, skipping.")
            return

        # Already confirmed — skip
        confirmation_status = str(token.confirmation_status or "").lower()
        if token.confirmed or confirmation_status == "confirmed":
            logger.info(f"[REMINDER] Token {token_id} already confirmed, skipping.")
            return

        # Already had reminder sent — skip to avoid duplicate messages
        if confirmation_status == "reminder_sent":
            logger.info(f"[REMINDER] Token {token_id} already had reminder sent, skipping.")
            return

        phone = str(token.patient_phone or "").strip()
        patient_name = str(token.patient_name or "Patient").strip()

        if not phone:
            logger.warning(f"[REMINDER] Token {token_id} has no phone number, skipping message.")
        else:
            try:
                await send_template_message(
                    phone=phone,
                    template_name="reminder_for_confirmation",
                    params=[patient_name],
                )
                logger.info(f"[REMINDER] Sent reminder to {phone} for token {token_id}")
            except Exception as e:
                logger.error(f"[REMINDER] Failed to send WhatsApp message for token {token_id}: {e}")
                # Don't return — still update status below

        # Update confirmation status
        token.confirmation_status = "reminder_sent"
        token.updated_at = datetime.utcnow()
        db.commit()
        logger.info(f"[REMINDER] Token {token_id} status updated to reminder_sent")

    except Exception as e:
        logger.error(f"[REMINDER] _reminder_job failed for token {token_id}: {e}")
        db.rollback()
    finally:
        db.close()


async def _final_job(token_id: str) -> None:
    token_id = str(token_id or "").strip()
    if not token_id:
        logger.warning("[FINAL] No token_id provided, skipping.")
        return

    db = SessionLocal()
    try:
        token = db.query(Token).filter(Token.id == token_id).first()
        if not token:
            logger.warning(f"[FINAL] Token {token_id} not found, skipping.")
            return

        # Already confirmed — skip
        confirmation_status = str(token.confirmation_status or "").lower()
        if token.confirmed or confirmation_status == "confirmed":
            logger.info(f"[FINAL] Token {token_id} already confirmed, skipping.")
            return

        # Mark as not confirmed
        token.confirmation_status = "not_confirmed"
        token.updated_at = datetime.utcnow()
        db.commit()
        logger.info(f"[FINAL] Token {token_id} marked as not_confirmed")

    except Exception as e:
        logger.error(f"[FINAL] _final_job failed for token {token_id}: {e}")
        db.rollback()
    finally:
        db.close()


def schedule_confirmation_checks(
    token_id: str,
    first_delay_minutes: int = 15,
    second_delay_minutes: int = 15,
) -> None:
    """Schedule APScheduler jobs for confirmation reminder and final check."""
    token_id = str(token_id or "").strip()
    if not token_id:
        logger.warning("[SCHEDULER] No token_id provided, skipping scheduling.")
        return

    first_delay = max(1, int(first_delay_minutes))   # minimum 1 minute
    second_delay = max(1, int(second_delay_minutes))  # minimum 1 minute

    run_reminder_at = datetime.utcnow() + timedelta(minutes=first_delay)
    run_final_at = run_reminder_at + timedelta(minutes=second_delay)

    sch = get_scheduler()

    if not sch:
        logger.error("[SCHEDULER] Scheduler not available, cannot schedule jobs.")
        return

    # Schedule reminder job
    try:
        sch.add_job(
            _reminder_job,
            trigger="date",
            run_date=run_reminder_at,
            args=[token_id],
            id=f"confirm_reminder:{token_id}",
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True,
            max_instances=1,
        )
        logger.info(f"[SCHEDULER] Reminder job scheduled for token {token_id} at {run_reminder_at}")
    except Exception as e:
        logger.error(f"[SCHEDULER] Failed to schedule reminder job for token {token_id}: {e}")

    # Schedule final job
    try:
        sch.add_job(
            _final_job,
            trigger="date",
            run_date=run_final_at,
            args=[token_id],
            id=f"confirm_final:{token_id}",
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True,
            max_instances=1,
        )
        logger.info(f"[SCHEDULER] Final job scheduled for token {token_id} at {run_final_at}")
    except Exception as e:
        logger.error(f"[SCHEDULER] Failed to schedule final job for token {token_id}: {e}")
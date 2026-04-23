from datetime import datetime, timedelta

from app.database import SessionLocal
from app.db_models import Token
from app.services.app_scheduler import get_scheduler
from app.services.whatsapp_service import send_template_message


async def _reminder_job(token_id: str) -> None:
    token_id = str(token_id or "").strip()
    if not token_id:
        return

    db = SessionLocal()
    try:
        token = db.query(Token).filter(Token.id == token_id).first()
        if not token:
            return

        # Already confirmed — skip
        if token.confirmed or str(token.confirmation_status or "").lower() == "confirmed":
            return

        phone = str(token.patient_phone or "").strip()
        patient_name = str(token.patient_name or "Patient")

        reminder_tpl = "reminder_for_confirmation"
        if phone and reminder_tpl:
            try:
                await send_template_message(
                    phone=phone,
                    template_name=reminder_tpl,
                    params=[patient_name],
                )
            except Exception as e:
                print(f"[ERROR] Failed to send reminder_for_confirmation: {e}")

        # Update confirmation status
        token.confirmation_status = "reminder_sent"
        token.updated_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        print(f"[ERROR] _reminder_job failed: {e}")
        db.rollback()
    finally:
        db.close()


async def _final_job(token_id: str) -> None:
    token_id = str(token_id or "").strip()
    if not token_id:
        return

    db = SessionLocal()
    try:
        token = db.query(Token).filter(Token.id == token_id).first()
        if not token:
            return

        # Already confirmed — skip
        if token.confirmed or str(token.confirmation_status or "").lower() == "confirmed":
            return

        # Mark as not confirmed
        token.confirmation_status = "not_confirmed"
        token.updated_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        print(f"[ERROR] _final_job failed: {e}")
        db.rollback()
    finally:
        db.close()


def schedule_confirmation_checks(token_id: str, first_delay_minutes: int = 15, second_delay_minutes: int = 15) -> None:
    """Schedule APScheduler jobs for confirmation reminder and final check."""
    token_id = str(token_id or "").strip()
    if not token_id:
        return

    first_delay = max(0, int(first_delay_minutes))
    second_delay = max(0, int(second_delay_minutes))

    run_reminder_at = datetime.utcnow() + timedelta(minutes=first_delay)
    run_final_at = run_reminder_at + timedelta(minutes=second_delay)

    sch = get_scheduler()
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
    except Exception:
        pass

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
    except Exception:
        pass

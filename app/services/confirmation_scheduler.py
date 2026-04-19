from datetime import datetime, timedelta

from app.config import COLLECTIONS
from app.database import get_db
from app.services.app_scheduler import get_scheduler
from app.services.whatsapp_service import send_template_message
from app.templates import TEMPLATES


async def _reminder_job(token_id: str) -> None:
    token_id = str(token_id or "").strip()
    if not token_id:
        return

    db = get_db()
    tref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    try:
        snap = tref.get()
        if not getattr(snap, "exists", False):
            return
        token = snap.to_dict() or {}
    except Exception:
        return

    if bool(token.get("confirmed")) or str(token.get("confirmation_status") or "").lower() == "confirmed":
        return

    phone = str(token.get("patient_phone") or "").strip()
    patient_name = str(token.get("patient_name") or "Patient")
    token_number = str(token.get("formatted_token") or token.get("token_number") or "")

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

    try:
        tref.set(
            {
                "confirmation_status": "reminder_sent",
                "reminder_sent_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
            merge=True,
        )
    except Exception:
        pass


async def _final_job(token_id: str) -> None:
    token_id = str(token_id or "").strip()
    if not token_id:
        return

    db = get_db()
    tref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    try:
        snap = tref.get()
        if not getattr(snap, "exists", False):
            return
        token = snap.to_dict() or {}
    except Exception:
        return

    if bool(token.get("confirmed")) or str(token.get("confirmation_status") or "").lower() == "confirmed":
        return

    try:
        tref.set(
            {
                "confirmation_status": "not_confirmed",
                "not_confirmed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
            merge=True,
        )
    except Exception:
        pass


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

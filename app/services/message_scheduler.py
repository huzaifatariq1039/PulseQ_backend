import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, List

from app.templates import TEMPLATES
from app.services.whatsapp_service import send_template_message
from app.database import get_db
from app.config import COLLECTIONS


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


async def schedule_at(run_at: datetime, template_name: str, token_context: Dict[str, Any], params: List[str]) -> None:
    now = datetime.now(timezone.utc)
    run_at_utc = run_at
    try:
        if run_at_utc.tzinfo is None:
            run_at_utc = run_at_utc.replace(tzinfo=timezone.utc)
        else:
            run_at_utc = run_at_utc.astimezone(timezone.utc)
    except Exception:
        run_at_utc = now

    delay = max(0.0, (run_at_utc - now).total_seconds())

    async def _runner():
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            to = str(token_context.get("patient_phone") or "").strip()
            if not to:
                return
            await send_template_message(to, template_name, params)
        except Exception:
            return

    try:
        asyncio.create_task(_runner())
    except Exception:
        await _runner()


async def _build_token_context(token: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    ctx: Dict[str, Any] = dict(token or {})

    patient_id = ctx.get("patient_id")
    if patient_id and not ctx.get("patient_phone"):
        try:
            usnap = db.collection(COLLECTIONS["USERS"]).document(str(patient_id)).get()
            if getattr(usnap, "exists", False):
                u = usnap.to_dict() or {}
                ctx["patient_phone"] = u.get("phone") or u.get("mobile")
                ctx["patient_name"] = ctx.get("patient_name") or u.get("name")
        except Exception:
            pass

    doctor_id = ctx.get("doctor_id")
    if doctor_id and not ctx.get("doctor_name"):
        try:
            dsnap = db.collection(COLLECTIONS["DOCTORS"]).document(str(doctor_id)).get()
            if getattr(dsnap, "exists", False):
                d = dsnap.to_dict() or {}
                ctx["doctor_name"] = d.get("name")
                ctx["department"] = ctx.get("department") or d.get("specialization") or d.get("subcategory") or d.get("department")
        except Exception:
            pass

    hospital_id = ctx.get("hospital_id")
    if hospital_id and not ctx.get("hospital_name"):
        try:
            hsnap = db.collection(COLLECTIONS["HOSPITALS"]).document(str(hospital_id)).get()
            if getattr(hsnap, "exists", False):
                h = hsnap.to_dict() or {}
                ctx["hospital_name"] = h.get("name")
        except Exception:
            pass

    return ctx


async def schedule_messages(token: Dict[str, Any]) -> None:
    ctx = await _build_token_context(token)

    appt = _to_dt(ctx.get("appointment_time")) or _to_dt(ctx.get("appointment_date"))
    if appt is None:
        return

    try:
        if appt.tzinfo is None:
            appt = appt.replace(tzinfo=timezone.utc)
        else:
            appt = appt.astimezone(timezone.utc)
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    diff_minutes = (appt - now).total_seconds() / 60.0

    phone = str(ctx.get("patient_phone") or "").strip()
    if not phone:
        return

    # ALWAYS SEND CONFIRMATION
    try:
        confirm_tpl = TEMPLATES["CONFIRMATION"]
    except Exception:
        confirm_tpl = None

    if confirm_tpl:
        confirm_params = [
            str(ctx.get("doctor_name") or "Doctor"),
            str(ctx.get("patient_name") or "Patient"),
            str(ctx.get("hospital_name") or "Hospital"),
            str(ctx.get("doctor_room_number") or ctx.get("doctor_room") or ""),
            str(ctx.get("estimated_wait_time") or ""),
        ]
        await send_template_message(phone, confirm_tpl, confirm_params)

    # CASE 1: LONG
    if diff_minutes > 60:
        await schedule_at(
            appt - timedelta(minutes=60),
            TEMPLATES.get("QUEUE_UPDATE"),
            ctx,
            [str(ctx.get("patient_name") or "Patient"), str(ctx.get("token_number") or "")],
        )
        await schedule_at(
            appt - timedelta(minutes=30),
            TEMPLATES.get("QUEUE_UPDATE"),
            ctx,
            [str(ctx.get("patient_name") or "Patient"), str(ctx.get("token_number") or "")],
        )
        await schedule_at(
            appt - timedelta(minutes=15),
            TEMPLATES.get("FINAL_CALL"),
            ctx,
            [str(ctx.get("patient_name") or "Patient"), str(ctx.get("token_number") or "")],
        )

    # CASE 2: MEDIUM
    elif 30 < diff_minutes <= 60:
        await schedule_at(
            appt - timedelta(minutes=30),
            TEMPLATES.get("QUEUE_UPDATE"),
            ctx,
            [str(ctx.get("patient_name") or "Patient"), str(ctx.get("token_number") or "")],
        )
        await schedule_at(
            appt - timedelta(minutes=15),
            TEMPLATES.get("FINAL_CALL"),
            ctx,
            [str(ctx.get("patient_name") or "Patient"), str(ctx.get("token_number") or "")],
        )

    # CASE 3: SHORT
    else:
        await schedule_at(
            now + timedelta(minutes=5),
            TEMPLATES.get("QUEUE_UPDATE"),
            ctx,
            [str(ctx.get("patient_name") or "Patient"), str(ctx.get("token_number") or "")],
        )
        await schedule_at(
            appt,
            TEMPLATES.get("FINAL_CALL"),
            ctx,
            [str(ctx.get("patient_name") or "Patient"), str(ctx.get("token_number") or "")],
        )

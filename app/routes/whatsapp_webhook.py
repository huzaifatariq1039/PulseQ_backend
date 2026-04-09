import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from app.db_models import User, Doctor, Hospital, Token
from app.templates import TEMPLATES
from app.services.whatsapp_service import send_template_message

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Webhook"])


@router.get("/webhook")
async def whatsapp_webhook_verify(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    verify = (os.getenv("WHATSAPP_VERIFY_TOKEN") or "").strip()
    if hub_mode == "subscribe" and verify and hub_verify_token == verify:
        return int(hub_challenge or 0)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification failed")


def _extract_text(payload: Dict[str, Any]) -> str:
    try:
        entry = (payload.get("entry") or [])[0] or {}
        changes = (entry.get("changes") or [])[0] or {}
        value = changes.get("value") or {}
        messages = (value.get("messages") or [])
        if not messages:
            return ""
        msg = messages[0] or {}
        # quick reply button
        if msg.get("button") and isinstance(msg.get("button"), dict):
            return str(msg["button"].get("text") or "").strip()
        # regular text
        text = (msg.get("text") or {}).get("body")
        return str(text or "").strip()
    except Exception:
        return ""


def _extract_from(payload: Dict[str, Any]) -> str:
    try:
        entry = (payload.get("entry") or [])[0] or {}
        changes = (entry.get("changes") or [])[0] or {}
        value = changes.get("value") or {}
        messages = (value.get("messages") or [])
        if not messages:
            return ""
        msg = messages[0] or {}
        return str(msg.get("from") or "").strip()
    except Exception:
        return ""


@router.post("/webhook")
async def whatsapp_webhook_receive(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    text = _extract_text(payload)
    wa_from = _extract_from(payload)
    if not wa_from:
        return {"success": True}

    msg = (text or "").strip().lower()
    if msg not in {"yes", "y", "cancel", "c"}:
        return {"success": True}

    # Find latest active token for this phone.
    # WhatsApp webhook uses E.164 digits.
    digits = "".join([c for c in wa_from if c.isdigit()])
    if digits.startswith("92"):
        local_suffix = digits[2:] # 3001234567
    else:
        local_suffix = digits[-10:]

    # Search tokens where patient_phone ends with the digits
    tokens = db.query(Token).filter(
        or_(
            Token.patient_phone.like(f"%{local_suffix}"),
            Token.patient_phone.like(f"%{digits}")
        )
    ).filter(
        ~Token.status.in_(["cancelled", "completed", "rescheduled"])
    ).order_by(Token.created_at.desc()).all()

    candidate = None
    for t in tokens:
        if msg in {"yes", "y"} and bool(getattr(t, "queue_opt_in", False)):
            continue
        candidate = t
        break

    if not candidate:
        return {"success": True}

    token_id = candidate.id
    now = datetime.utcnow()

    # CANCEL flow: mark token cancelled and send cancelled template immediately
    if msg in {"cancel", "c"}:
        candidate.status = "cancelled"
        candidate.cancelled_at = now
        candidate.updated_at = now
        db.commit()

        try:
            tpl = str(TEMPLATES.get("CANCELLED") or "").strip()
            if tpl:
                phone_to = str(candidate.patient_phone or "").strip()
                patient_name = str(candidate.patient_name or "")
                token_number = str(candidate.display_code or candidate.token_number or "")
                params = [p for p in [patient_name, token_number] if p]
                await send_template_message(phone_to or digits, tpl, params)
        except Exception:
            pass

        return {"success": True}

    # YES flow: opt-in token and mark confirmed
    candidate.queue_opt_in = True
    candidate.queue_opted_in_at = now
    candidate.confirmed = True
    candidate.confirmation_status = "confirmed"
    candidate.confirmed_at = now
    candidate.updated_at = now
    db.commit()

    try:
        from app.routes.tokens import _recalculate_token_wait_times
        doctor_id = candidate.doctor_id
        hospital_id = candidate.hospital_id
        appt_dt = candidate.appointment_date
        day_local = appt_dt.date() if appt_dt else now.date()

        # per-patient minutes from doctor config
        doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
        per_min = int(getattr(doctor, "per_patient_minutes", 5) or 5)

        _recalculate_token_wait_times(db, doctor_id, hospital_id, day_local, per_patient_minutes=per_min)
    except Exception:
        pass

    return {"success": True}

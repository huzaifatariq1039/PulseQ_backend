import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.config import COLLECTIONS
from app.database import get_db
from app.templates import TEMPLATES
from app.services.whatsapp_service import send_template_message

# Reuse recalculation helper from tokens route (local import to avoid cycles at startup)

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
async def whatsapp_webhook_receive(request: Request):
    payload = await request.json()
    text = _extract_text(payload)
    wa_from = _extract_from(payload)
    if not wa_from:
        return {"success": True}

    msg = (text or "").strip().lower()
    if msg not in {"yes", "y", "cancel", "c"}:
        return {"success": True}

    db = get_db()

    # Find latest active token for this phone.
    # Tokens store patient_phone in local format; WhatsApp webhook uses E.164 digits.
    # We'll do a best-effort match by digits suffix.
    digits = "".join([c for c in wa_from if c.isdigit()])
    if digits.startswith("92"):
        local = "0" + digits[2:]
    else:
        local = digits

    tokens = list(db.collection(COLLECTIONS["TOKENS"]).limit(5000).stream())
    candidate = None
    for tdoc in tokens:
        t = tdoc.to_dict() or {}
        phone = str(t.get("patient_phone") or "").strip()
        if not phone:
            continue
        pd = "".join([c for c in phone if c.isdigit()])
        if not pd:
            continue
        if pd.endswith(local[-10:]) or local.endswith(pd[-10:]):
            st_raw = t.get("status")
            st = str(getattr(st_raw, "value", st_raw) or "").lower()
            if st in {"cancelled", "completed", "rescheduled"}:
                continue
            # For YES, only consider tokens not yet opted-in.
            if msg in {"yes", "y"} and bool(t.get("queue_opt_in")):
                continue
            # choose most recently created
            created = t.get("created_at")
            try:
                created_dt = created if isinstance(created, datetime) else getattr(created, "to_datetime", lambda: None)()
            except Exception:
                created_dt = None
            if candidate is None:
                candidate = (tdoc, t, created_dt)
            else:
                if created_dt and (candidate[2] is None or created_dt > candidate[2]):
                    candidate = (tdoc, t, created_dt)

    if not candidate:
        return {"success": True}

    tdoc, token, _ = candidate
    token_id = str(token.get("id") or getattr(tdoc, "id", "") or "").strip()
    if not token_id:
        return {"success": True}

    # CANCEL flow: mark token cancelled and send cancelled template immediately
    if msg in {"cancel", "c"}:
        now = datetime.utcnow()
        try:
            db.collection(COLLECTIONS["TOKENS"]).document(token_id).set(
                {
                    "status": "cancelled",
                    "cancelled_at": now,
                    "updated_at": now,
                },
                merge=True,
            )
        except Exception:
            return {"success": True}

        try:
            tpl = str(TEMPLATES.get("CANCELLED") or "").strip()
        except Exception:
            tpl = ""

        if tpl:
            try:
                phone_to = str(token.get("patient_phone") or "").strip()
                patient_name = str(token.get("patient_name") or "")
                token_number = str(token.get("formatted_token") or token.get("token_number") or "")
                params = [p for p in [patient_name, token_number] if p]
                await send_template_message(phone_to or local, tpl, params)
            except Exception:
                pass

        return {"success": True}

    # YES flow: opt-in token and mark confirmed
    now = datetime.utcnow()
    try:
        db.collection(COLLECTIONS["TOKENS"]).document(token_id).set(
            {
                "queue_opt_in": True,
                "queue_opted_in_at": now,
                "confirmed": True,
                "confirmation_status": "confirmed",
                "confirmed_at": now,
                "updated_at": now,
            },
            merge=True,
        )
    except Exception:
        return {"success": True}

    try:
        from app.routes.tokens import _recalculate_token_wait_times
        doctor_id = str(token.get("doctor_id") or "").strip()
        hospital_id = str(token.get("hospital_id") or "").strip()
        appt = token.get("appointment_date")
        appt_dt = appt if isinstance(appt, datetime) else getattr(appt, "to_datetime", lambda: None)()
        day_local = appt_dt.date() if appt_dt else datetime.utcnow().date()

        # per-patient minutes from doctor config if present
        per_min = 5
        try:
            dsnap = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id).get()
            d = dsnap.to_dict() if getattr(dsnap, "exists", False) else {}
            per_min = int(d.get("per_patient_minutes") or 5)
        except Exception:
            per_min = 5

        _recalculate_token_wait_times(db, doctor_id, hospital_id, day_local, per_patient_minutes=per_min)
    except Exception:
        pass

    return {"success": True}

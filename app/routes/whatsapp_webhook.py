import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from twilio.twiml.messaging_response import MessagingResponse
from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.db_models import User, Token
from app.services.whatsapp_service import send_template_message
from app.config import TWILIO_AUTH_TOKEN
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

def _clean_phone(raw: str) -> str:
    return raw.replace("whatsapp:", "").strip()

def _safe_str(value, fallback: str = "") -> str:
    try:
        if value is None:
            return fallback
        return str(value).strip() or fallback
    except Exception:
        return fallback

def _safe_int(value, fallback: int = 0) -> int:
    try:
        if value is None:
            return fallback
        return int(float(str(value)))
    except Exception:
        return fallback


@router.post("/twilio/webhook")
async def twilio_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Twilio WhatsApp Webhook — handles YES / NO replies from patients."""
    signature = request.headers.get("X-Twilio-Signature", "")
    body      = await request.body()

    webhook_url = "https://oyster-app-notep.ondigitalocean.app/api/v1/webhooks/twilio/webhook"
    is_prod      = os.getenv("ENVIRONMENT") == "production"

    if is_prod and signature:
        try:
            from twilio.request_validator import RequestValidator
            from urllib.parse import parse_qs

            validator = RequestValidator(TWILIO_AUTH_TOKEN)
            form_data_raw = {k: v[0] for k, v in parse_qs(body.decode("utf-8")).items()}

            if not validator.validate(webhook_url, form_data_raw, signature):
                logger.warning("Invalid Twilio signature")
                raise HTTPException(status_code=403, detail="Invalid Twilio Signature")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Signature validation error: {e}")

    from urllib.parse import parse_qs

    form_data     = {k: v[0] for k, v in parse_qs(body.decode("utf-8")).items()}
    From          = form_data.get("From", "")
    Body          = form_data.get("Body", "")
    ButtonPayload = form_data.get("ButtonPayload", "")
    ButtonText    = form_data.get("ButtonText", "")

    effective_message = (ButtonPayload or ButtonText or Body).strip().lower()

    user_number  = _clean_phone(From)
    digits       = "".join(c for c in user_number if c.isdigit())
    local_suffix = digits[-10:] if len(digits) >= 10 else digits

    twiml_response = MessagingResponse()

    token = (
        db.query(Token)
        .outerjoin(User, Token.patient_id == User.id)
        .filter(
            or_(
                Token.patient_phone.like(f"%{local_suffix}"),
                Token.patient_phone.like(f"%{digits}"),
                User.phone.like(f"%{local_suffix}"),
                User.phone.like(f"%{digits}"),
            )
        )
        .filter(~Token.status.in_(["cancelled", "completed"]))
        .order_by(Token.created_at.desc())
        .first()
    )

    if not token:
        twiml_response.message("You are not registered in any active queue.")
        return Response(content=str(twiml_response), media_type="application/xml")

    now = datetime.utcnow()

    # ── YES ────────────────────────────────────────────────────────────────────
    if effective_message in ["yes", "y"]:
        token.status              = "confirmed"
        token.confirmed           = True
        token.confirmed_at        = now
        token.updated_at          = now
        token.confirmation_status = "confirmed"
        token.queue_opt_in        = True
        token.queue_opted_in_at   = now
        db.commit()

        try:
            from app.services.app_scheduler import get_scheduler
            sch = get_scheduler()
            if sch:
                for job_id in [f"confirm_reminder:{token.id}", f"confirm_final:{token.id}"]:
                    try:
                        sch.remove_job(job_id)
                    except Exception:
                        pass
        except Exception as e:
            pass

        patient_name  = _safe_str(token.patient_name,  "Patient")
        hospital_name = _safe_str(token.hospital_name, "Clinic")
        token_number  = _safe_str(token.token_number,  "0")
        wait_time     = _safe_int(token.estimated_wait_time, 0)

        # ✅ FIX: Compare by token_number, NOT queue_position, to prevent walk-in crash
        try:
            patients_ahead = (
                db.query(Token)
                .filter(
                    Token.doctor_id        == token.doctor_id,
                    Token.hospital_id      == token.hospital_id,
                    func.date(Token.appointment_date) == func.date(token.appointment_date),
                    Token.token_number     < token.token_number, 
                    Token.status.in_(["waiting", "confirmed", "pending", "in_queue"]),
                )
                .count()
            )

            await send_template_message(
                user_number,
                "queue_update_alert",
                [
                    patient_name,           # {{1}} name
                    str(patients_ahead),    # {{2}} patients ahead
                    str(wait_time),         # {{3}} wait time
                    hospital_name,          # {{4}} hospital name
                    token_number,           # {{5}} token number
                ],
            )
        except Exception as e:
            logger.error(f"queue_update_alert failed for token {token.id}: {e}", exc_info=True)

        try:
            from app.services.message_scheduler import schedule_messages

            token_dict = {k: v for k, v in token.__dict__.items() if not k.startswith("_")}
            token_dict["patient_name"]       = patient_name
            token_dict["hospital_name"]      = hospital_name
            token_dict["token_number"]       = token_number
            token_dict["estimated_wait_time"] = wait_time
            token_dict["patient_phone"]      = user_number

            # ✅ FIX: Pass is_webhook_trigger=True to prevent duplicate spam
            await schedule_messages(token_dict, is_webhook_trigger=True)
            logger.info(f"Follow-up sequence scheduled for token {token.id}")
        except Exception as e:
            logger.error(f"schedule_messages failed for token {token.id}: {e}", exc_info=True)

        return Response(content=str(MessagingResponse()), media_type="application/xml")

    # ── NO / CANCEL ────────────────────────────────────────────────────────────
    elif effective_message in ["no", "n", "cancel"]:
        token.status       = "cancelled"
        token.cancelled_at = now
        token.updated_at   = now
        db.commit()

        try:
            from app.services.queue_management_service import QueueManagementService
            await QueueManagementService.recalculate_positions(
                token.doctor_id, token.hospital_id, token.appointment_date
            )
        except Exception as e:
            pass

        try:
            await send_template_message(
                user_number,
                "cancelled",
                [_safe_str(token.patient_name, "Patient")],
            )
        except Exception as e:
            twiml_response.message("Your appointment has been cancelled. Thank you.")
            return Response(content=str(twiml_response), media_type="application/xml")

        return Response(content=str(MessagingResponse()), media_type="application/xml")

    # ── UNKNOWN ────────────────────────────────────────────────────────────────
    else:
        twiml_response.message("Please reply YES to confirm or NO to cancel.")

    return Response(content=str(twiml_response), media_type="application/xml")
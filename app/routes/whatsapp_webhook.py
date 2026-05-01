import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from twilio.twiml.messaging_response import MessagingResponse
from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.db_models import User, Token
from app.services.whatsapp_service import send_queue_message, send_template_message
from app.config import TWILIO_AUTH_TOKEN
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def _clean_phone(raw: str) -> str:
    """Strip whatsapp: prefix — send_template_message adds it itself."""
    return raw.replace("whatsapp:", "").strip()


def _safe_str(value, fallback: str = "") -> str:
    """Cast any value to string safely — never raises, never returns None."""
    try:
        if value is None:
            return fallback
        return str(value).strip() or fallback
    except Exception:
        return fallback


def _safe_int(value, fallback: int = 0) -> int:
    """Cast any value to int safely — never raises."""
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
    is_prod     = os.getenv("ENVIRONMENT") == "production"

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

    # Log every field Twilio sends — critical for debugging button taps
    logger.info(
        f"Twilio webhook | From={From!r} | Body={Body!r} | "
        f"ButtonPayload={ButtonPayload!r} | ButtonText={ButtonText!r} | "
        f"AllFields={list(form_data.keys())}"
    )

    # ButtonPayload is authoritative for button taps; fall back to ButtonText then Body
    # .strip().lower() means "YES", "yes", " Yes " all become "yes"
    effective_message = (ButtonPayload or ButtonText or Body).strip().lower()

    user_number  = _clean_phone(From)
    digits       = "".join(c for c in user_number if c.isdigit())
    local_suffix = digits[-10:] if len(digits) >= 10 else digits

    logger.info(f"effective_message={effective_message!r} | user_number={user_number!r}")

    twiml_response = MessagingResponse()

    # Fetch the latest active token for this phone number
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
        logger.warning(f"No active token found for {user_number}")
        twiml_response.message("You are not registered in any active queue.")
        return Response(content=str(twiml_response), media_type="application/xml")

    now = datetime.utcnow()

    # ── YES ────────────────────────────────────────────────────────────────────
    if effective_message == "yes":

        # 1. Update token status
        token.status              = "confirmed"
        token.confirmed           = True
        token.confirmed_at        = now
        token.updated_at          = now
        token.confirmation_status = "confirmed"
        token.queue_opt_in        = True
        token.queue_opted_in_at   = now
        db.commit()
        logger.info(f"Token {token.id} confirmed | patient={user_number}")

        # 2. Cancel any pending reminder scheduler jobs
        try:
            from app.services.app_scheduler import get_scheduler
            sch = get_scheduler()
            if sch:
                for job_id in [f"confirm_reminder:{token.id}", f"confirm_final:{token.id}"]:
                    try:
                        sch.remove_job(job_id)
                        logger.info(f"Removed scheduler job: {job_id}")
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Scheduler cleanup error: {e}")

        # 3. Safe-cast every token field we will use — prevents crashes on None/bad types
        patient_name  = _safe_str(token.patient_name,  "Patient")
        hospital_name = _safe_str(token.hospital_name, "Clinic")
        token_number  = _safe_str(token.token_number,  "0")
        wait_time     = _safe_int(token.estimated_wait_time, 0)

        logger.info(
            f"Token fields | patient_name={patient_name!r} | "
            f"hospital_name={hospital_name!r} | token_number={token_number!r} | "
            f"wait_time={wait_time}"
        )

        # 4. Send immediate queue_update_alert — isolated try so step 5 always runs
        try:
            patients_ahead = (
                db.query(Token)
                .filter(
                    Token.doctor_id        == token.doctor_id,
                    Token.hospital_id      == token.hospital_id,
                    Token.appointment_date == token.appointment_date,
                    Token.queue_position   < token.queue_position,
                    Token.status.in_(["waiting", "confirmed"]),
                )
                .count()
            )
            logger.info(f"Patients ahead of token {token.id}: {patients_ahead}")

            await send_template_message(
                user_number,
                "queue_update_alert",
                [
                    patient_name,           # {{1}} name
                    str(patients_ahead),    # {{2}} patients ahead — plain integer string
                    str(wait_time),         # {{3}} wait time    — plain integer string, NO "mins"
                    hospital_name,          # {{4}} hospital name
                    token_number,           # {{5}} token number
                ],
            )
            logger.info(f"queue_update_alert sent to {user_number}")
        except Exception as e:
            # Log the real error but continue — step 5 must still run
            logger.error(f"queue_update_alert failed for token {token.id}: {e}", exc_info=True)

        # 5. Schedule all timed follow-up messages — runs regardless of step 4 outcome
        try:
            from app.services.message_scheduler import schedule_messages

            # Serialise the ORM object to a plain dict for the scheduler
            token_dict = {
                k: v
                for k, v in token.__dict__.items()
                if not k.startswith("_")
            }
            # Override with safe-cast values so the scheduler also never crashes on None
            token_dict["patient_name"]       = patient_name
            token_dict["hospital_name"]      = hospital_name
            token_dict["token_number"]       = token_number
            token_dict["estimated_wait_time"] = wait_time
            token_dict["patient_phone"]      = user_number

            await schedule_messages(token_dict, is_webhook_trigger=True)
            logger.info(f"Follow-up sequence scheduled for token {token.id}")
        except Exception as e:
            logger.error(f"schedule_messages failed for token {token.id}: {e}", exc_info=True)

        # Always return empty TwiML — replies sent via API above, not via TwiML
        return Response(content=str(MessagingResponse()), media_type="application/xml")

    # ── NO / CANCEL ────────────────────────────────────────────────────────────
    elif effective_message in ["no", "n", "cancel"]:
        token.status       = "cancelled"
        token.cancelled_at = now
        token.updated_at   = now
        db.commit()
        logger.info(f"Token {token.id} cancelled by {user_number}")

        try:
            from app.services.queue_management_service import QueueManagementService
            await QueueManagementService.recalculate_positions(
                token.doctor_id, token.hospital_id, token.appointment_date
            )
        except Exception as e:
            logger.warning(f"Queue recalculation failed: {e}")

        try:
            await send_template_message(
                user_number,
                "cancelled",
                [_safe_str(token.patient_name, "Patient")],
            )
        except Exception as e:
            logger.error(f"Cancellation message failed: {e}", exc_info=True)
            twiml_response.message("Your appointment has been cancelled. Thank you.")
            return Response(content=str(twiml_response), media_type="application/xml")

        return Response(content=str(MessagingResponse()), media_type="application/xml")

    # ── UNKNOWN ────────────────────────────────────────────────────────────────
    else:
        logger.warning(f"Unrecognised message {effective_message!r} from {user_number}")
        twiml_response.message("Please reply YES to confirm or NO to cancel.")

    return Response(content=str(twiml_response), media_type="application/xml")
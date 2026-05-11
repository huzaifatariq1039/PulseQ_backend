import os
from datetime import datetime, timezone, date
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
import redis.asyncio as redis
from app.config import REDIS_URL

logger = logging.getLogger(__name__)

router = APIRouter()

# ✅ Global Redis client for message deduplication
_redis_client: Optional[redis.Redis] = None

async def _get_redis_client() -> redis.Redis:
    """Get or create Redis client for message deduplication."""
    global _redis_client
    if _redis_client is None:
        _redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client

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


async def _is_message_already_sent(phone: str, template_name: str) -> bool:
    try:
        redis_client = await _get_redis_client()
        message_key = f"message:{phone}:{template_name}"
        result = await redis_client.get(message_key)
        return result is not None
    except Exception as e:
        logger.error(f"Failed to check message cache: {e}")
        return False


async def _mark_message_sent(phone: str, template_name: str, ttl_seconds: int = 86400) -> None:
    try:
        redis_client = await _get_redis_client()
        message_key = f"message:{phone}:{template_name}"
        await redis_client.setex(message_key, ttl_seconds, "sent")
        logger.info(f"Marked message as sent: {message_key}")
    except Exception as e:
        logger.error(f"Failed to mark message as sent: {e}")


def normalize_phone(phone: str) -> str:
    if not phone:
        return phone
    phone = str(phone).strip().replace(" ", "").replace("-", "")
    if phone.startswith("0") and len(phone) == 11:
        return "+92" + phone[1:]
    if not phone.startswith("+"):
        return "+" + phone
    return phone


@router.post("/twilio/webhook")
async def twilio_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Twilio WhatsApp Webhook — handles YES / NO replies from patients."""

    signature = request.headers.get("X-Twilio-Signature", "")
    body = await request.body()

    # ✅ Build URL from forwarded headers (load balancer aware)
    forwarded_host = request.headers.get("X-Forwarded-Host", "")
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "http")
    if forwarded_host:
        webhook_url = f"{forwarded_proto}://{forwarded_host}/api/v1/webhooks/twilio/webhook"
    else:
        webhook_url = "http://pulseq-api-env.eba-i2evcmmi.ap-south-1.elasticbeanstalk.com/api/v1/webhooks/twilio/webhook"

    logger.info(f"[WEBHOOK] Incoming request, URL: {webhook_url}")

    is_prod = os.getenv("ENVIRONMENT") == "production"

    if is_prod and signature:
        try:
            from twilio.request_validator import RequestValidator
            from urllib.parse import parse_qs

            validator = RequestValidator(TWILIO_AUTH_TOKEN)
            form_data_raw = {k: v[0] for k, v in parse_qs(body.decode("utf-8")).items()}

            if not validator.validate(webhook_url, form_data_raw, signature):
                logger.warning(f"[WEBHOOK] Invalid Twilio signature for URL: {webhook_url}")
                raise HTTPException(status_code=403, detail="Invalid Twilio Signature")

            logger.info(f"[WEBHOOK] Signature validated successfully")

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

    normalized_incoming = normalize_phone(user_number)
    logger.info(f"[WEBHOOK] Received message from: {normalized_incoming}, text: {effective_message}")

    twiml_response = MessagingResponse()
    today = datetime.utcnow().date()

    token = (
        db.query(Token)
        .outerjoin(User, Token.patient_id == User.id)
        .filter(
            or_(
                Token.patient_phone == normalized_incoming,
                Token.patient_phone.like(f"%{local_suffix}"),
                Token.patient_phone.like(f"%{digits}"),
                User.phone.like(f"%{local_suffix}"),
                User.phone.like(f"%{digits}"),
            )
        )
        .filter(Token.status.in_(["pending", "waiting", "confirmed", "in_queue"]))
        .filter(func.date(Token.appointment_date) == today)
        .order_by(Token.created_at.desc())
        .first()
    )

    if not token:
        logger.warning(f"[WEBHOOK] No token found for: {normalized_incoming}")
        twiml_response.message("You are not registered in any active queue.")
        return Response(content=str(twiml_response), media_type="application/xml")

    logger.info(f"[WEBHOOK] Token found: {token.token_number}, status: {token.status}")

    now = datetime.utcnow()

    # ── YES ────────────────────────────────────────────────────────────────────
    if effective_message in ["yes", "y"]:
        logger.info(f"[YES] Processing YES for token: {token.id}")

        token.status              = "confirmed"
        token.confirmed           = True
        token.confirmed_at        = now
        token.updated_at          = now
        token.confirmation_status = "confirmed"
        token.queue_opt_in        = True
        token.queue_opted_in_at   = now
        db.commit()
        logger.info(f"[YES] Token status updated to CONFIRMED: {token.token_number}")

        # Cancel any pending reminder jobs
        try:
            from app.services.app_scheduler import get_scheduler
            sch = get_scheduler()
            if sch:
                for job_id in [f"confirm_reminder:{token.id}", f"confirm_final:{token.id}"]:
                    try:
                        sch.remove_job(job_id)
                    except Exception:
                        pass
        except Exception:
            pass

        patient_name  = _safe_str(token.patient_name,  "Patient")
        hospital_name = _safe_str(token.hospital_name, "Clinic")
        token_display = _safe_str(token.display_code or token.token_number, "0")
        wait_time     = _safe_int(token.estimated_wait_time, 0)

        patients_ahead = 0
        try:
            patients_ahead = (
                db.query(Token)
                .filter(
                    Token.doctor_id   == token.doctor_id,
                    Token.hospital_id == token.hospital_id,
                    func.date(Token.appointment_date) == func.date(token.appointment_date),
                    Token.token_number < token.token_number,
                    Token.status.in_(["waiting", "confirmed", "pending", "in_queue"]),
                )
                .count()
            )
        except Exception as e:
            logger.error(f"[YES] patients_ahead query failed: {e}")

        logger.info(f"[YES] patient_name={patient_name}, patients_ahead={patients_ahead}, wait_time={wait_time}")

        try:
            if await _is_message_already_sent(normalized_incoming, "queue_update_alert"):
                logger.warning(f"[YES] queue_update_alert already sent, skipping")
            else:
                result = await send_template_message(
                    normalized_incoming,
                    "queue_update_alert",
                    [
                        patient_name,
                        str(patients_ahead),
                        str(wait_time),
                        hospital_name,
                        token_display,
                    ],
                )
                logger.info(f"[YES] queue_update_alert sent: sid={result}")
                await _mark_message_sent(normalized_incoming, "queue_update_alert")

        except Exception as e:
            logger.error(f"[YES] Failed to send queue_update_alert: {e}", exc_info=True)

        # ✅ NO ARQ - no schedule_messages call
        return Response(content=str(MessagingResponse()), media_type="application/xml")

    # ── NO / CANCEL ────────────────────────────────────────────────────────────
    elif effective_message in ["no", "n", "cancel"]:
        logger.info(f"[NO] Processing NO for token: {token.id}")

        token.status       = "cancelled"
        token.cancelled_at = now
        token.updated_at   = now
        db.commit()
        logger.info(f"[NO] Token status updated to CANCELLED: {token.token_number}")

        try:
            from app.services.queue_management_service import QueueManagementService
            await QueueManagementService.recalculate_positions(
                token.doctor_id, token.hospital_id, token.appointment_date
            )
        except Exception as e:
            logger.error(f"[NO] Failed to recalculate positions: {e}")

        try:
            if not await _is_message_already_sent(normalized_incoming, "cancelled"):
                await send_template_message(
                    normalized_incoming,
                    "cancelled",
                    [_safe_str(token.patient_name, "Patient")],
                )
                logger.info(f"[NO] Cancellation message sent")
                await _mark_message_sent(normalized_incoming, "cancelled")
        except Exception as e:
            logger.error(f"[NO] Failed to send cancellation message: {e}")
            twiml_response.message("Your appointment has been cancelled. Thank you.")
            return Response(content=str(twiml_response), media_type="application/xml")

        return Response(content=str(MessagingResponse()), media_type="application/xml")

    # ── UNKNOWN ────────────────────────────────────────────────────────────────
    else:
        logger.info(f"[UNKNOWN] Unrecognized message: {effective_message}")
        twiml_response.message("Please reply YES to confirm or NO to cancel.")

    return Response(content=str(twiml_response), media_type="application/xml")


# ✅ CLEANUP
async def close_redis():
    """Close Redis connection on app shutdown."""
    global _redis_client
    if _redis_client:
        try:
            await _redis_client.close()
            _redis_client = None
            logger.info("Webhook Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing webhook Redis: {e}")
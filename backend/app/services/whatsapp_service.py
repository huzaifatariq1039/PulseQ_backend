from twilio.rest import Client
from app.config import (
    TWILIO_ACCOUNT_SID, 
    TWILIO_AUTH_TOKEN, 
    TWILIO_WHATSAPP_NUMBER, 
    TWILIO_TEMPLATE_SID,
    TWILIO_CALL_ALERT_SID,
    TWILIO_FINAL_ALERT_SID,
    TWILIO_DOCTOR_CHANGE_SID,
    TWILIO_CANCELLED_SID,
    TWILIO_THANKYOU_SID,
    TWILIO_SKIPPED_SID,
    TWILIO_REMINDER_CONFIRM_SID,
    TWILIO_QUEUE_UPDATE_SID,
    TWILIO_TOKEN_NUMBER_SID,
    TWILIO_OTP_SID 
)
import logging
import json
import re

logger = logging.getLogger(__name__)

def format_whatsapp_number(phone: str) -> str:
    """
    Normalize a phone number for Twilio WhatsApp delivery.

    Accepts local Pakistani numbers or numbers already starting with 92 or +92,
    strips any leading 0, and always returns a whatsapp:+92XXXXXXXXXX string.
    """
    if not phone:
        return ""

    clean_phone = str(phone).strip()
    if clean_phone.startswith("whatsapp:"):
        clean_phone = clean_phone[len("whatsapp:"):].strip()

    clean_phone = re.sub(r"[^\d+]", "", clean_phone)
    clean_phone = clean_phone.lstrip("+")

    while clean_phone.startswith("0"):
        clean_phone = clean_phone[1:]

    if clean_phone.startswith("92"):
        clean_phone = clean_phone[2:]

    if clean_phone.startswith("0"):
        clean_phone = clean_phone[1:]

    return f"whatsapp:+92{clean_phone}"


def _template_param(params: list, index: int, default: str = "") -> str:
    try:
        if not params or index < 0 or index >= len(params):
            return default

        val = params[index]
        if val is None:
            return default

        s = str(val)
        # Replace newlines, carriage returns, and tabs with a single space
        s = re.sub(r"[\r\n\t]+", " ", s)
        # Collapse multiple spaces and strip leading/trailing whitespace
        s = re.sub(r" +", " ", s).strip()

        return s if s else default
    except Exception:
        return default


def send_queue_message(phone: str, name: str, position: int, wait_time: int, doctor_name: str = "N/A", hospital_name: str = "PulseQ Clinic", room_number: str = "Room 1"):
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured. Skipping WhatsApp message.")
        return

    try:
        formatted_phone = format_whatsapp_number(phone)
        if not formatted_phone:
            return None

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        from_number = format_whatsapp_number(TWILIO_WHATSAPP_NUMBER)

        if TWILIO_TEMPLATE_SID:
            message = client.messages.create(
                from_=from_number,
                to=formatted_phone,
                content_sid=TWILIO_TEMPLATE_SID,
                content_variables=json.dumps({
                    "1": str(doctor_name),
                    "2": str(name),
                    "3": str(hospital_name),
                    "4": str(room_number),
                    "5": str(wait_time)
                })
            )
            return message.sid
        else:
            message_body = f"""Apki appointment book ho chuki h!\n\nDoctor: {doctor_name}\nPatient: {name}\nHospital: {hospital_name}\nRoom Number: {room_number}\nEstimated Time: {wait_time} minutes\n\nReply YES to receive live updates.\n\nPulseQ"""
            return client.messages.create(from_=from_number, to=formatted_phone, body=message_body).sid
            
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message to {phone}: {e}")
        return None


async def send_template_message(phone: str, template_name: str, params: list):
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        return

    try:
        formatted_phone = format_whatsapp_number(phone)
        from_number = format_whatsapp_number(TWILIO_WHATSAPP_NUMBER)
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        # ✅ OTP
        if template_name == "otp_verification":
            if TWILIO_OTP_SID:
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    content_sid=TWILIO_OTP_SID,
                    content_variables=json.dumps({
                        "1": str(params[0]) if params else "000000"
                    })
                )
                return message.sid
            else:
                otp = str(params[0]) if params else "000000"
                body = f"{otp} is your verification code. For your security, do not share this code."
                return client.messages.create(from_=from_number, to=formatted_phone, body=body).sid

        if template_name == "token_number":
            if TWILIO_TOKEN_NUMBER_SID:
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    content_sid=TWILIO_TOKEN_NUMBER_SID,
                    content_variables=json.dumps({
                        "1": _template_param(params, 0, "Doctor"),
                        "2": _template_param(params, 1, "Patient"),
                        "3": _template_param(params, 2, "Hospital"),
                        "4": _template_param(params, 3, "Department")
                    })
                )
                return message.sid
            else:
                body = f"""Apki appointment book ho chuki h!\n\nDoctor: {_template_param(params, 0, 'Doctor')}\nPatient: {_template_param(params, 1, 'Patient')}\nHospital: {_template_param(params, 2, 'Hospital')}\nDepartment: {_template_param(params, 3, 'Department')}\n\nReply YES to receive live updates.\n\nPulseQ"""
                return client.messages.create(from_=from_number, to=formatted_phone, body=body).sid

        if template_name == "patient_call_alert" and TWILIO_CALL_ALERT_SID:
            message = client.messages.create(
                from_=from_number,
                to=formatted_phone,
                content_sid=TWILIO_CALL_ALERT_SID,
                content_variables=json.dumps({"1": str(params[0]) if params else "Patient"})
            )
            return message.sid

        if template_name == "final_alert":
            if TWILIO_FINAL_ALERT_SID:
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    content_sid=TWILIO_FINAL_ALERT_SID,
                    content_variables=json.dumps({
                        "1": str(params[0]) if params else "Patient",
                        "2": str(params[1]) if len(params) > 1 else ""
                    })
                )
                return message.sid
            else:
                body = f"""Hello {params[0]},\n\nAapki turn kisi bhi waqt aa sakti hai. Please hospital ki taraf rawana ho jayein.\n\nAapka token number {params[1]} hai.\n\nPulseQ"""
                return client.messages.create(from_=from_number, to=formatted_phone, body=body).sid

        if template_name == "appointment_doctor_change":
            if TWILIO_DOCTOR_CHANGE_SID:
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    content_sid=TWILIO_DOCTOR_CHANGE_SID,
                    content_variables=json.dumps({
                        "1": str(params[0]) if params else "Patient",
                        "2": str(params[1]) if len(params) > 1 else "",
                        "3": str(params[2]) if len(params) > 2 else "",
                        "4": str(params[3]) if len(params) > 3 else "https://pulseq.blog/"
                    })
                )
                return message.sid

        if template_name == "cancelled":
            if TWILIO_CANCELLED_SID:
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    content_sid=TWILIO_CANCELLED_SID,
                    content_variables=json.dumps({"1": str(params[0]) if params else "Patient"})
                )
                return message.sid
            else:
                body = f"""Hello {params[0]},\n\nAapki appointment cancel ho chuki hai.\n\nPulseQ"""
                return client.messages.create(from_=from_number, to=formatted_phone, body=body).sid

        if template_name == "skipped":
            if TWILIO_SKIPPED_SID:
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    content_sid=TWILIO_SKIPPED_SID,
                    content_variables=json.dumps({
                        "1": str(params[0]) if params else "Patient",
                        "2": str(params[1]) if len(params) > 1 else ""
                    })
                )
                return message.sid

        if template_name == "queue_update_alert":
            if TWILIO_QUEUE_UPDATE_SID:
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    content_sid=TWILIO_QUEUE_UPDATE_SID,
                    content_variables=json.dumps({
                        "1": str(params[0]) if params else "Patient",
                        "2": str(params[1]) if len(params) > 1 else "0",
                        "3": str(params[2]) if len(params) > 2 else "0",
                        "4": str(params[3]) if len(params) > 3 else "Clinic",
                        "5": str(params[4]) if len(params) > 4 else "Token"
                    })
                )
                return message.sid

        logger.warning(f"send_template_message: unknown template_name '{template_name}'")
        return None

    except Exception as e:
        logger.error(f"Failed to send WhatsApp template message to {phone}: {e}")
        return None
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
    TWILIO_TOKEN_NUMBER_SID
)
import logging
import json

logger = logging.getLogger(__name__)

def send_queue_message(phone: str, name: str, position: int, wait_time: int, doctor_name: str = "N/A", hospital_name: str = "PulseQ Clinic", room_number: str = "Room 1"):
    """
    Sends a WhatsApp message using either the official Template SID (for buttons) 
    or a text fallback.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured. Skipping WhatsApp message.")
        return

    try:
        if not phone:
            logger.warning("No phone number provided. Skipping WhatsApp message.")
            return None

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        formatted_phone = str(phone)
        if not formatted_phone.startswith("whatsapp:"):
            if not formatted_phone.startswith("+"):
                formatted_phone = f"+{formatted_phone}"
            formatted_phone = f"whatsapp:{formatted_phone}"

        from_number = TWILIO_WHATSAPP_NUMBER
        if from_number and not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"

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
            logger.info(f"WhatsApp template message (with buttons) sent to {formatted_phone}: SID {message.sid}")
        else:
            message_body = f"""Apki appointment book ho chuki h!\n\nDoctor: {doctor_name}\nPatient: {name}\nHospital: {hospital_name}\nRoom Number: {room_number}\nEstimated Time: {wait_time} minutes\n\nReply YES to receive live updates.\n\nPulseQ"""
            message = client.messages.create(from_=from_number, to=formatted_phone, body=message_body)
            logger.info(f"WhatsApp text message sent (no buttons) to {formatted_phone}: SID {message.sid}")
        
        return message.sid
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message to {phone}: {e}")
        return None

async def send_template_message(phone: str, template_name: str, params: list):
    """
    Sends a WhatsApp template message using Twilio Content API.
    Ensure variables in the Twilio Console are named {{1}}, {{2}}, etc.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured. Skipping template message.")
        return

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        formatted_phone = phone
        if not formatted_phone.startswith("whatsapp:"):
            if not formatted_phone.startswith("+"):
                formatted_phone = f"+{formatted_phone}"
            formatted_phone = f"whatsapp:{formatted_phone}"

        from_number = TWILIO_WHATSAPP_NUMBER
        if from_number and not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"

        if template_name == "token_number":
            if TWILIO_TOKEN_NUMBER_SID:
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    content_sid=TWILIO_TOKEN_NUMBER_SID,
                    content_variables=json.dumps({
                        "1": str(params[0]) if params else "Doctor",
                        "2": str(params[1]) if len(params) > 1 else "Patient",
                        "3": str(params[2]) if len(params) > 2 else "Clinic",
                        "4": str(params[3]) if len(params) > 3 else "General",
                        "5": str(params[4]) if len(params) > 4 else "0"
                    })
                )
                return message.sid
            else:
                body = f"""Apki appointment book ho chuki h!\n\nDoctor: {params[0]}\nPatient: {params[1]}\nHospital: {params[2]}\nDepartment: {params[3]}\nEstimated Time: {params[4]} minutes\n\nReply YES to receive live updates.\n\nPulseQ"""
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
                body = f"""Hello {params[0]},\n\nAapki turn kisi bhi waqt aa sakti hai. Please hospital ki taraf rawana ho jayein.\n\nAapka token number {params[1]} hai.\n\nKindly arrive on time.\n\nPulseQ"""
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
                body = f"""Hello {params[0]},\n\nAapki appointment cancel ho chuki hai.\n\nAgr ap dobara book krna chahte hain to is website ka through book kr skte hain: https://pulseq.blog/\nYa Hospital reception sa rabta karein.\n\nThankyou\n\nPulseQ"""
                return client.messages.create(from_=from_number, to=formatted_phone, body=body).sid

        if template_name == "template":
            if TWILIO_THANKYOU_SID:
                return client.messages.create(from_=from_number, to=formatted_phone, content_sid=TWILIO_THANKYOU_SID).sid
            else:
                body = """Thankyou for visiting PulseQ.\n\nFor future appointments use this link:\nhttps://pulseq.blog/\n\nDid you like our service?\n\n(Reply with one of the options below)\n1. Yes, It was Great\n2. No, I didn't like it"""
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
            else:
                body = f"""Hello {params[0]},\n\nLagta hai ke aap apni scheduled appointment miss kar chuke hain. Aapka token number {params[1]} tha.\n\nKindly jald az jald hospital reception se rabta karein taake aap apni appointment reschedule kar saken ya mazeed madad le saken.\n\nThank you for your attention.\n\nPulseQ"""
                return client.messages.create(from_=from_number, to=formatted_phone, body=body).sid

        if template_name == "reminder_for_confirmation":
            if TWILIO_REMINDER_CONFIRM_SID:
                return client.messages.create(from_=from_number, to=formatted_phone, content_sid=TWILIO_REMINDER_CONFIRM_SID).sid
            else:
                body = """Aapki appointment ke liye koi response receive nahi hua.\n\nReply YES karein updates confirm karne ke liye aur NO karein cancel karne ke liye."""
                return client.messages.create(from_=from_number, to=formatted_phone, body=body).sid

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
            else:
                body = f"""Dear {params[0]},\n\nAapki turn qareeb aa rahi hai. Aap se pehle {params[1]} patients hain. Taqreeban wait {params[2]} hai. Please {params[3]} ki taraf chle jayein.\nToken: {params[4]}\n\nKindly tayar rhein.\n\nPulseQ"""
                return client.messages.create(from_=from_number, to=formatted_phone, body=body).sid

        # Generic fallback
        body = f"Template: {template_name} | Params: {', '.join(map(str, params))}"
        return client.messages.create(from_=from_number, to=formatted_phone, body=body).sid

    except Exception as e:
        logger.error(f"Failed to send WhatsApp template message to {phone}: {e}")
        return None
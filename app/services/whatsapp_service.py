
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
    TWILIO_REMINDER_CONFIRM_SID
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
        
        # Ensure phone is in the correct format for WhatsApp
        formatted_phone = str(phone)
        if not formatted_phone.startswith("whatsapp:"):
            if not formatted_phone.startswith("+"):
                formatted_phone = f"+{formatted_phone}"
            formatted_phone = f"whatsapp:{formatted_phone}"

        # Ensure FROM number is in correct WhatsApp format
        from_number = TWILIO_WHATSAPP_NUMBER
        if from_number and not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"

        # If we have a Template SID, use the Content API to show buttons
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
            # Fallback to plain text if SID is missing
            message_body = f"""
Apki appointment book ho chuki h!

Doctor: {doctor_name}
Patient: {name}
Hospital: {hospital_name}
Room Number: {room_number}
Estimated Time: {wait_time}

Reply YES to receive live updates.

PulseQ
"""
            message = client.messages.create(
                from_=from_number,
                to=formatted_phone,
                body=message_body.strip()
            )
            logger.info(f"WhatsApp text message sent (no buttons) to {formatted_phone}: SID {message.sid}")
        
        return message.sid
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message to {phone}: {e}")
        return None

def send_call_alert(phone: str, name: str):
    """
    Sends the 'patient_call_alert' template message when wait time is low.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_CALL_ALERT_SID:
        logger.warning("Twilio credentials or Call Alert SID not configured.")
        return

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        formatted_phone = str(phone)
        if not formatted_phone.startswith("whatsapp:"):
            if not formatted_phone.startswith("+"):
                formatted_phone = f"+{formatted_phone}"
            formatted_phone = f"whatsapp:{formatted_phone}"

        from_number = TWILIO_WHATSAPP_NUMBER
        if from_number and not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"

        message = client.messages.create(
            from_=from_number,
            to=formatted_phone,
            content_sid=TWILIO_CALL_ALERT_SID,
            content_variables=json.dumps({
                "1": str(name)
            })
        )
        logger.info(f"WhatsApp Call Alert sent to {formatted_phone}: SID {message.sid}")
        return message.sid
    except Exception as e:
        logger.error(f"Failed to send Call Alert to {phone}: {e}")
        return None

async def send_template_message(phone: str, template_name: str, params: list):
    """
    Sends a WhatsApp template message using Twilio.
    Note: Twilio handles templates via their Content API or pre-approved messages.
    For simplicity, this function simulates sending a template by constructing a body.
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

        # Ensure FROM number is in correct WhatsApp format
        from_number = TWILIO_WHATSAPP_NUMBER
        if from_number and not from_number.startswith("whatsapp:"):
            from_number = f"whatsapp:{from_number}"

        # In a real production environment, you would use Twilio's Content SID.
        if template_name == "patient_call_alert" and TWILIO_CALL_ALERT_SID:
            message = client.messages.create(
                from_=from_number,
                to=formatted_phone,
                content_sid=TWILIO_CALL_ALERT_SID,
                content_variables=json.dumps({
                    "1": str(params[0]) if params else "Patient"
                })
            )
            logger.info(f"WhatsApp Call Alert template sent to {formatted_phone}: SID {message.sid}")
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
                logger.info(f"WhatsApp Final Alert template (SID) sent to {formatted_phone}: SID {message.sid}")
                return message.sid
            else:
                # Fallback text as per user requirement image
                name = str(params[0]) if params else "Patient"
                token = str(params[1]) if len(params) > 1 else ""
                body = f"""
Hello {name},

Aapki turn kisi bhi waqt aa sakti hai. Please hospital ki taraf rawana ho jayein.

Aapka token number {token} hai.

Kindly arrive on time.

PulseQ
""".strip()
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    body=body
                )
                logger.info(f"WhatsApp Final Alert text sent (fallback) to {formatted_phone}: SID {message.sid}")
                return message.sid

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
                logger.info(f"WhatsApp Doctor Change template (SID) sent to {formatted_phone}: SID {message.sid}")
                return message.sid
            else:
                # Fallback text as per user requirement image
                name = str(params[0]) if params else "Patient"
                old_doctor = str(params[1]) if len(params) > 1 else ""
                new_doctor = str(params[2]) if len(params) > 2 else ""
                link = str(params[3]) if len(params) > 3 and params[3] else "https://pulseq.blog/"
                
                body = f"""
Hello {name},

Dr.{old_doctor} emergency ki wajah se available nahi hain.

Aapki appointment update kar di gayi hai: Dr.{new_doctor}

Agar aap apni appointment modify karna chahte hain, to neeche diye gaye link ko use karein:
{link}

Agar aap appointment cancel karna chahte hain, to Cancel button par click karein.

Shukriya aapke cooperation ka.
""".strip()
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    body=body
                )
                logger.info(f"WhatsApp Doctor Change text sent (fallback) to {formatted_phone}: SID {message.sid}")
                return message.sid

        if template_name == "cancelled":
            if TWILIO_CANCELLED_SID:
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    content_sid=TWILIO_CANCELLED_SID,
                    content_variables=json.dumps({
                        "1": str(params[0]) if params else "Patient"
                    })
                )
                logger.info(f"WhatsApp Cancelled template (SID) sent to {formatted_phone}: SID {message.sid}")
                return message.sid
            else:
                # Fallback text as per user requirement image
                name = str(params[0]) if params else "Patient"
                body = f"""
Hello {name},

Aapki appointment cancel ho chuki hai.

Agr ap dobara book krna chahte hain to is website ka through book kr skte hain: https://pulseq.blog/
Ya Hospital reception sa rabta karein.

Thankyou

PulseQ
""".strip()
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    body=body
                )
                logger.info(f"WhatsApp Cancelled text sent (fallback) to {formatted_phone}: SID {message.sid}")
                return message.sid

        if template_name == "template": # The internal key for thankyou is "template" in templates.py
            if TWILIO_THANKYOU_SID:
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    content_sid=TWILIO_THANKYOU_SID
                )
                logger.info(f"WhatsApp Thankyou template (SID) sent to {formatted_phone}: SID {message.sid}")
                return message.sid
            else:
                # Fallback text as per user requirement image
                body = """
Thank for visiting PulseQ.

Please share your feedback: https://forms.gle/u1TTULK298ZM6VZ5A
""".strip()
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    body=body
                )
                logger.info(f"WhatsApp Thankyou text sent (fallback) to {formatted_phone}: SID {message.sid}")
                return message.sid

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
                logger.info(f"WhatsApp Skipped template (SID) sent to {formatted_phone}: SID {message.sid}")
                return message.sid
            else:
                # Fallback text as per user requirement image
                name = str(params[0]) if params else "Patient"
                token = str(params[1]) if len(params) > 1 else ""
                body = f"""
Hello {name},

Lagta hai ke aap apni scheduled appointment miss kar chuke hain. Aapka token number {token} tha.

Kindly jald az jald hospital reception se rabta karein taake aap apni appointment reschedule kar saken ya mazeed madad le saken.

Thank you for your attention.

PulseQ
""".strip()
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    body=body
                )
                logger.info(f"WhatsApp Skipped text sent (fallback) to {formatted_phone}: SID {message.sid}")
                return message.sid

        if template_name == "reminder_for_confirmation":
            if TWILIO_REMINDER_CONFIRM_SID:
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    content_sid=TWILIO_REMINDER_CONFIRM_SID
                )
                logger.info(f"WhatsApp Reminder Confirm template (SID) sent to {formatted_phone}: SID {message.sid}")
                return message.sid
            else:
                # Fallback text as per user requirement image
                body = """
Aapki appointment ke liye koi response receive nahi hua.

Reply YES karein updates confirm karne ke liye aur NO karein cancel karne ke liye.
""".strip()
                message = client.messages.create(
                    from_=from_number,
                    to=formatted_phone,
                    body=body
                )
                logger.info(f"WhatsApp Reminder Confirm text sent (fallback) to {formatted_phone}: SID {message.sid}")
                return message.sid

        # Here we construct the body based on the template name and params.
        body = f"Template: {template_name} | Params: {', '.join(map(str, params))}"
        
        message = client.messages.create(
            from_=from_number,
            to=formatted_phone,
            body=body
        )
        logger.info(f"WhatsApp template message sent to {formatted_phone}: SID {message.sid}")
        return message.sid
    except Exception as e:
        logger.error(f"Failed to send WhatsApp template message to {phone}: {e}")
        return None

import asyncio
import httpx
from typing import List, Dict
from datetime import datetime
from app.database import get_db
from app.config import COLLECTIONS
from app.models import NotificationType
import os


class NotificationService:
    """Service for handling WhatsApp and SMS notifications"""

    @staticmethod
    async def send_whatsapp_template(
        phone_number: str,
        template_name: str,
        body_parameters: List[str] | None = None,
        language_code: str = "en_US",
    ) -> Dict:
        """Send a WhatsApp template message using Meta WhatsApp Cloud API.

        Notes:
        - `body_parameters` map to template body variables in-order ({{1}}, {{2}}, ...)
        - If WhatsApp credentials are missing, returns a mock success response.
        """
        token = os.getenv("WHATSAPP_TOKEN")
        phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

        if not template_name:
            return {"success": False, "error": "template_name is required", "phone_number": phone_number}

        # If not configured, fallback to mock
        if not token or not phone_id:
            await asyncio.sleep(0.05)
            return {
                "success": True,
                "message_id": f"whatsapp_{datetime.utcnow().timestamp()}",
                "status": "sent",
                "phone_number": phone_number,
                "mock": True,
                "template": template_name,
                "body_parameters": body_parameters or [],
            }

        url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # WhatsApp Cloud expects E.164 format; do a simple Pakistan normalization if needed
        to = phone_number
        digits = "".join([c for c in to if c.isdigit()])
        if digits.startswith("03") and len(digits) == 11:
            to = f"+92{digits[1:]}"
        elif digits.startswith("923"):
            to = f"+{digits}"

        components: List[Dict] = []
        params = body_parameters or []
        if params:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(p)} for p in params],
                }
            )

        payload: Dict = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        if components:
            payload["template"]["components"] = components

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
                ok = 200 <= resp.status_code < 300
                data = resp.json() if resp.content else {}
                return {
                    "success": ok,
                    "status_code": resp.status_code,
                    "response": data,
                    "phone_number": to,
                    "template": template_name,
                }
            except Exception as e:
                return {"success": False, "error": str(e), "phone_number": to, "template": template_name}
    
    @staticmethod
    async def send_whatsapp_message(phone_number: str, message: str) -> Dict:
        """Send WhatsApp message using Meta WhatsApp Cloud API if configured; otherwise mock."""
        token = os.getenv("WHATSAPP_TOKEN")
        phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        template_name = os.getenv("WHATSAPP_TEMPLATE_NAME")  # optional
        use_template = os.getenv("WHATSAPP_USE_TEMPLATE", "false").lower() == "true"

        # If not configured, fallback to mock
        if not token or not phone_id:
            await asyncio.sleep(0.05)
            return {"success": True, "message_id": f"whatsapp_{datetime.utcnow().timestamp()}", "status": "sent", "phone_number": phone_number, "mock": True}

        url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # WhatsApp Cloud expects E.164 format; do a simple Pakistan normalization if needed
        to = phone_number
        digits = ''.join([c for c in to if c.isdigit()])
        if digits.startswith('03') and len(digits) == 11:
            to = f"+92{digits[1:]}"
        elif digits.startswith('923'):
            to = f"+{digits}"

        payload: Dict
        if use_template and template_name:
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {"name": template_name, "language": {"code": "en_US"}}
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"preview_url": False, "body": message}
            }

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
                ok = 200 <= resp.status_code < 300
                data = resp.json() if resp.content else {}
                return {"success": ok, "status_code": resp.status_code, "response": data, "phone_number": to}
            except Exception as e:
                return {"success": False, "error": str(e), "phone_number": to}
    
    @staticmethod
    async def send_sms_message(phone_number: str, message: str) -> Dict:
        """Send SMS via configured provider. Supported: TWILIO, VONAGE, MESSAGEBIRD. Fallback to mock."""
        provider = (os.getenv("SMS_PROVIDER", "mock") or "mock").strip().lower()

        # Normalize to E.164 (Pakistan convenience)
        to = phone_number
        digits = ''.join([c for c in to if c.isdigit()])
        if digits.startswith('03') and len(digits) == 11:
            to = f"+92{digits[1:]}"
        elif digits.startswith('923'):
            to = f"+{digits}"
        elif not to.startswith('+'):
            to = phone_number

        # Twilio
        if provider in ("twilio", "twilio_sms"):
            sid = os.getenv("TWILIO_ACCOUNT_SID")
            token = os.getenv("TWILIO_AUTH_TOKEN")
            from_number = os.getenv("TWILIO_FROM_NUMBER")
            messaging_service_sid = os.getenv("TWILIO_MESSAGING_SERVICE_SID")
            if sid and token and (from_number or messaging_service_sid):
                url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
                if messaging_service_sid:
                    data = {"MessagingServiceSid": messaging_service_sid, "To": to, "Body": message}
                else:
                    data = {"From": from_number, "To": to, "Body": message}
                async with httpx.AsyncClient(timeout=15, auth=(sid, token)) as client:
                    try:
                        resp = await client.post(url, data=data)
                        ok = 200 <= resp.status_code < 300
                        j = resp.json() if resp.content else {}
                        return {"success": ok, "status_code": resp.status_code, "response": j, "phone_number": to, "provider": "twilio"}
                    except Exception as e:
                        return {"success": False, "error": str(e), "phone_number": to, "provider": "twilio"}

        # Vonage (Nexmo)
        if provider in ("vonage", "nexmo"):
            api_key = os.getenv("VONAGE_API_KEY")
            api_secret = os.getenv("VONAGE_API_SECRET")
            sender = os.getenv("VONAGE_FROM", "SmartToken")
            if api_key and api_secret and sender:
                url = "https://rest.nexmo.com/sms/json"
                payload = {
                    "api_key": api_key,
                    "api_secret": api_secret,
                    "to": to.lstrip('+'),  # Vonage accepts without leading + for many routes
                    "from": sender[:11],    # Max 11 chars for alphanumeric sender
                    "text": message
                }
                async with httpx.AsyncClient(timeout=15) as client:
                    try:
                        resp = await client.post(url, json=payload)
                        ok = 200 <= resp.status_code < 300
                        j = resp.json() if resp.content else {}
                        return {"success": ok, "status_code": resp.status_code, "response": j, "phone_number": to, "provider": "vonage"}
                    except Exception as e:
                        return {"success": False, "error": str(e), "phone_number": to, "provider": "vonage"}

        # MessageBird
        if provider in ("messagebird", "mb"):
            access_key = os.getenv("MESSAGEBIRD_ACCESS_KEY")
            originator = os.getenv("MESSAGEBIRD_ORIGINATOR", "SmartToken")
            if access_key and originator:
                url = "https://rest.messagebird.com/messages"
                headers = {"Authorization": f"AccessKey {access_key}"}
                # API expects form-encoded by default
                data = {
                    "recipients": to,
                    "originator": originator[:11],  # Limit to 11 for alpha sender
                    "body": message
                }
                async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                    try:
                        resp = await client.post(url, data=data)
                        ok = 200 <= resp.status_code < 300
                        j = resp.json() if resp.content else {}
                        return {"success": ok, "status_code": resp.status_code, "response": j, "phone_number": to, "provider": "messagebird"}
                    except Exception as e:
                        return {"success": False, "error": str(e), "phone_number": to, "provider": "messagebird"}

        # Mock fallback
        await asyncio.sleep(0.05)
        return {"success": True, "message_id": f"sms_{datetime.utcnow().timestamp()}", "status": "sent", "phone_number": phone_number, "mock": True, "provider": provider}
    
    @staticmethod
    async def send_token_confirmation_notification(
        token_id: str, 
        phone_number: str, 
        token_number: str,
        doctor_name: str,
        hospital_name: str,
        appointment_time: str,
        notification_types: List[NotificationType]
    ) -> Dict:
        """Send token confirmation notification"""
        
        message = f"""🎫 Token Generated!
Your appointment has been confirmed

Smart Token: {token_number}
Doctor: {doctor_name}
Hospital: {hospital_name}
Time: {appointment_time}

Check your WhatsApp and SMS for token details and updates."""
        
        results = []
        
        for notification_type in notification_types:
            if notification_type == NotificationType.WHATSAPP:
                result = await NotificationService.send_whatsapp_message(phone_number, message)
                results.append({"type": "whatsapp", "result": result})
            
            elif notification_type == NotificationType.SMS:
                result = await NotificationService.send_sms_message(phone_number, message)
                results.append({"type": "sms", "result": result})
        
        return {
            "token_id": token_id,
            "phone_number": phone_number,
            "notifications_sent": results,
            "message": message
        }

    # ---------------- New: Appointment Summary (Twilio-compatible content) ----------------
    @staticmethod
    def build_appointment_summary_message(
        token_label: str,
        doctor_name: str,
        hospital_name: str,
        appointment_time: str,
        people_ahead: int | None = None,
        estimated_wait_time: int | None = None,
        address: str | None = None,
        is_same_day: bool = False
    ) -> str:
        """Build appointment summary message with different content based on whether it's for today or future date.
        
        Args:
            token_label: The token number/label
            doctor_name: Name of the doctor
            hospital_name: Name of the hospital
            appointment_time: Formatted appointment date/time string
            people_ahead: Number of people ahead in queue (only for same-day)
            estimated_wait_time: Estimated wait time in minutes (only for same-day)
            address: Hospital/clinic address (optional)
            is_same_day: Whether the appointment is for today
            
        Returns:
            Formatted message string
        """
        from datetime import datetime, timezone
        
        # Format the appointment date for better readability
        try:
            appt_datetime = datetime.strptime(appointment_time, "%Y-%m-%d %H:%M:%S")
            formatted_date = appt_datetime.strftime("%A, %B %d, %Y at %I:%M %p")
            
            # Check if the appointment is today
            today = datetime.now(timezone.utc).date()
            is_same_day = appt_datetime.date() == today
        except (ValueError, TypeError):
            formatted_date = appointment_time
            is_same_day = False
        
        # Build the message based on whether it's a same-day or future appointment
        if is_same_day:
            # Same-day appointment - include queue information
            message_lines = [
                "📋 Your Appointment is Confirmed",
                "",
                f"🏥 Hospital: {hospital_name}",
                f"👨‍⚕️ Doctor: {doctor_name}",
                f"🎫 Token: {token_label}",
                f"⏰ Time: {formatted_date}",
                "",
                "📊 Your Queue Status:",
                f"👥 People ahead of you: {people_ahead or 0}",
            ]
            
            if estimated_wait_time and estimated_wait_time > 0:
                message_lines.append(f"⏱️ Estimated wait time: ~{estimated_wait_time} minutes")
            else:
                message_lines.append("⏱️ You're next in line!")
                
            if address:
                message_lines.extend(["", f"📍 Location: {address}"])
        else:
            # Future appointment - just confirmation
            message_lines = [
                "✅ Appointment Confirmed",
                "",
                f"🏥 Hospital: {hospital_name}",
                f"👨‍⚕️ Doctor: {doctor_name}",
                f"🎫 Token: {token_label}",
                f"📅 Date & Time: {formatted_date}",
            ]
            
            if address:
                message_lines.extend(["", f"📍 Location: {address}"])
                
            message_lines.extend([
                "",
                "ℹ️ You'll receive a reminder with your queue position and estimated wait time on the day of your appointment."
            ])
        
        message_lines.extend([
            "",
            "Thank you for using SmartToken!"
        ])
        
        return "\n".join(message_lines)
    
    @staticmethod
    async def send_appointment_summary(
        token_label: str,
        phone_number: str,
        doctor_name: str,
        hospital_name: str,
        appointment_time: str,
        people_ahead: int | None,
        estimated_wait_time: int | None,
        notification_types: List[NotificationType],
        address: str | None = None,
    ) -> Dict:
        """Send an appointment summary over selected channels (SMS/WhatsApp)."""
        # Determine if this is a same-day appointment
        from datetime import datetime, timezone
        is_same_day = False
        try:
            # Try to parse the appointment time to check if it's today
            appt_dt = datetime.strptime(appointment_time, "%I:%M %p")
            today = datetime.now(timezone.utc).date()
            is_same_day = True  # If we can parse the time, assume it's for today
        except (ValueError, AttributeError):
            is_same_day = False

        message = NotificationService.build_appointment_summary_message(
            token_label=token_label,
            doctor_name=doctor_name,
            hospital_name=hospital_name,
            appointment_time=appointment_time,
            people_ahead=people_ahead if is_same_day else None,
            estimated_wait_time=estimated_wait_time if is_same_day else None,
            address=address,
            is_same_day=is_same_day
        )
        results = []
        for t in notification_types or []:
            if t == NotificationType.SMS:
                results.append({"type": "sms", "result": await NotificationService.send_sms_message(phone_number, message)})
            elif t == NotificationType.WHATSAPP:
                results.append({"type": "whatsapp", "result": await NotificationService.send_whatsapp_message(phone_number, message)})
        return {"message": message, "results": results}
    
    @staticmethod
    async def send_queue_update_notification(
        token_id: str,
        phone_number: str,
        token_number: str,
        people_ahead: int,
        estimated_wait_time: int,
        notification_types: List[NotificationType]
    ) -> Dict:
        """Send queue position update notification"""
        
        message = f"""📍 Queue Update
Token: {token_number}
People ahead: {people_ahead}
Estimated wait: {estimated_wait_time} minutes

Your turn is coming soon!"""
        
        results = []
        
        for notification_type in notification_types:
            if notification_type == NotificationType.WHATSAPP:
                result = await NotificationService.send_whatsapp_message(phone_number, message)
                results.append({"type": "whatsapp", "result": result})
            
            elif notification_type == NotificationType.SMS:
                result = await NotificationService.send_sms_message(phone_number, message)
                results.append({"type": "sms", "result": result})
        
        return {
            "token_id": token_id,
            "phone_number": phone_number,
            "notifications_sent": results,
            "message": message
        }
    
    @staticmethod
    async def send_appointment_ready_notification(
        token_id: str,
        phone_number: str,
        token_number: str,
        doctor_name: str,
        notification_types: List[NotificationType]
    ) -> Dict:
        """Send notification when it's patient's turn"""
        
        message = f"""🔔 Your Turn!
Token: {token_number}
Doctor: {doctor_name}

Please proceed to the consultation room."""
        
        results = []
        
        for notification_type in notification_types:
            if notification_type == NotificationType.WHATSAPP:
                result = await NotificationService.send_whatsapp_message(phone_number, message)
                results.append({"type": "whatsapp", "result": result})
            
            elif notification_type == NotificationType.SMS:
                result = await NotificationService.send_sms_message(phone_number, message)
                results.append({"type": "sms", "result": result})
        
        return {
            "token_id": token_id,
            "phone_number": phone_number,
            "notifications_sent": results,
            "message": message
        }

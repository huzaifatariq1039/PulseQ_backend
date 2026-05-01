import uuid
import random
import string
from datetime import datetime, timedelta
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import User, OTPVerification
from app.models import ForgotPasswordRequest, VerifyOTPRequest, ResetPasswordRequest
from app.security import get_password_hash
from app.utils.responses import ok
from app.services.whatsapp_service import send_template_message
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Helpers ---

def generate_otp(length: int = 6) -> str:
    """Generate a numeric OTP."""
    return ''.join(random.choices(string.digits, k=length))

def normalize_phone(phone: str) -> str:
    """Normalize phone to international format (Pakistan focus)."""
    phone = str(phone).strip().replace(" ", "").replace("-", "")
    if phone.startswith("0") and len(phone) == 11:
        return "+92" + phone[1:]
    if not phone.startswith("+"):
        return "+" + phone
    return phone

# --- Endpoints ---

@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest, 
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Send OTP to phone number for password reset."""
    phone = normalize_phone(payload.phone)
    
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="No account found with this phone number")
    
    # Invalidate any old unused OTPs
    db.query(OTPVerification).filter(
        OTPVerification.phone == phone, 
        OTPVerification.is_used == False
    ).update({"is_used": True})
    db.commit()
    
    otp = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=2)  # 2 min expiry
    
    otp_record = OTPVerification(
        id=str(uuid.uuid4()),
        phone=phone,
        otp=otp,
        is_used=False,
        expires_at=expires_at,
        created_at=datetime.utcnow()
    )
    db.add(otp_record)
    db.commit()
    
    try:
        await send_template_message(
            phone=phone,
            template_name="otp_verification",
            params=[otp]
        )
        return ok(data={"phone": phone}, message="OTP sent successfully to your WhatsApp")
    except Exception as e:
        logger.error(f"WhatsApp Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to send OTP via WhatsApp")

@router.post("/verify-otp")
async def verify_otp(
    payload: VerifyOTPRequest, 
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Check if OTP is valid without consuming it yet."""
    phone = normalize_phone(payload.phone)
    
    otp_record = db.query(OTPVerification).filter(
        OTPVerification.phone == phone,
        OTPVerification.otp == payload.otp,
        OTPVerification.is_used == False,
        OTPVerification.expires_at > datetime.utcnow()
    ).first()
    
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    # Logic Fix: We do NOT mark is_used=True here so reset-password can still find it.
    return ok(data={"phone": phone, "otp_valid": True}, message="OTP verified successfully")

@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest, 
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Reset password using verified OTP."""
    phone = normalize_phone(payload.phone)
    
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    
    # Final check of the OTP
    otp_record = db.query(OTPVerification).filter(
        OTPVerification.phone == phone,
        OTPVerification.otp == payload.otp,
        OTPVerification.is_used == False,
        OTPVerification.expires_at > datetime.utcnow()
    ).first()
    
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update Security
    user.password_hash = get_password_hash(payload.new_password)
    user.updated_at = datetime.utcnow()
    
    # Mark OTP as consumed
    otp_record.is_used = True
    db.commit()
    
    return ok(data={"phone": phone}, message="Password reset successfully. You can now login.")

@router.post("/resend-otp")
async def resend_otp(
    payload: ForgotPasswordRequest, 
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Resend OTP with 60-second rate limiting."""
    phone = normalize_phone(payload.phone)
    
    recent_otp = db.query(OTPVerification).filter(
        OTPVerification.phone == phone,
        OTPVerification.created_at > datetime.utcnow() - timedelta(seconds=60)
    ).first()
    
    if recent_otp:
        raise HTTPException(status_code=429, detail="Please wait 60 seconds before resending")
    
    return await forgot_password(payload, db)
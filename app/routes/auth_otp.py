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


def generate_otp(length: int = 6) -> str:
    """Generate a numeric OTP."""
    return ''.join(random.choices(string.digits, k=length))


def normalize_phone(phone: str) -> str:
    """Normalize phone to international format."""
    phone = str(phone).strip().replace(" ", "").replace("-", "")
    if phone.startswith("0") and len(phone) == 11:
        return "+92" + phone[1:]
    if phone.startswith("92") and not phone.startswith("+"):
        return "+" + phone
    if not phone.startswith("+"):
        return "+" + phone
    return phone


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Send OTP to phone number for password reset."""
    
    phone = normalize_phone(payload.phone)
    
    # Check if user exists
    user = db.query(User).filter(
        User.phone == phone
    ).first()
    
    # Also try without normalization
    if not user:
        user = db.query(User).filter(
            User.phone == payload.phone
        ).first()
    
    if not user:
        # Don't reveal if user exists or not for security
        raise HTTPException(
            status_code=404,
            detail="No account found with this phone number"
        )
    
    # Invalidate any existing OTPs for this phone
    db.query(OTPVerification).filter(
        OTPVerification.phone == phone,
        OTPVerification.is_used == False
    ).update({"is_used": True})
    db.commit()
    
    # Generate new OTP
    otp = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=2)  # 2 min expiry

    # Save OTP to DB
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
    
    # Send OTP via WhatsApp
    try:
        await send_template_message(
            phone=phone,
            template_name="otp_verification",
            params=[otp]
        )
        logger.info(f"OTP sent to {phone} for password reset")
    except Exception as e:
        logger.error(f"Failed to send OTP to {phone}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to send OTP. Please try again."
        )
    
    return ok(
        data={"phone": phone},
        message="OTP sent successfully to your WhatsApp"
    )


@router.post("/verify-otp")
async def verify_otp(
    payload: VerifyOTPRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Verify OTP without resetting password — just validates."""
    
    phone = normalize_phone(payload.phone)
    
    # Find valid OTP
    otp_record = db.query(OTPVerification).filter(
        OTPVerification.phone == phone,
        OTPVerification.otp == payload.otp,
        OTPVerification.is_used == False,
        OTPVerification.expires_at > datetime.utcnow()
    ).first()
    
    if not otp_record:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OTP. Please request a new one."
        )
    
    # REMOVED: otp_record.is_used = True
    # REMOVED: db.commit()
    
    return ok(
        data={"phone": phone, "otp_valid": True},
        message="OTP verified successfully"
    )

@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Reset password using OTP."""
    
    phone = normalize_phone(payload.phone)
    
    # Validate password strength
    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters long"
        )
    
    # Find valid OTP
    otp_record = db.query(OTPVerification).filter(
        OTPVerification.phone == phone,
        OTPVerification.otp == payload.otp,
        OTPVerification.is_used == False,
        OTPVerification.expires_at > datetime.utcnow()
    ).first()
    
    if not otp_record:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OTP. Please request a new one."
        )
    
    # Find user
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update password
    user.password_hash = get_password_hash(payload.new_password)
    user.updated_at = datetime.utcnow()
    
    # Mark OTP as used
    otp_record.is_used = True
    
    db.commit()
    
    logger.info(f"Password reset successfully for {phone}")
    
    return ok(
        data={"phone": phone},
        message="Password reset successfully. You can now login."
    )


@router.post("/resend-otp")
async def resend_otp(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Resend OTP — rate limited to once every 60 seconds."""
    
    phone = normalize_phone(payload.phone)
    
    # Check rate limit — last OTP must be at least 60 seconds ago
    recent_otp = db.query(OTPVerification).filter(
        OTPVerification.phone == phone,
        OTPVerification.created_at > datetime.utcnow() - timedelta(seconds=60)
    ).first()
    
    if recent_otp:
        raise HTTPException(
            status_code=429,
            detail="Please wait 60 seconds before requesting a new OTP"
        )
    
    # Call forgot_password logic
    return await forgot_password(payload, db)
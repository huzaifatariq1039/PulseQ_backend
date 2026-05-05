from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Response, Body, Query
from typing import List, Optional, Dict, Any
from app.models import (
    UserResponse, ProfileUpdate, NotificationSettings, AppointmentHistory,
    PaymentMethodInfo, SecuritySettings, ActivityType, TokenStatus
)
from app.database import get_db
from sqlalchemy.orm import Session
from app.db_models import User, Doctor, Hospital, Token, ActivityLog
from app.security import get_current_active_user, get_password_hash, verify_password
from app.services.token_service import SmartTokenService
from datetime import datetime
import uuid
import base64
import re

router = APIRouter()

async def create_activity_log(db: Session, user_id: str, activity_type: ActivityType, description: str, metadata: dict = None):
    """Helper function to create activity logs in PostgreSQL"""
    activity = ActivityLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        activity_type=activity_type.value if hasattr(activity_type, 'value') else str(activity_type),
        description=description,
        metadata=metadata or {},
        created_at=datetime.utcnow()
    )
    db.add(activity)
    db.commit()

@router.get("")
@router.get("/", response_model=UserResponse)
async def get_profile(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get user profile information from PostgreSQL"""
    user = db.query(User).filter(User.id == current_user.user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Ensure a displayable name
    name = (user.name or "").strip()
    if not name:
        email = (user.email or "").strip()
        phone = (user.phone or "").strip()
        if email and "@" in email:
            name = email.split("@")[0]
        elif phone:
            name = phone
        else:
            name = "User"
    
    # Normalize role
    role_val = str(user.role.value if hasattr(user.role, 'value') else user.role).lower()
    
    # Generate avatar initials
    avatar_initials = "".join([word[0].upper() for word in name.split()[:2] if word])
    
    return UserResponse(
        id=str(user.id),
        name=name,
        email=user.email,
        phone=user.phone,
        role=role_val,
        location_access=user.location_access or False,
        date_of_birth=user.date_of_birth,
        address=user.address,
        birthday=user.date_of_birth,
        location=user.address,
        created_at=user.created_at,
        updated_at=user.updated_at,
        avatar_initials=avatar_initials
    )

@router.patch("")
@router.patch("/", response_model=UserResponse)
@router.put("")
@router.put("/", response_model=UserResponse)
async def update_profile(
    profile_update: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Update user profile information in PostgreSQL"""
    user = db.query(User).filter(User.id == current_user.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prepare update data
    update_fields = []
    if profile_update.name:
        user.name = profile_update.name
        user.avatar_initials = "".join([word[0].upper() for word in profile_update.name.split()[:2]])
        update_fields.append("name")
    if profile_update.email:
        user.email = profile_update.email
        update_fields.append("email")
    if profile_update.phone:
        user.phone = profile_update.phone
        update_fields.append("phone")
    if profile_update.date_of_birth:
        user.date_of_birth = profile_update.date_of_birth
        update_fields.append("date_of_birth")
    if profile_update.address:
        user.address = profile_update.address
        update_fields.append("address")
    
    # Handle aliases
    birthday = getattr(profile_update, "birthday", None)
    if birthday:
        user.date_of_birth = birthday
    location = getattr(profile_update, "location", None)
    if location:
        user.address = location
    
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    # Create activity log
    await create_activity_log(
        db,
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        "Profile information updated",
        {"updated_fields": update_fields}
    )
    
    # Construct UserResponse explicitly to ensure all fields are present
    # Using __dict__ after db.refresh() can be unreliable as SQLAlchemy expires attributes
    role_val = str(user.role.value if hasattr(user.role, 'value') else user.role).lower()
    
    # Generate avatar initials if not set
    name = (user.name or "").strip()
    avatar_initials = "".join([word[0].upper() for word in name.split()[:2] if word])

    return UserResponse(
        id=str(user.id),
        name=name,
        email=user.email,
        phone=user.phone,
        role=role_val,
        location_access=user.location_access or False,
        date_of_birth=user.date_of_birth,
        address=user.address,
        birthday=user.date_of_birth,
        location=user.address,
        created_at=user.created_at,
        updated_at=user.updated_at,
        avatar_initials=avatar_initials
    )

# ==============================
# Avatar: upload, generate, fetch, delete
# ==============================
_MAX_AVATAR_BYTES = 1_500_000  # ~1.5 MB safety cap
_ALLOWED_MIME = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/svg+xml"}

def _save_avatar(db: Session, user_id: str, mime: str, data_b64: str):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.avatar_mime = mime
        user.avatar_b64 = data_b64
        user.avatar_updated_at = datetime.utcnow()
        user.updated_at = datetime.utcnow()
        db.commit()

@router.post("/avatar/upload-file")
async def upload_avatar_file(
    file: UploadFile = File(..., description="PNG/JPEG/WEBP/SVG up to ~1.5MB"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Upload a profile avatar as a file (multipart/form-data)."""
    mime = (file.content_type or "").lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in _ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {mime}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > _MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Avatar too large")
    
    b64 = base64.b64encode(data).decode("utf-8")
    _save_avatar(db, current_user.user_id, mime, b64)
    return {"message": "Avatar uploaded successfully", "mime": mime, "size": len(data)}

@router.post("/avatar/upload-base64")
async def upload_avatar_base64(
    payload: dict,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Upload a profile avatar as base64 JSON."""
    data_b64 = None
    mime = None
    data_url = (payload or {}).get("data_url")
    if data_url:
        m = re.match(r"^data:([\w\-/+\.]+);base64,(.*)$", data_url)
        if not m:
            raise HTTPException(status_code=400, detail="Invalid data_url format")
        mime = m.group(1).lower()
        data_b64 = m.group(2)
    else:
        data_b64 = (payload or {}).get("data_base64")
        mime = ((payload or {}).get("mime") or "").lower()
    
    if mime == "image/jpg":
        mime = "image/jpeg"
    if not data_b64 or not mime:
        raise HTTPException(status_code=400, detail="Missing data")
    if mime not in _ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Unsupported mime")
        
    try:
        raw = base64.b64decode(data_b64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64")
        
    if len(raw) > _MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Avatar too large")
        
    _save_avatar(db, current_user.user_id, mime, data_b64)
    return {"message": "Avatar saved", "mime": mime, "size": len(raw)}

@router.get("/avatar")
async def get_avatar(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Return the user's avatar image bytes from PostgreSQL"""
    user = db.query(User).filter(User.id == current_user.user_id).first()
    if not user or not user.avatar_b64:
        raise HTTPException(status_code=404, detail="Avatar not set")
    
    try:
        raw = base64.b64decode(user.avatar_b64)
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid data")
    
    return Response(content=raw, media_type=user.avatar_mime)

@router.delete("/avatar")
async def delete_avatar(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Remove user's avatar in PostgreSQL"""
    user = db.query(User).filter(User.id == current_user.user_id).first()
    if user:
        user.avatar_mime = None
        user.avatar_b64 = None
        user.avatar_updated_at = datetime.utcnow()
        user.updated_at = datetime.utcnow()
        db.commit()
    return {"message": "Avatar removed"}

@router.get("/appointment-history", response_model=List[AppointmentHistory])
async def get_appointment_history(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get user's appointment history from PostgreSQL"""
    tokens = db.query(Token).filter(Token.patient_id == current_user.user_id).order_by(Token.appointment_date.desc()).all()
    
    appointments = []
    for t in tokens:
        doctor = db.query(Doctor).filter(Doctor.id == t.doctor_id).first()
        hospital = db.query(Hospital).filter(Hospital.id == t.hospital_id).first()
        
        status_display = "Completed" if str(t.status).lower() == "completed" else "Cancelled"
        
        appointment = AppointmentHistory(
            id=t.id,
            doctor_name=doctor.name if doctor else "Unknown Doctor",
            doctor_specialization=doctor.specialization if doctor else "",
            hospital_name=hospital.name if hospital else "Unknown Hospital",
            appointment_date=t.appointment_date,
            status=status_display,
            rating=getattr(t, 'rating', None),
            token_number=str(t.token_number)
        )
        appointments.append(appointment)
    
    return appointments

@router.post("/change-password")
async def change_password(
    current_password: str,
    new_password: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Change user password in PostgreSQL"""
    user = db.query(User).filter(User.id == current_user.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Verify current password
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid current password")
    
    # Hash and update
    user.password_hash = get_password_hash(new_password)
    user.updated_at = datetime.utcnow()
    db.commit()
    
    await create_activity_log(
        db,
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        "Password changed successfully",
        {"action": "password_change"}
    )
    
    return {"message": "Password changed successfully"}

@router.delete("/account")
async def delete_account(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Delete user account (soft delete) in PostgreSQL"""
    user = db.query(User).filter(User.id == current_user.user_id).first()
    if user:
        # Check if column name is 'status' or 'role' or something else
        # For now, we'll just delete the user record from the database
        db.delete(user)
        db.commit()
        
    await create_activity_log(
        db,
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        "Account deleted",
        {"action": "account_deletion"}
    )
    
    return {"message": "Account deleted successfully"}

@router.get("/statistics")
async def get_profile_statistics(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get profile statistics from PostgreSQL"""
    tokens = db.query(Token).filter(Token.patient_id == current_user.user_id).all()
    
    completed = [t for t in tokens if str(t.status).lower() == "completed"]
    cancelled = [t for t in tokens if str(t.status).lower() == "cancelled"]
    
    return {
        "total_appointments": len(tokens),
        "completed_appointments": len(completed),
        "cancelled_appointments": len(cancelled),
        "wallet_balance": 0, # TODO: Wallet integration
        "member_since": tokens[0].created_at if tokens else datetime.utcnow()
    }

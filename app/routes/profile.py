from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Response, Body, Query
from typing import List, Optional, Dict, Any
from app.models import (
    UserResponse, ProfileUpdate, NotificationSettings, AppointmentHistory,
    PaymentMethodInfo, SecuritySettings, ActivityType, TokenStatus
)
from app.database import get_db
from app.config import COLLECTIONS
from app.security import get_current_active_user, get_password_hash
from app.services.token_service import SmartTokenService
from datetime import datetime
from app.routes.dashboard import invalidate_dashboard_cache_for_user

router = APIRouter(prefix="/profile", tags=["Profile"])

async def create_activity_log(user_id: str, activity_type: ActivityType, description: str, metadata: dict = None):
    """Helper function to create activity logs"""
    db = get_db()
    activities_ref = db.collection("activities")
    
    activity_ref = activities_ref.document()
    activity_data = {
        "id": activity_ref.id,
        "user_id": user_id,
        "activity_type": activity_type,
        "description": description,
        "metadata": metadata or {},
        "created_at": datetime.utcnow()
    }
    
    activity_ref.set(activity_data)

@router.get("/", response_model=UserResponse)
async def get_profile(current_user = Depends(get_current_active_user)):
    """Get user profile information"""
    db = get_db()
    user_ref = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user_data = user_doc.to_dict()
    user_data.pop("password", None)  # Remove password from response
    
    # Ensure a displayable name
    name = (user_data.get("name") or "").strip()
    if not name:
        email = (user_data.get("email") or "").strip()
        phone = (user_data.get("phone") or "").strip()
        if email and "@" in email:
            name = email.split("@")[0]
        elif phone:
            name = phone
        else:
            name = "User"
        user_data["name"] = name

    # Generate avatar initials if not set (after name resolution)
    if not user_data.get("avatar_initials"):
        user_data["avatar_initials"] = "".join([word[0].upper() for word in name.split()[:2] if word])
    
    # Populate alias fields for frontend compatibility
    if user_data.get("date_of_birth") and not user_data.get("birthday"):
        user_data["birthday"] = user_data.get("date_of_birth")
    if user_data.get("address") and not user_data.get("location"):
        user_data["location"] = user_data.get("address")

    return UserResponse(**user_data)

@router.put("/", response_model=UserResponse)
async def update_profile(
    profile_update: ProfileUpdate,
    current_user = Depends(get_current_active_user)
):
    """Update user profile information"""
    db = get_db()
    user_ref = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id)
    
    # Prepare update data
    update_data = {}
    if profile_update.name:
        update_data["name"] = profile_update.name
        # Update avatar initials
        update_data["avatar_initials"] = "".join([word[0].upper() for word in profile_update.name.split()[:2]])
    if profile_update.email:
        update_data["email"] = profile_update.email
    if profile_update.phone:
        update_data["phone"] = profile_update.phone
    if profile_update.date_of_birth:
        update_data["date_of_birth"] = profile_update.date_of_birth
    if profile_update.address:
        update_data["address"] = profile_update.address
    # Accept alternate field names
    if getattr(profile_update, "birthday", None):
        update_data["date_of_birth"] = profile_update.birthday
    if getattr(profile_update, "location", None):
        update_data["address"] = profile_update.location
    
    update_data["updated_at"] = datetime.utcnow()
    
    user_ref.update(update_data)
    
    # If phone was updated, also sync it into notification_preferences.phone_number
    if profile_update.phone:
        prefs_ref = db.collection("notification_preferences")
        prefs_query = prefs_ref.where("user_id", "==", current_user.user_id).limit(1)
        prefs_docs = list(prefs_query.stream())
        if prefs_docs:
            prefs_doc_id = prefs_docs[0].id
            prefs_ref.document(prefs_doc_id).update({
                "phone_number": profile_update.phone,
                "updated_at": datetime.utcnow()
            })
        else:
            # Create a minimal prefs doc if missing so notifications can use phone number
            pref_doc = prefs_ref.document(f"pref_{current_user.user_id}")
            pref_doc.set({
                "id": pref_doc.id,
                "user_id": current_user.user_id,
                "phone_number": profile_update.phone,
                "whatsapp_enabled": True,
                "sms_enabled": True,
                "settings": {
                    "queue_updates": True,
                    "appointment_reminders": True,
                    "emergency_alerts": True
                },
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            })
    
    # Create activity log
    await create_activity_log(
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        "Profile information updated",
        {"updated_fields": list(update_data.keys())}
    )
    # Invalidate dashboard caches for this user to reflect latest profile info
    try:
        invalidate_dashboard_cache_for_user(current_user.user_id)
    except Exception:
        pass
    
    # Get updated user data
    updated_user = user_ref.get().to_dict()
    updated_user.pop("password", None)
    # Populate alias fields for frontend compatibility
    if updated_user.get("date_of_birth") and not updated_user.get("birthday"):
        updated_user["birthday"] = updated_user.get("date_of_birth")
    if updated_user.get("address") and not updated_user.get("location"):
        updated_user["location"] = updated_user.get("address")
    
    return UserResponse(**updated_user)

# ==============================
# Avatar: upload, generate, fetch, delete
# ==============================
_MAX_AVATAR_BYTES = 1_500_000  # ~1.5 MB safety cap
_ALLOWED_MIME = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/svg+xml"}

def _save_avatar(user_id: str, mime: str, data_b64: str):
    db = get_db()
    user_ref = db.collection(COLLECTIONS["USERS"]).document(user_id)
    user_ref.update({
        "avatar_mime": mime,
        "avatar_b64": data_b64,
        "avatar_updated_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })

@router.post("/avatar/upload-file")
async def upload_avatar_file(
    file: UploadFile = File(..., description="PNG/JPEG/WEBP/SVG up to ~1.5MB"),
    current_user = Depends(get_current_active_user)
):
    """Upload a profile avatar as a file (multipart/form-data).

    Stores the image inline as base64 in the user's document for simplicity (no external object storage required).
    """
    mime = (file.content_type or "").lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in _ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {mime}")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > _MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Avatar too large. Please upload an image under 1.5MB.")
    import base64
    b64 = base64.b64encode(data).decode("utf-8")
    _save_avatar(current_user.user_id, mime, b64)
    # Invalidate dashboard cache where avatar might appear
    try:
        invalidate_dashboard_cache_for_user(current_user.user_id)
    except Exception:
        pass
    return {"message": "Avatar uploaded successfully", "mime": mime, "size": len(data)}

@router.post("/avatar/upload-base64")
async def upload_avatar_base64(
    payload: dict,
    current_user = Depends(get_current_active_user)
):
    """Upload a profile avatar as base64 JSON.

    Accepts either {"data_base64": "...", "mime": "image/png"} or a data URL {"data_url": "data:image/png;base64,..."}.
    """
    import base64, re
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
        raise HTTPException(status_code=400, detail="Missing base64 data or mime")
    if mime not in _ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {mime}")
    try:
        raw = base64.b64decode(data_b64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")
    if len(raw) > _MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="Avatar too large. Please upload an image under 1.5MB.")
    _save_avatar(current_user.user_id, mime, data_b64)
    try:
        invalidate_dashboard_cache_for_user(current_user.user_id)
    except Exception:
        pass
    return {"message": "Avatar saved", "mime": mime, "size": len(raw)}

@router.post("/avatar/generate")
async def generate_avatar(
    initials: Optional[str] = None,
    bg: Optional[str] = None,
    fg: Optional[str] = None,
    current_user = Depends(get_current_active_user)
):
    """Generate a simple SVG avatar with initials server-side and store it.

    Parameters: initials (defaults to user initials), bg (hex like #5B8DEF), fg (hex like #FFFFFF)
    """
    db = get_db()
    user_ref = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id)
    user_doc = user_ref.get()
    user = user_doc.to_dict() if getattr(user_doc, "exists", False) else {}
    name = (user.get("name") or "User").strip()
    if not initials:
        initials = "".join([w[0].upper() for w in name.split()[:2] if w]) or "U"
    bg = bg or "#5B8DEF"
    fg = fg or "#FFFFFF"
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' width='256' height='256'>
      <rect width='100%' height='100%' rx='32' ry='32' fill='{bg}'/>
      <text x='50%' y='55%' font-size='120' font-family='Arial, Helvetica, sans-serif' fill='{fg}' text-anchor='middle' dominant-baseline='middle'>{initials}</text>
    </svg>
    """.strip()
    import base64
    data_b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    _save_avatar(current_user.user_id, "image/svg+xml", data_b64)
    try:
        invalidate_dashboard_cache_for_user(current_user.user_id)
    except Exception:
        pass
    return {"message": "New avatar applied", "initials": initials}

@router.get("/avatar")
async def get_avatar(current_user = Depends(get_current_active_user)):
    """Return the user's avatar image bytes with the correct Content-Type.

    If no avatar is set, returns 404 (front-end can fall back to initials avatar).
    """
    db = get_db()
    user_ref = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id)
    doc = user_ref.get()
    if not getattr(doc, "exists", False):
        raise HTTPException(status_code=404, detail="User not found")
    data = doc.to_dict() or {}
    mime = data.get("avatar_mime")
    b64 = data.get("avatar_b64")
    if not mime or not b64:
        raise HTTPException(status_code=404, detail="Avatar not set")
    import base64
    try:
        raw = base64.b64decode(b64)
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid avatar data")
    return Response(content=raw, media_type=mime)

@router.delete("/avatar")
async def delete_avatar(current_user = Depends(get_current_active_user)):
    """Remove user's avatar (revert to initials)."""
    db = get_db()
    user_ref = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id)
    try:
        user_ref.update({
            "avatar_mime": None,
            "avatar_b64": None,
            "avatar_updated_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
    except Exception:
        pass
    try:
        invalidate_dashboard_cache_for_user(current_user.user_id)
    except Exception:
        pass
    return {"message": "Avatar removed"}

@router.get("/notification-preferences")
async def get_notification_preferences(current_user = Depends(get_current_active_user)):
    """Get user notification preferences"""
    db = get_db()
    prefs_ref = db.collection("notification_preferences")
    
    query = prefs_ref.where("user_id", "==", current_user.user_id).limit(1)
    docs = list(query.stream())
    
    if docs:
        prefs_data = docs[0].to_dict()
        return prefs_data.get("settings", NotificationSettings().dict())
    else:
        # Return default settings
        return NotificationSettings().dict()

@router.put("/notification-preferences")
async def update_notification_preferences(
    settings: NotificationSettings,
    current_user = Depends(get_current_active_user)
):
    """Update user notification preferences"""
    db = get_db()
    prefs_ref = db.collection("notification_preferences")
    
    # Check if preferences exist
    query = prefs_ref.where("user_id", "==", current_user.user_id).limit(1)
    docs = list(query.stream())
    
    if docs:
        # Update existing preferences
        pref_doc_ref = prefs_ref.document(docs[0].id)
        pref_doc_ref.update({
            "settings": settings.dict(),
            "updated_at": datetime.utcnow()
        })
    else:
        # Create new preferences
        pref_ref = prefs_ref.document()
        pref_data = {
            "id": pref_ref.id,
            "user_id": current_user.user_id,
            "settings": settings.dict(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        pref_ref.set(pref_data)
    
    # Create activity log
    await create_activity_log(
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        "Notification preferences updated",
        {"settings": settings.dict()}
    )
    # Invalidate dashboard caches to refresh any tiles depending on notifications
    try:
        invalidate_dashboard_cache_for_user(current_user.user_id)
    except Exception:
        pass
    
    return {"message": "Notification preferences updated successfully"}

@router.get("/appointment-history", response_model=List[AppointmentHistory])
async def get_appointment_history(current_user = Depends(get_current_active_user)):
    """Get user's appointment history"""
    db = get_db()
    tokens_ref = db.collection(COLLECTIONS["TOKENS"])
    
    # Get all user tokens - use simple query to avoid composite index requirement
    query = tokens_ref.where("patient_id", "==", current_user.user_id)
    
    appointments = []
    token_docs = []
    
    # Get all documents first
    for doc in query.stream():
        token_data = doc.to_dict()
        token_data["doc_id"] = doc.id
        token_docs.append(token_data)
    
    # Sort in memory by appointment_date descending
    token_docs.sort(key=lambda x: x.get("appointment_date", datetime.min), reverse=True)
    
    for token_data in token_docs:
        # Get doctor info
        doctor_ref = db.collection(COLLECTIONS["DOCTORS"]).document(token_data["doctor_id"])
        doctor_data = doctor_ref.get().to_dict()
        
        # Get hospital info
        hospital_ref = db.collection(COLLECTIONS["HOSPITALS"]).document(token_data["hospital_id"])
        hospital_data = hospital_ref.get().to_dict()
        
        # Determine status display
        status_display = "Completed" if token_data.get("status") == TokenStatus.COMPLETED else "Cancelled"
        
        appointment = AppointmentHistory(
            id=token_data["doc_id"],
            doctor_name=doctor_data.get("name", "Unknown Doctor"),
            doctor_specialization=doctor_data.get("specialization", ""),
            hospital_name=hospital_data.get("name", "Unknown Hospital"),
            appointment_date=token_data["appointment_date"],
            status=status_display,
            rating=token_data.get("rating"),
            token_number=SmartTokenService.format_token(token_data["token_number"])
        )
        appointments.append(appointment)
    
    return appointments

@router.post("/appointment-history/{appointment_id}/rating")
async def rate_appointment(
    appointment_id: str,
    rating: Optional[int] = Query(None),
    payload: Optional[Dict[str, Any]] = Body(None),
    current_user = Depends(get_current_active_user)
):
    """Rate a completed appointment"""
    rating_val = rating
    if rating_val is None:
        try:
            rating_val = int((payload or {}).get("rating"))
        except Exception:
            rating_val = None
    if rating_val is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rating is required"
        )

    if int(rating_val) < 1 or int(rating_val) > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rating must be between 1 and 5"
        )
    
    db = get_db()
    token_ref = db.collection(COLLECTIONS["TOKENS"]).document(appointment_id)
    token_doc = token_ref.get()
    
    if not token_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    token_data = token_doc.to_dict()
    
    # Check if user owns this appointment
    if token_data.get("patient_id") != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # Only allow rating for completed consultations
    raw_status = token_data.get("status")
    status_val = str(getattr(raw_status, "value", raw_status) or "").strip().lower()
    if status_val != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only completed consultations can be rated"
        )
    
    review_text = None
    if payload:
        review_text = payload.get("review_text")
        if review_text is None:
            review_text = payload.get("feedback")
        if review_text is None:
            review_text = payload.get("comment")

    update = {
        "rating": int(rating_val),
        "rated_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    if isinstance(review_text, str):
        txt = review_text.strip()
        if txt:
            update["review_text"] = txt

    token_ref.update(update)
    out = {"message": "Rating submitted successfully", "rating": int(rating_val)}
    if update.get("review_text") is not None:
        out["review_text"] = update.get("review_text")
    return out

@router.get("/payment-methods", response_model=List[PaymentMethodInfo])
async def get_payment_methods(current_user = Depends(get_current_active_user)):
    """Get user's saved payment methods"""
    db = get_db()
    payment_methods_ref = db.collection("payment_methods")
    
    query = payment_methods_ref.where("user_id", "==", current_user.user_id)
    docs = query.stream()
    
    methods = []
    for doc in docs:
        method_data = doc.to_dict()
        methods.append(PaymentMethodInfo(**method_data))
    
    # Add wallet if exists
    wallets_ref = db.collection("wallets")
    wallet_query = wallets_ref.where("user_id", "==", current_user.user_id).limit(1)
    wallet_docs = list(wallet_query.stream())
    
    if wallet_docs:
        wallet_data = wallet_docs[0].to_dict()
        wallet_method = PaymentMethodInfo(
            id=wallet_data["id"],
            user_id=current_user.user_id,
            method_type="wallet",
            display_name=f"SmartToken Wallet (Rs. {wallet_data.get('balance', 0)})",
            is_default=False,
            created_at=wallet_data["created_at"]
        )
        methods.append(wallet_method)
    
    return methods

@router.get("/security-settings")
async def get_security_settings(current_user = Depends(get_current_active_user)):
    """Get user security settings"""
    db = get_db()
    security_ref = db.collection("security_settings")
    
    query = security_ref.where("user_id", "==", current_user.user_id).limit(1)
    docs = list(query.stream())
    
    if docs:
        security_data = docs[0].to_dict()
        return SecuritySettings(**security_data)
    else:
        # Return default settings
        return SecuritySettings().dict()

@router.put("/security-settings")
async def update_security_settings(
    settings: SecuritySettings,
    current_user = Depends(get_current_active_user)
):
    """Update user security settings"""
    db = get_db()
    security_ref = db.collection("security_settings")
    
    # Check if settings exist
    query = security_ref.where("user_id", "==", current_user.user_id).limit(1)
    docs = list(query.stream())
    
    if docs:
        # Update existing settings
        security_doc_ref = security_ref.document(docs[0].id)
        security_doc_ref.update({
            **settings.dict(),
            "updated_at": datetime.utcnow()
        })
    else:
        # Create new settings
        security_doc_ref = security_ref.document()
        security_data = {
            "id": security_doc_ref.id,
            "user_id": current_user.user_id,
            **settings.dict(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        security_doc_ref.set(security_data)
    
    # Invalidate dashboard caches as a safety to refresh any security-related UI
    try:
        invalidate_dashboard_cache_for_user(current_user.user_id)
    except Exception:
        pass
    return {"message": "Security settings updated successfully"}

@router.post("/change-password")
async def change_password(
    current_password: str,
    new_password: str,
    current_user = Depends(get_current_active_user)
):
    """Change user password"""
    db = get_db()
    user_ref = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user_data = user_doc.to_dict()
    
    # Verify current password (you'll need to implement verify_password)
    # For now, we'll skip verification in development
    
    # Hash new password
    hashed_password = get_password_hash(new_password)
    
    # Update password
    user_ref.update({
        "password": hashed_password,
        "password_last_changed": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })
    
    # Create activity log
    await create_activity_log(
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        "Password changed successfully",
        {"action": "password_change"}
    )
    # Invalidate dashboard caches to reflect security change
    try:
        invalidate_dashboard_cache_for_user(current_user.user_id)
    except Exception:
        pass
    
    return {"message": "Password changed successfully"}

@router.delete("/account")
async def delete_account(current_user = Depends(get_current_active_user)):
    """Delete user account (soft delete)"""
    db = get_db()
    user_ref = db.collection(COLLECTIONS["USERS"]).document(current_user.user_id)
    
    # Soft delete by marking as deleted
    user_ref.update({
        "is_deleted": True,
        "deleted_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })
    
    # Create activity log
    await create_activity_log(
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        "Account deleted",
        {"action": "account_deletion"}
    )
    # Invalidate caches as the account is deleted
    try:
        invalidate_dashboard_cache_for_user(current_user.user_id)
    except Exception:
        pass
    
    return {"message": "Account deleted successfully"}

@router.get("/statistics")
async def get_profile_statistics(current_user = Depends(get_current_active_user)):
    """Get profile statistics for display"""
    db = get_db()
    
    # Get appointment counts
    tokens_ref = db.collection(COLLECTIONS["TOKENS"])
    user_tokens = list(tokens_ref.where("patient_id", "==", current_user.user_id).stream())
    
    completed_count = len([t for t in user_tokens if t.to_dict().get("status") == TokenStatus.COMPLETED])
    cancelled_count = len([t for t in user_tokens if t.to_dict().get("status") == TokenStatus.CANCELLED])
    total_appointments = len(user_tokens)
    
    # Get wallet balance
    wallets_ref = db.collection("wallets")
    wallet_query = wallets_ref.where("user_id", "==", current_user.user_id).limit(1)
    wallet_docs = list(wallet_query.stream())
    wallet_balance = wallet_docs[0].to_dict().get("balance", 0) if wallet_docs else 0
    
    return {
        "total_appointments": total_appointments,
        "completed_appointments": completed_count,
        "cancelled_appointments": cancelled_count,
        "wallet_balance": wallet_balance,
        "member_since": user_tokens[0].to_dict().get("created_at") if user_tokens else datetime.utcnow()
    }

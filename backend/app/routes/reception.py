from datetime import datetime, timedelta, timezone, time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db_models import User, Doctor, Hospital, Token, ActivityLog, Queue as DBQueue
from app.models import TokenData, ReceptionistCreate, ReceptionistResponse
from app.security import get_current_active_user, require_roles, get_password_hash
from app.database import get_db
from app.services.token_service import SmartTokenService
from app.utils.responses import ok
from app.utils.mrn import get_or_create_patient_mrn
from app.utils.date_utils import to_dt
import uuid
import logging

# --- AI Engine Imports ---
from app.services.ai_engine import ai_engine
from app.services.queue_management_service import (
    get_current_hour, get_current_day, calculate_queue_velocity, get_last_patient_duration,
    avg_last_5, avg_last_10, count_available_doctors, get_hour_history,
    get_weekday_history, get_doctor_history
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/receptionists", response_model=ReceptionistResponse, dependencies=[Depends(require_roles("admin"))])
async def create_receptionist(
    receptionist: ReceptionistCreate,
    db: Session = Depends(get_db)
):
    """Create a new receptionist user (Admin only).
    
    This creates a User record with the 'receptionist' role.
    """
    # 1. Check if user with this email already exists
    existing_user = db.query(User).filter(func.lower(User.email) == receptionist.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email {receptionist.email} already exists"
        )
    
    # 2. Check if hospital exists
    hospital = db.query(Hospital).filter(Hospital.id == receptionist.hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hospital not found"
        )

    # 3. Create User record for credentials
    user_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    new_user = User(
        id=user_id,
        name=receptionist.name,
        email=receptionist.email.lower(),
        phone=receptionist.phone,
        password_hash=get_password_hash(receptionist.password),
        role="receptionist",
        hospital_id=receptionist.hospital_id,
        created_at=now,
        updated_at=now
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Map to response
    return ReceptionistResponse(
        id=new_user.id,
        name=new_user.name,
        email=new_user.email,
        phone=new_user.phone,
        hospital_id=new_user.hospital_id,
        role=new_user.role,
        created_at=new_user.created_at,
        updated_at=new_user.updated_at
    )


# Use centralized helper from app.utils.date_utils


def _infer_has_session(dept_text: str) -> bool:
    dt = (dept_text or "").lower()
    return any(kw in dt for kw in ("psychology", "psychiatry", "physiotherapist", "physiotherapy", "physio"))


@router.get("/queue", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def reception_queue(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    hospital_id: str = Query(..., description="Hospital id managed by receptionist"),
    doctor_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """Receptionist Queue View from PostgreSQL"""
    today = datetime.utcnow().date()
    query = db.query(Token).filter(
        Token.hospital_id == hospital_id, 
        func.date(Token.appointment_date) == today,
        # ✅ FIX: Explicitly added "skipped" and "TokenStatus.SKIPPED" so they remain on the receptionist board
        Token.status.in_(["pending", "in_progress", "waiting", "skipped", "TokenStatus.SKIPPED"])  
    )
    if doctor_id:
        query = query.filter(Token.doctor_id == doctor_id)

    total = query.count()
    tokens = query.order_by(Token.token_number.asc()).offset((page-1)*page_size).limit(page_size).all()

    items: List[Dict[str, Any]] = []
    for t in tokens:
        doctor = db.query(Doctor).filter(Doctor.id == t.doctor_id).first()

        #  Read age from Token first (as int)
        age = None
        if t.patient_age is not None:
            try:
                age = int(t.patient_age)
            except Exception:
                age = None

        # Read gender from Token first
        gender = t.patient_gender if t.patient_gender else None

        # Fallback to User table only if token has no age or gender
        if age is None or gender is None:
            user = db.query(User).filter(User.id == t.patient_id).first()
            if user:
                if age is None and user.date_of_birth:
                   try:
                       dob = datetime.strptime(user.date_of_birth, "%Y-%m-%d")
                       age = (datetime.utcnow() - dob).days // 365  # ✅ int
                   except Exception:
                       age = None
                if gender is None: 
                    gender = getattr(user, 'gender', None)

        department = getattr(t, 'doctor_specialization', None) or (doctor.specialization if doctor else "")
        dept_text = f"{department or ''}"
        inferred_has_session = _infer_has_session(dept_text)

        consultation_fee = getattr(t, 'consultation_fee', None) or (doctor.consultation_fee if doctor else 0.0)
        session_fee = getattr(t, 'session_fee', None) or (getattr(doctor, 'session_fee', None) if doctor else 0.0)

        total_fee = getattr(t, 'total_fee', None)
        if total_fee is None:
            total_fee = (consultation_fee or 0) + (session_fee or 0 if inferred_has_session else 0)

        items.append({
           "token_id": t.id,
           "token_number": t.display_code or str(t.token_number),
           "mrn": t.mrn,
           "patient_name": t.patient_name,
           "patient_age": age,             # ✅ int or None
           "patient_gender": gender,       # ✅ from token or user
           "patient_phone": t.patient_phone,
           "doctor_name": t.doctor_name,
           "department": department,
           "reason": getattr(t, 'reason_for_visit', None) or "",
           "consultation_fee": consultation_fee,
           "session_fee": session_fee if inferred_has_session else None,
           "total_fee": total_fee,
           "status": t.status,
           "payment": "PAID" if t.payment_status == "paid" else "UNPAID",
           "payment_method": t.payment_method,
    })

    return ok(
        data=items,
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get("/tokens", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def reception_tokens(
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
    hospital_id: str = Query(...),
    doctor_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """Receptionist view of slot bookings from PostgreSQL"""
    query = db.query(Token).filter(Token.hospital_id == hospital_id)
    if doctor_id:
        query = query.filter(Token.doctor_id == doctor_id)

    total = query.count()
    tokens = query.order_by(Token.appointment_date.desc()).offset((page-1)*page_size).limit(page_size).all()

    items: List[Dict[str, Any]] = []
    for t in tokens:
        items.append({
            "token_id": t.id,
            "doctor_id": t.doctor_id,
            "doctor_name": t.doctor_name,
            "patient_name": t.patient_name,
            "appointment_date": t.appointment_date.isoformat() if t.appointment_date else None,
            "status": str(t.status).lower(),
            "payment_status": str(t.payment_status).lower() if t.payment_status else "pending",  # ✅ add this
            "payment_method": str(t.payment_method).lower() if t.payment_method else None,   
        })

    return ok(data=items, meta={"page": page, "page_size": page_size, "total": total})


# --------------------------------------------------------------------------------
# NEW: UNIFIED AI WALK-IN TOKEN ENDPOINT WITH WHATSAPP MESSAGING
# --------------------------------------------------------------------------------
@router.post("/walkin-token", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def receptionist_create_walkin_token(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Creates a Walk-in token from the receptionist portal. 
    Uses the exact same XGBoost AI Wait-Time engine and WhatsApp logic as the Patient App.
    """
    hospital_id = payload.get("hospital_id")
    doctor_id = payload.get("doctor_id")
    patient_name = payload.get("patient_name")
    phone = payload.get("phone")
    age = payload.get("age")
    gender = payload.get("gender")
    reason = payload.get("reason")
    
    if not all([hospital_id, doctor_id, patient_name, phone]):
        raise HTTPException(status_code=400, detail="Missing required fields: hospital, doctor, name, phone")

    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
    
    # 1. Calculate precise UTC bounds for today to match Patient Portal exactly
    tz_doc = doctor_data.get("tz_offset_minutes", 300)
    tz = timezone(timedelta(minutes=tz_doc))
    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    now_local = now_utc.astimezone(tz)
    day_local = now_local.date()
    
    local_start = datetime.combine(day_local, time.min).replace(tzinfo=tz)
    local_end = datetime.combine(day_local, time.max).replace(tzinfo=tz)
    utc_start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    utc_end = local_end.astimezone(timezone.utc).replace(tzinfo=None)

    # 2. Find or Create User
    dob_str = None
    patient_age_int = 30 # Default for AI if missing
    if age:
        try:
            patient_age_int = int(age)
            dob_str = (datetime.utcnow() - timedelta(days=patient_age_int*365)).strftime("%Y-%m-%d")
        except Exception:
            pass

    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        user = User(
            id=str(uuid.uuid4()),
            name=patient_name,
            phone=phone,
            role="patient",
            password_hash="", 
            date_of_birth=dob_str,
            gender=gender
        )
        db.add(user)
    else:
        if dob_str and not user.date_of_birth:
            user.date_of_birth = dob_str
        if gender and not user.gender:
            user.gender = gender
        if patient_name and user.name != patient_name:
            user.name = patient_name
            
        if user.date_of_birth and not age:
            try:
                dob = datetime.strptime(user.date_of_birth, "%Y-%m-%d")
                patient_age_int = (datetime.utcnow() - dob).days // 365
            except Exception:
                pass

    db.commit()
    db.refresh(user)

    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    hospital_name_str = hospital.name if hospital else "Unknown Hospital"
    mrn = get_or_create_patient_mrn(db, user.id, hospital_id)

    doc_fee = float(doctor.consultation_fee or 0)
    token_fee = 50.0
    total_fee = doc_fee + token_fee

    last_token = db.query(Token).filter(
        Token.hospital_id == hospital_id,
        Token.doctor_id == doctor_id,
        Token.appointment_date >= utc_start,
        Token.appointment_date <= utc_end
    ).order_by(Token.token_number.desc()).first()
    
    next_num = (last_token.token_number + 1) if last_token else 1
    token_id = str(uuid.uuid4())
    
    doc_initial = doctor.name.strip()[0].upper() if doctor.name else "T"
    if doctor.name and doctor.name.lower().startswith("dr"):
        clean_name = doctor.name[2:].replace(".", "").strip()
        doc_initial = clean_name[0].upper() if clean_name else "D"
        
    display_code = f"{doc_initial}-{next_num:03d}"
    
    # ---------------------------------------------------------
    # 🚀 UNIFIED AI ESTIMATED WAIT TIME CALCULATION
    # ---------------------------------------------------------
    estimated_wait_time = 0
    BLOCKING_STATUSES = ["waiting", "confirmed", "pending", "called", "in_consultation", "in_progress", "TokenStatus.PENDING", "TokenStatus.WAITING", "TokenStatus.CONFIRMED"]

    try:
        patients_ahead = db.query(Token).filter(
            Token.doctor_id == doctor_id,
            Token.status.in_(BLOCKING_STATUSES),
            Token.appointment_date >= utc_start,
            Token.appointment_date <= utc_end
        ).count()

        completed_today = db.query(Token).filter(
            Token.doctor_id == doctor_id,
            func.lower(Token.status) == "completed",
            Token.appointment_date >= utc_start,
            Token.appointment_date <= utc_end
        ).count()

        if completed_today == 0:
            estimated_wait_time = (patients_ahead + 1) * 5
        else:
            if patients_ahead == 0:
                estimated_wait_time = 0 
            else:
                if not ai_engine.model:
                    ai_engine.load()

                last_5 = avg_last_5(doctor_id, db) or 5.0
                last_10 = avg_last_10(doctor_id, db) or 5.0 
                last_1 = get_last_patient_duration(doctor_id, db) or 5.0

                ai_input: Dict[str, Any] = {
                    "hour_of_day": get_current_hour(),
                    "day_of_week": get_current_day(),
                    "patients_ahead_of_user": patients_ahead,
                    "patients_in_queue": patients_ahead + 1,
                    "queue_length_last_10_min": 0, 
                    "queue_velocity": calculate_queue_velocity(doctor_id, db),
                    "last_patient_duration": last_1,
                    "avg_service_time_last_5": last_5,
                    "avg_service_time_last_10": last_10,
                    "doctors_available": count_available_doctors(db),
                    "doctor_type": "Specialist" if doctor_data.get("has_session") else "General Medicine",
                    "clinic_type": "Specialist" if doctor_data.get("has_session") else "General Medicine",
                    "avg_wait_time_this_hour_past_week": get_hour_history(db),
                    "avg_wait_time_this_weekday_past_month": get_weekday_history(db),
                    "avg_service_time_doctor_historic": get_doctor_history(doctor_id, db),
                    "Name": patient_name,
                    "Doctor Name": doctor_data.get("name", "Unknown"),
                    "Service_Duration": 0, 
                    "Disease": reason or doctor_data.get("specialization") or "General",
                    "Age": patient_age_int
                }

                predicted_duration = ai_engine.predict_duration(ai_input)
                predicted_duration = max(predicted_duration, 3.5) 

                rolling_service_time = (0.5 * last_5) + (0.3 * last_10) + (0.2 * last_1)
                ai_eta = patients_ahead * predicted_duration

                if completed_today >= 30:
                    alpha = 0.7   
                elif completed_today >= 10:
                    alpha = 0.5   
                else:
                    alpha = 0.2   

                eta = alpha * ai_eta + (1 - alpha) * (patients_ahead * rolling_service_time)
                estimated_wait_time = max(int(eta), 5) 

    except Exception as e:
        logger.error(f"AI Wait Time Calculation failed for walk-in: {e}", exc_info=True)
        # Safe Fallback
        try:
            last_5 = avg_last_5(doctor_id, db) or 5.0
            estimated_wait_time = int(max(patients_ahead, 1) * last_5)
        except Exception:
            estimated_wait_time = max(0, patients_ahead * 15)

    # ---------------------------------------------------------

    new_token = Token(
        id=token_id,
        patient_id=user.id,
        doctor_id=doctor_id,
        hospital_id=hospital_id,
        mrn=mrn,
        token_number=next_num,
        display_code=display_code,
        hex_code=token_id[:8],
        appointment_date=datetime.utcnow(),
        status="pending",
        patient_name=patient_name,
        patient_phone=phone,
        patient_age=patient_age_int,
        patient_gender=gender,
        doctor_name=doctor.name,
        doctor_specialization=doctor.specialization,
        department=doctor.specialization,
        reason_for_visit=reason,
        hospital_name=hospital_name_str,
        consultation_fee=doc_fee,
        total_fee=total_fee,
        estimated_wait_time=estimated_wait_time
    )
    
    db.add(new_token)
    db.commit()

    # ---------------------------------------------------------
    # 🚀 WHATSAPP MESSAGING & SCHEDULING (Mirrored from Patient App)
    # ---------------------------------------------------------
    def normalize_phone(phone_num: str) -> str:
        if not phone_num:
            return phone_num
        phone_num = str(phone_num).strip().replace(" ", "").replace("-", "")
        if phone_num.startswith("0") and len(phone_num) == 11:
            return "+92" + phone_num[1:]  # 03325293408 → +923325293408
        if not phone_num.startswith("+"):
            return "+" + phone_num
        return phone_num

    if phone:
        normalized_phone = normalize_phone(phone)
        logger.info(f"DEBUG: Raw phone={phone}, Normalized={normalized_phone}")  # ✅ add
        # 1. Send the initial Token template
        try:
            from app.services.whatsapp_service import send_template_message
            await send_template_message(
                phone=normalized_phone,
                template_name="token_number",
                params=[
                    doctor.name or "Doctor",
                    patient_name or "Patient",
                    hospital_name_str or "Clinic",
                    doctor.specialization or "General", 
                    str(estimated_wait_time or 0)
                ]
            )
            logger.info(f"WhatsApp walk-in confirmation sent to {normalized_phone} for token {token_id}")
        except Exception as e:
            logger.error(f"Failed to send WhatsApp walk-in confirmation for token {token_id}: {e}")
    
        # 2. Schedule the confirmation reminders
        try:
            from app.services.confirmation_scheduler import schedule_confirmation_checks
            await schedule_confirmation_checks(
                token_id=token_id,
                first_delay_minutes=15,
                second_delay_minutes=15
            )
            logger.info(f"Confirmation reminder scheduled for walk-in token {token_id}")
        except Exception as e:
            logger.error(f"Failed to schedule confirmation reminder for walk-in token {token_id}: {e}")
    # ---------------------------------------------------------
    
    return ok(
        data={
            "token_id": token_id,
            "token_number": display_code,
            "hospital_name": hospital_name_str,
            "department": reason,
            "doctor_name": doctor.name,
            "patient_name": patient_name,
            "phone": phone,
            "mrn": mrn,
            "age": age,
            "gender": gender,
            "payment": "UNPAID",
            "status": "PENDING",
            "consultation_fee": doc_fee,
            "token_fee": token_fee,
            "total_fee": total_fee,
            "estimated_wait_time": estimated_wait_time
        }, 
        message="Walk-in token created via AI Engine"
    )

@router.post("/receptionist/tokens/{token_id}/skip", dependencies=[Depends(require_roles("receptionist", "patient", "admin"))])
async def receptionist_skip_token(
    token_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
        
    token.status = "skipped"
    token.updated_at = datetime.utcnow()
    token.skipped_at = datetime.utcnow()
    db.commit()

    try:
        from app.services.message_scheduler import schedule_skip_messages
        await schedule_skip_messages(token_id)
        logger.info(f"Skip message scheduler triggered for token {token_id}")
    except Exception as e:
        logger.error(f"Failed to schedule skip messages for token {token_id}: {e}")
    
    return ok(message="Token skipped")


@router.post("/doctor/tokens/{token_id}/skip", dependencies=[Depends(require_roles("doctor", "admin"))])
async def doctor_skip_token(
    token_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    doctor_profile = db.query(Doctor).filter(Doctor.user_id == current.user_id).first()
    doctor_profile_id = doctor_profile.id if doctor_profile else None
    
    if str(current.user_id) != str(token.doctor_id) and str(doctor_profile_id) != str(token.doctor_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only skip your own tokens"
        )
    
    st = str(token.status).lower()
    if st in ["completed", "cancelled", "skipped"]:
        raise HTTPException(
            status_code=400,
            detail=f"Token cannot be skipped. Current status: {st}"
        )
    
    now = datetime.utcnow()
    token.status = "skipped"
    token.skipped_at = now
    token.updated_at = now
    
    db.commit()
    
    try:
        from app.services.message_scheduler import schedule_skip_messages
        await schedule_skip_messages(token_id)
        logger.info(f"Skip message scheduler triggered for token {token_id}")
    except Exception as e:
        logger.error(f"Failed to schedule skip messages for token {token_id}: {e}")
    
    today = now.date()
    next_token_obj = db.query(Token).filter(
        Token.doctor_id == token.doctor_id,
        Token.status.in_(["pending", "waiting", "confirmed"]),
        func.date(Token.appointment_date) == today,
        Token.token_number > token.token_number
    ).order_by(Token.token_number.asc()).first()
    
    next_token_data = None
    if next_token_obj:
        next_token_obj.status = "called"
        next_token_obj.called_at = now
        next_token_obj.updated_at = now
        
        db.commit()
        next_token_data = {k: v for k, v in next_token_obj.__dict__.items() if not k.startswith('_')}
    
    return ok(
        data={
            "token_id": token_id,
            "status": "skipped",
            "next_called_token": next_token_data
        },
        message="Token skipped successfully"
    )


@router.patch("/receptionist/tokens/{token_id}", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def receptionist_update_token(
    token_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    if str(token.status).lower() in ["cancelled", "completed"]:
        raise HTTPException(status_code=400, detail=f"Cannot edit token with status: {token.status}")
    
    if "status" in payload:
        new_status = str(payload["status"]).strip().lower()
        valid_statuses = ["pending", "waiting", "confirmed", "called", "skipped", "completed", "cancelled"]
        
        if new_status not in valid_statuses:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
        
        if str(token.status).lower() == "skipped" and new_status in ["waiting", "confirmed", "pending"]:
            token.status = new_status
            token.updated_at = datetime.utcnow()
            db.commit()
            return ok(
                data={
                    "token_id": token.id,
                    "display_code": token.display_code,
                    "patient_name": token.patient_name,
                    "status": token.status,
                    "previous_status": "skipped"
                },
                message=f"Token re-added successfully with status: {new_status}"
            )
        
        token.status = new_status
        token.updated_at = datetime.utcnow()
        db.commit()
        
        return ok(
            data={"token_id": token.id, "status": token.status},
            message="Token status updated successfully"
        )
    
    updatable_fields = [
        "patient_name", "patient_phone", "patient_gender",
        "reason_for_visit", "appointment_date", "department"
    ]
    
    if "reason" in payload and "reason_for_visit" not in payload:
        payload["reason_for_visit"] = payload["reason"]
    updated_fields = []
    for field in updatable_fields:
        if field in payload:
            setattr(token, field, payload[field])
            updated_fields.append(field)
    
    if "patient_age" in payload:
        try:
            age_str = str(payload["patient_age"]).strip()
            if age_str.endswith('y'):
                age_str = age_str[:-1]
            age = int(age_str)
            token.patient_age = age
            if "patient_age" not in updated_fields:
                updated_fields.append("patient_age")
        except (ValueError, TypeError):
            pass
    
    token.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(token)

    user = db.query(User).filter(User.id == token.patient_id).first()
    if user:
        if "patient_name" in updated_fields:
            user.name = token.patient_name
        if "patient_phone" in updated_fields:
            user.phone = token.patient_phone
        user.updated_at = datetime.utcnow()
        db.commit()
    
    return ok(
        data={
            "token_id": token.id,
            "display_code": token.display_code,
            "patient_name": token.patient_name,
            "patient_age": token.patient_age,
            "patient_gender": token.patient_gender,
            "patient_phone": token.patient_phone,
            "status": token.status,
            "updated_fields": updated_fields
        },
        message="Token updated successfully"
    )


@router.delete("/receptionist/tokens/{token_id}", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def receptionist_delete_token(
    token_id: str,
    db: Session = Depends(get_db),
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    if str(token.status).lower() == "completed":
        raise HTTPException(status_code=400, detail="Cannot delete completed token")
    
    if str(token.status).lower() == "cancelled":
        return ok(message="Token is already cancelled")
    
    token.status = "cancelled"
    token.cancelled_at = datetime.utcnow()
    token.updated_at = datetime.utcnow()
    db.commit()
    
    return ok(
        data={
            "token_id": token.id,
            "display_code": token.display_code,
            "status": "cancelled",
            "cancelled_at": token.cancelled_at
        },
        message="Token cancelled/deleted successfully"
    )
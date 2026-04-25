from fastapi import APIRouter, HTTPException, status, Query, Depends
from typing import List, Optional, Dict, Any
from app.models import DoctorCreate, DoctorResponse, DoctorSearchResponse, DoctorWithQueue, QueueStatus
from app.database import get_db, get_db_session
from sqlalchemy.orm import Session
from app.db_models import Doctor, Hospital, User, Queue as DBQueue, Department, Token, Refund
from app.security import get_current_active_user, require_roles
from app.utils.responses import ok
from datetime import datetime, timezone
import random
import logging
from app.services.cache_service import CacheService, cached

router = APIRouter(tags=["Doctors"])
logger = logging.getLogger("performance.doctors")


def _is_doctor_available_today(doctor: Doctor) -> bool:
    """Check if doctor is available RIGHT NOW based on day, time, and status"""
    try:
        # Check status
        status_val = str(doctor.status or "").lower()
        if status_val in {"offline", "on_leave"}:
            return False
        
        # Check if doctor has schedule
        if not doctor.start_time or not doctor.end_time:
            return False
        
        # Check if today is in available_days (if specified)
        if doctor.available_days:
            now_utc = datetime.now(timezone.utc)
            today_name = now_utc.strftime("%A").lower()  # e.g., "monday"
            available_days_lower = [str(d).strip().lower() for d in doctor.available_days]
            
            if available_days_lower and today_name not in available_days_lower:
                return False
        
        # Check current time vs working hours
        now_utc = datetime.now(timezone.utc)
        current_time_str = now_utc.strftime("%H:%M")  # e.g., "14:30"
        
        # Parse doctor's start and end times
        def parse_time(time_str: str) -> Optional[str]:
            """Parse time string to HH:MM format"""
            if not time_str:
                return None
            s = str(time_str).strip().lower()
            
            # Handle AM/PM format
            if 'am' in s or 'pm' in s:
                import re
                m = re.match(r"(\d{1,2}):(\d{2})\s*([ap]m)", s)
                if m:
                    h = int(m.group(1))
                    mm = int(m.group(2))
                    mer = m.group(3)
                    if mer == 'pm' and h != 12:
                        h += 12
                    elif mer == 'am' and h == 12:
                        h = 0
                    return f"{h:02d}:{mm:02d}"
            
            # Handle 24-hour format
            if ':' in s:
                parts = s.split(':')
                if len(parts) == 2:
                    h = int(parts[0])
                    mm = int(parts[1])
                    if 0 <= h <= 23 and 0 <= mm <= 59:
                        return f"{h:02d}:{mm:02d}"
            
            return None
        
        start_time = parse_time(doctor.start_time)
        end_time = parse_time(doctor.end_time)
        
        if not start_time or not end_time:
            return False
        
        # Check if current time is within working hours
        return start_time <= current_time_str <= end_time
        
    except Exception as e:
        logger.error(f"Error checking doctor availability: {e}")
        return False


# Optimized: Batch fetch queues for multiple doctors in single query
def batch_fetch_queues(doctor_ids: List[str], db: Session) -> Dict[str, DBQueue]:
    """Fetch all queues for given doctor IDs in a single query (eliminates N+1)"""
    if not doctor_ids:
        return {}
    
    queues = db.query(DBQueue).filter(DBQueue.doctor_id.in_(doctor_ids)).all()
    return {q.doctor_id: q for q in queues}


# Optimized: Build queue status from queue object
def build_queue_status(doctor_id: str, queue_obj: Optional[DBQueue]) -> QueueStatus:
    """Build QueueStatus from database queue object or generate fallback"""
    if queue_obj:
        return QueueStatus(
            doctor_id=doctor_id,
            current_token=int(getattr(queue_obj, "current_token", 0) or 0),
            waiting_patients=int(getattr(queue_obj, "waiting_patients", 0) or 0),
            estimated_wait_time_minutes=int(getattr(queue_obj, "estimated_wait_time_minutes", 0) or 0)
        )
    
    # Fallback synthetic queue
    waiting_patients = random.randint(5, 25)
    return QueueStatus(
        doctor_id=doctor_id,
        current_token=random.randint(1, 10),
        waiting_patients=waiting_patients,
        estimated_wait_time_minutes=waiting_patients * 3
    )


def _fmt_time_12h(v: Any) -> Optional[str]:
    """Format time to 12-hour format (HH:MM AM/PM)"""
    try:
        s = str(v or "").strip()
        if not s:
            return None
        low = s.lower()
        if low.endswith("am") or low.endswith("pm"):
            import re
            m = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*$", low)
            if not m:
                return None
            h = int(m.group(1))
            mm = int(m.group(2) or 0)
            mer = m.group(3).upper()
            if h < 1 or h > 12 or mm < 0 or mm > 59:
                return None
            return f"{h:02d}:{mm:02d} {mer}"

        parts = s.split(":")
        if len(parts) != 2:
            return None
        h = int(parts[0])
        mm = int(parts[1])
        if h < 0 or h > 23 or mm < 0 or mm > 59:
            return None
        mer = "AM" if h < 12 else "PM"
        h12 = h % 12
        h12 = 12 if h12 == 0 else h12
        return f"{h12:02d}:{mm:02d} {mer}"
    except Exception:
        return None


@router.patch("/status", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def update_doctor_status(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> Dict[str, Any]:
    doctor_id = str((payload or {}).get("doctor_id") or "").strip()
    new_status = str((payload or {}).get("status") or "").strip().lower()
    if not doctor_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="doctor_id is required")
    if new_status not in {"available", "busy", "offline", "on_leave"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="status is invalid")

    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    # Emergency leave flow: pause queues, update tokens, and notify patients
    if new_status == "on_leave":
        from app.services.doctor_leave_service import DoctorLeaveService

        leave_action = (payload or {}).get("leave_action") or (payload or {}).get("leave_handling")
        alternate_doctor_id = (payload or {}).get("alternate_doctor_id")
        reason = (payload or {}).get("reason") or (payload or {}).get("leave_reason")
        return await DoctorLeaveService.handle_doctor_on_leave(
            doctor_id=doctor_id,
            leave_action=leave_action,
            alternate_doctor_id=alternate_doctor_id,
            reason=reason,
        )

    now = datetime.utcnow()
    doctor.status = new_status
    doctor.updated_at = now
    db.commit()
    db.refresh(doctor)
    
    merged = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
    return {"success": True, "data": merged, "message": "Doctor status updated"}


@router.get("/manage", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def receptionist_manage_doctors(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    hospital_id: Optional[str] = Query(None, description="Optional hospital scope"),
    department: Optional[str] = Query(None, description="Filter by department"),
    search: Optional[str] = Query(None, description="Search by doctor name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),  # Increased default
) -> Dict[str, Any]:
    # OPTIMIZED: Apply filters at database level instead of in-memory
    query = db.query(Doctor)
    
    # Apply hospital filter
    if hospital_id:
        query = query.filter(Doctor.hospital_id == hospital_id)
    
    # Apply department filter at DB level
    if department:
        dep = str(department).strip()
        if dep:
            query = query.filter(
                Doctor.specialization.ilike(f"%{dep}%")
            )
    
    # Apply search filter at DB level
    if search:
        s = str(search).strip()
        if s:
            query = query.filter(Doctor.name.ilike(f"%{s}%"))
    
    # Get total count
    total = query.count()
    
    # Apply pagination and ordering
    doctors = query.order_by(Doctor.updated_at.desc(), Doctor.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    # Convert to response format
    out: List[Dict[str, Any]] = []
    for doctor in doctors:
        it = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
        
        # Format times
        start_fmt = _fmt_time_12h(it.get("start_time"))
        end_fmt = _fmt_time_12h(it.get("end_time"))
        timings = f"{start_fmt} - {end_fmt}" if start_fmt and end_fmt else None
        # Doctor model has 'specialization' field, not 'department'
        dept = it.get("specialization")
        fee_val = it.get("consultation_fee")
        
        out.append(
            {
                "id": it.get("id"),
                "name": it.get("name"),
                "department": dept,
                "qualifications": it.get("specialization") or it.get("subcategory") or dept,
                "fee": fee_val,
                "consultation_fee": fee_val,
                "session_fee": it.get("session_fee"),
                "start_time": it.get("start_time"),
                "end_time": it.get("end_time"),
                "available_days": it.get("available_days") or [],
                "timings": timings,
                "status": str(it.get("status") or "available").lower(),
                "hospital_id": it.get("hospital_id"),
            }
        )

    return {"success": True, "data": out, "meta": {"page": page, "page_size": page_size, "total": total}}


@router.get("/departments", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def receptionist_list_departments(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    hospital_id: Optional[str] = Query(None, description="Optional hospital scope"),
) -> Dict[str, Any]:
    # Extract unique departments/specializations from doctors
    out: List[str] = []
    
    # Extract unique departments from doctors
    query = db.query(Doctor)
    if hospital_id:
        query = query.filter(Doctor.hospital_id == hospital_id)
    
    doctors = query.all()
    names = []
    for doctor in doctors:
        # Doctor model has 'specialization' field, not 'department'
        dept = str(doctor.specialization or "").strip()
        if dept:
            names.append(dept)
    
    out = sorted(set(names), key=lambda x: x.lower())

    return {"success": True, "data": out}


# ==================== DEPARTMENT MANAGEMENT (Admin) ====================

@router.post("/departments", dependencies=[Depends(require_roles("admin"))])
async def create_department(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Create a new department (Admin only)"""
    import uuid
    
    name = str(payload.get("name") or "").strip()
    hospital_id = str(payload.get("hospital_id") or "").strip()
    description = str(payload.get("description") or "").strip()
    
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name is required")
    if not hospital_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hospital ID is required")
    
    # Check if hospital exists
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found")
    
    # Check if department already exists
    existing = db.query(Department).filter(
        Department.name == name,
        Department.hospital_id == hospital_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department already exists")
    
    # Create department
    department_id = str(uuid.uuid4())
    new_department = Department(
        id=department_id,
        name=name,
        hospital_id=hospital_id,
        created_at=datetime.utcnow()
    )
    
    db.add(new_department)
    db.commit()
    db.refresh(new_department)
    
    logger.info(f"Admin {current_user.user_id} created department: {name}")
    
    return ok(
        data={
            "id": new_department.id,
            "name": new_department.name,
            "hospital_id": new_department.hospital_id,
            "created_at": new_department.created_at
        },
        message="Department created successfully"
    )


@router.get("/departments/list", dependencies=[Depends(require_roles("admin", "receptionist"))])
async def get_departments_list(
    db: Session = Depends(get_db),
    hospital_id: Optional[str] = Query(None, description="Filter by hospital"),
) -> Dict[str, Any]:
    """Get all departments (Admin/Receptionist)"""
    query = db.query(Department)
    
    if hospital_id:
        query = query.filter(Department.hospital_id == hospital_id)
    
    departments = query.order_by(Department.name.asc()).all()
    
    return ok(
        data=[
            {
                "id": dept.id,
                "name": dept.name,
                "hospital_id": dept.hospital_id,
                "created_at": dept.created_at
            }
            for dept in departments
        ]
    )


@router.put("/departments/{department_id}", dependencies=[Depends(require_roles("admin"))])
@router.patch("/departments/{department_id}", dependencies=[Depends(require_roles("admin"))])
async def update_department(
    department_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Update department details (Admin only) - Edit button uses this"""
    department = db.query(Department).filter(Department.id == department_id).first()
    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    
    # Update allowed fields
    if "name" in payload:
        new_name = str(payload["name"]).strip()
        if not new_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name cannot be empty")
        department.name = new_name
    
    if "description" in payload:
        department.description = str(payload["description"]).strip()
    
    if "hospital_id" in payload:
        new_hospital_id = str(payload["hospital_id"]).strip()
        if new_hospital_id:
            # Verify hospital exists
            hospital = db.query(Hospital).filter(Hospital.id == new_hospital_id).first()
            if not hospital:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found")
            department.hospital_id = new_hospital_id
    
    db.commit()
    db.refresh(department)
    
    logger.info(f"Admin {current_user.user_id} updated department: {department_id}")
    
    return ok(
        data={
            "id": department.id,
            "name": department.name,
            "hospital_id": department.hospital_id,
            "created_at": department.created_at
        },
        message="Department updated successfully"
    )


@router.delete("/departments/{department_id}", dependencies=[Depends(require_roles("admin"))])
async def delete_department(
    department_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Delete a department (Admin only)"""
    department = db.query(Department).filter(Department.id == department_id).first()
    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    
    # Check if any doctors are using this department
    doctors_count = db.query(Doctor).filter(
        Doctor.specialization == department.name,
        Doctor.hospital_id == department.hospital_id
    ).count()
    
    if doctors_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete department. {doctors_count} doctor(s) are assigned to this department"
        )
    
    db.delete(department)
    db.commit()
    
    logger.info(f"Admin {current_user.user_id} deleted department: {department_id}")
    
    return ok(message="Department deleted successfully")


@router.patch("/{doctor_id}", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def receptionist_update_doctor(
    doctor_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):

    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    allowed = {
        "name",
        "department",
        "specialization",
        "subcategory",
        "phone",
        "email",
        "experience_years",
        "fee",
        "consultation_fee",
        "session_fee",
        "available_days",
        "start_time",
        "end_time",
        "room",
        "room_number",
        "qualifications",
        "qualification",
        "degrees",
        "patients_per_day",
        "status",
    }
    update: Dict[str, Any] = {}
    for k, v in (payload or {}).items():
        if k in allowed:
            update[k] = v

    if "fee" in update and "consultation_fee" not in update:
        update["consultation_fee"] = update.get("fee")
    update.pop("fee", None)

    if "start_time" in update:
        norm = _normalize_time_to_hhmm(update.get("start_time"))
        if update.get("start_time") and not norm:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_time is invalid")
        if norm:
            update["start_time"] = norm

    if "end_time" in update:
        norm = _normalize_time_to_hhmm(update.get("end_time"))
        if update.get("end_time") and not norm:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_time is invalid")
        if norm:
            update["end_time"] = norm

    if "department" in update and "specialization" not in update:
        update["specialization"] = update.get("department")
    if "specialization" in update and "department" not in update:
        update["department"] = update.get("specialization")

    if "status" in update and update["status"] is not None:
        update["status"] = str(update["status"]).strip().lower()
        if update["status"] not in {"available", "busy", "offline", "on_leave"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="status is invalid")

    merged = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
    merged.update(update)

    dept_text = (
        f"{merged.get('specialization') or ''} "
        f"{merged.get('subcategory') or ''} "
        f"{merged.get('department') or ''}"
    ).lower().strip()
    inferred_has_session = any(
        kw in dept_text for kw in ("psychology", "psychiatry", "physiotherapist", "physiotherapy", "physio")
    )
    if inferred_has_session:
        try:
            session_fee_val = float(merged.get("session_fee") or 0)
        except Exception:
            session_fee_val = 0
        if session_fee_val <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="session_fee is required and must be > 0 for session-based departments",
            )
        merged["has_session"] = True
        merged["pricing_type"] = "session_based"
        merged["session_fee"] = session_fee_val
    else:
        merged["has_session"] = False
        merged["pricing_type"] = "standard"
        merged["session_fee"] = None

    merged["updated_at"] = datetime.utcnow()
    persist = dict(update)
    persist.update(
        {
            "has_session": merged.get("has_session"),
            "session_fee": merged.get("session_fee"),
            "pricing_type": merged.get("pricing_type"),
            "specialization": merged.get("specialization") or merged.get("department"),
            "updated_at": merged.get("updated_at"),
        }
    )
    
    # Remove 'department' from persist as Doctor DB model only has 'specialization'
    persist.pop("department", None)
    persist.pop("room", None)  # Room field doesn't exist in DB model
    persist.pop("qualifications", None)  # Qualifications field doesn't exist in DB model
    persist.pop("qualification", None)  # Qualifications field doesn't exist in DB model
    persist.pop("degrees", None)  # Degrees field doesn't exist in DB model
    persist.pop("experience_years", None)  # Experience years field doesn't exist in DB model
    persist.pop("phone", None)  # Phone field doesn't exist in DB model
    persist.pop("email", None)  # Email field exists but may not be intended to update here
    
    # Update doctor in PostgreSQL
    for key, value in persist.items():
        if hasattr(doctor, key):
            setattr(doctor, key, value)
    
    db.commit()
    db.refresh(doctor)
    
    if not merged.get("id"):
        merged["id"] = doctor_id
    return {"success": True, "data": merged, "message": "Doctor updated"}

# -------------------- Time Normalization --------------------
def _normalize_time_to_hhmm(s: Optional[str]) -> Optional[str]:
    """Accepts 'HH:MM' or 'H[:MM] AM/PM' and returns zero-padded 24-hour 'HH:MM'.
    Returns None if input is falsy or invalid.
    """
    if s is None:
        return None
    val = str(s).strip()
    if not val:
        return None
    low = val.lower()
    try:
        # AM/PM formats
        if low.endswith("am") or low.endswith("pm"):
            import re
            m = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*$", low)
            if not m:
                return None
            h = int(m.group(1))
            mm = int(m.group(2) or 0)
            mer = m.group(3)
            if h < 1 or h > 12 or mm < 0 or mm > 59:
                return None
            if mer == "am":
                h = 0 if h == 12 else h
            else:
                h = 12 if h == 12 else h + 12
            return f"{h:02d}:{mm:02d}"

        # 24-hour HH:MM
        parts = val.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            h = int(parts[0])
            mm = int(parts[1])
            if 0 <= h <= 23 and 0 <= mm <= 59:
                return f"{h:02d}:{mm:02d}"
            return None

        # Hour-only -> HH:00
        if val.isdigit():
            h = int(val)
            if 0 <= h <= 23:
                return f"{h:02d}:00"
            return None
        return None
    except Exception:
        return None

@router.post("/", response_model=DoctorResponse)
async def create_doctor(
    doctor: DoctorCreate,
    db: Session = Depends(get_db)
):
    """Create a new doctor"""
    # Check if doctor with same name and hospital already exists
    existing_doctor = db.query(Doctor).filter(
        Doctor.name == doctor.name,
        Doctor.hospital_id == doctor.hospital_id
    ).first()
    
    if existing_doctor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doctor with this name already exists in this hospital"
        )

    import uuid
    doctor_id = str(uuid.uuid4())
    doctor_data = doctor.dict()

    # Normalize schedule times to 24-hour HH:MM if provided (support AM/PM input from frontend)
    norm_start = _normalize_time_to_hhmm(doctor_data.get("start_time"))
    norm_end = _normalize_time_to_hhmm(doctor_data.get("end_time"))
    if norm_start:
        doctor_data["start_time"] = norm_start
    if norm_end:
        doctor_data["end_time"] = norm_end
    doctor_data["id"] = doctor_id
    doctor_data["created_at"] = datetime.utcnow()
    doctor_data["updated_at"] = datetime.utcnow()

    # Keep Firestore documents compatible with both field names.
    # Your DB uses `department`, but much of the code historically uses `specialization`.
    # Map department to specialization for DB compatibility
    if "department" in doctor_data and "specialization" not in doctor_data:
        doctor_data["specialization"] = doctor_data["department"]
    # Remove 'department' key as Doctor DB model only has 'specialization'
    doctor_data.pop("department", None)

    # ---------------- Session-based pricing rules (doctor creation validation) ----------------
    dept_text = (
        f"{doctor_data.get('specialization') or ''} "
        f"{doctor_data.get('subcategory') or ''} "
        f"{doctor_data.get('department') or ''}"
    ).lower().strip()
    inferred_has_session = any(
        kw in dept_text for kw in ("psychology", "psychiatry", "physiotherapist", "physiotherapy", "physio")
    )
    if inferred_has_session:
        try:
            session_fee_val = float(doctor_data.get("session_fee") or 0)
        except Exception:
            session_fee_val = 0
        if session_fee_val <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="session_fee is required and must be > 0 for Psychology/Psychiatry/Physiotherapy departments",
            )
        doctor_data["has_session"] = True
        doctor_data["pricing_type"] = "session_based"
        doctor_data["session_fee"] = session_fee_val
    else:
        doctor_data["has_session"] = False
        doctor_data["pricing_type"] = "standard"
        doctor_data["session_fee"] = None
    
    # Generate avatar initials from name
    if not doctor_data.get("avatar_initials"):
        name_parts = doctor.name.split()
        if len(name_parts) >= 2:
            doctor_data["avatar_initials"] = f"{name_parts[0][0]}{name_parts[1][0]}".upper()
        else:
            doctor_data["avatar_initials"] = doctor.name[:2].upper()

    # Create doctor in PostgreSQL
    new_doctor = Doctor(**doctor_data)
    db.add(new_doctor)
    db.commit()
    db.refresh(new_doctor)
    
    return DoctorResponse(**doctor_data)


@router.delete("/{doctor_id}", dependencies=[Depends(require_roles("admin", "receptionist"))])
async def delete_doctor(
    doctor_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Delete a doctor (Admin/Receptionist only)"""
    # Find the doctor
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    # Check if doctor has active tokens/appointments
    from sqlalchemy import func
    active_tokens = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status.in_(["pending", "waiting", "confirmed", "called", "in_consultation"])
    ).count()
    
    if active_tokens > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete doctor. They have {active_tokens} active token(s). Please cancel or complete them first."
        )
    
    # Get doctor info for response
    doctor_name = doctor.name
    doctor_specialization = doctor.specialization
    
    # Delete all tokens associated with this doctor (historical data is preserved in token snapshots)
    tokens_to_delete = db.query(Token).filter(Token.doctor_id == doctor_id).all()
    
    # Delete refunds associated with these tokens first (to avoid foreign key violation)
    token_ids = [token.id for token in tokens_to_delete]
    if token_ids:
        refunds_to_delete = db.query(Refund).filter(Refund.token_id.in_(token_ids)).all()
        for refund in refunds_to_delete:
            db.delete(refund)
    
    # Delete tokens
    for token in tokens_to_delete:
        db.delete(token)
    
    # Delete the doctor
    db.delete(doctor)
    db.commit()
    
    logger.info(f"User {current_user.user_id} deleted doctor: {doctor_id} ({doctor_name})")
    
    return {
        "success": True,
        "message": f"Doctor {doctor_name} ({doctor_specialization}) has been deleted successfully",
        "deleted_doctor_id": doctor_id,
        "deleted_doctor_name": doctor_name,
        "deleted_tokens_count": len(tokens_to_delete),
        "deleted_refunds_count": len(refunds_to_delete) if token_ids else 0
    }


@router.get("/{doctor_id}/available-slots")
async def get_available_slots(
    doctor_id: str,
    day: str = Query(..., description="DD-MM-YYYY"),
    slot_minutes: int = Query(15, ge=5, le=60),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Generate available slots for a doctor from their availability."""
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    doc = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}

    # Hide/disable slots during emergency leave
    status_val = str(doc.get("status") or "").lower()
    if status_val in {"offline", "on_leave"} or bool(doc.get("queue_paused")) or bool(doc.get("paused")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor unavailable")

    from app.services.slot_booking_service import _parse_day_dd_mm_yyyy, generate_slots_for_doctor, slot_id_for, _parse_time_hhmm_ampm

    d = _parse_day_dd_mm_yyyy(day)
    slots = generate_slots_for_doctor(doc, d, slot_minutes=slot_minutes)

    # Mark booked/reserved by checking appointments docs
    # TODO: Create Appointment model in db_models and implement this
    out = []
    for s in slots:
        # For now, mark all slots as available
        out.append({"time": s.get("time"), "available": True})

    return {"doctor_id": doctor_id, "day": day, "slot_minutes": slot_minutes, "slots": out}

@router.get("/", response_model=List[DoctorResponse])
async def list_doctors(
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    specialization: Optional[str] = Query(None, description="Filter by specialization"),
    subcategory: Optional[str] = Query(None, description="Filter by subcategory"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List all doctors with optional filtering - OPTIMIZED with DB-level filtering"""
    # Build query with database-level filtering (not in-memory)
    query = db.query(Doctor)
    
    # Apply hospital filter
    if hospital_id:
        query = query.filter(Doctor.hospital_id == hospital_id)
    
    # Apply specialization filter using ILIKE (case-insensitive)
    if specialization:
        spec_norm = f"%{specialization.strip()}%"
        query = query.filter(
            Doctor.specialization.ilike(spec_norm) | Doctor.subcategory.ilike(spec_norm)
        )
    
    # Apply subcategory filter
    if subcategory:
        sub_norm = f"%{subcategory.strip()}%"
        query = query.filter(
            Doctor.subcategory.ilike(sub_norm) | Doctor.specialization.ilike(sub_norm)
        )
    
    # Fetch with limit
    doctors = query.order_by(Doctor.created_at.desc()).limit(limit).all()
    
    # Convert to response objects
    results = []
    for doctor in doctors:
        doctor_data = {
            "id": doctor.id,
            "name": doctor.name,
            "specialization": doctor.specialization,
            "subcategory": doctor.subcategory,
            "hospital_id": doctor.hospital_id,
            "consultation_fee": doctor.consultation_fee,
            "session_fee": doctor.session_fee,
            "status": doctor.status,
            "available_days": doctor.available_days or [],
            "start_time": doctor.start_time,
            "end_time": doctor.end_time,
            "avatar_initials": doctor.avatar_initials,
            "rating": doctor.rating,
            "review_count": doctor.review_count,
            "created_at": doctor.created_at,
            "updated_at": doctor.updated_at,
        }
        results.append(DoctorResponse(**doctor_data))
    
    return results

@router.get("/hospital/{hospital_id}", response_model=DoctorSearchResponse)
async def get_doctors_by_hospital(
    hospital_id: str,
    category: Optional[str] = Query(None, description="Filter by main category or specialization (General Medical, Specialist, Surgeon, or specific)"),
    subcategory: Optional[str] = Query(None, description="Filter by subcategory"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Get doctors for a specific hospital with optional main category & subcategory filter.
    OPTIMIZED: Batch fetches queues to eliminate N+1 queries
    """
    # Query doctors from PostgreSQL with limit
    doctors = db.query(Doctor).filter(Doctor.hospital_id == hospital_id).limit(200).all()

    main_category_map = {
        "General Medical": [
            "General Medicine", "Family Medicine", "Internal Medicine", "Emergency Medicine"
        ],
        "Specialist": [
            "Cardiology", "Neurology", "Dermatology", "Pediatrics", "Psychiatry",
            "Radiology", "Pathology", "Anesthesiology", "Oncology", "Endocrinology",
            "Gastroenterology", "Pulmonology", "Nephrology", "Rheumatology",
            "Ophthalmology", "ENT", "Gynecology", "Urology"
        ],
        "Surgeon": [
            "General Surgery", "Cardiac Surgery", "Heart Surgeon", "Neuro Surgeon",
            "Ortho Surgeon", "Plastic Surgery", "Vascular Surgery", "Thoracic Surgery",
            "Pediatric Surgery", "Trauma Surgery", "Transplant Surgery",
            "Laparoscopic Surgery", "Reconstructive Surgery", "Surgeon"
        ],
    }

    # Normalize category for main-category matching
    resolved_subcategories: Optional[List[str]] = None
    main_selected = None
    if category:
        for key, subs in main_category_map.items():
            if category.strip().lower() == key.lower():
                main_selected = key
                resolved_subcategories = list(subs)
                break

    # Filter doctors based on category/subcategory
    filtered_doctors = []
    for doctor in doctors:
        doctor_sub = (doctor.subcategory or "").strip()
        doctor_spec = (doctor.specialization or "").strip()

        # If a concrete subcategory is given, match it exactly
        if subcategory:
            if doctor_sub.lower() == subcategory.strip().lower() or doctor_spec.lower() == subcategory.strip().lower():
                filtered_doctors.append(doctor)
            continue

        # If main category selected -> inclusion rules
        if main_selected == "Surgeon":
            if "surgeon" in doctor_sub.lower() or "surgeon" in doctor_spec.lower() or (
                resolved_subcategories and (
                    doctor_sub in resolved_subcategories or doctor_spec in resolved_subcategories
                )
            ):
                filtered_doctors.append(doctor)
            continue
        elif main_selected == "General Medical":
            if doctor_sub in main_category_map["General Medical"] or doctor_spec in main_category_map["General Medical"]:
                filtered_doctors.append(doctor)
            continue
        elif main_selected == "Specialist":
            if (
                "surgeon" not in doctor_sub.lower() and "surgeon" not in doctor_spec.lower()
                and doctor_sub not in main_category_map["General Medical"]
                and doctor_spec not in main_category_map["General Medical"]
            ):
                if not resolved_subcategories or doctor_sub in resolved_subcategories or doctor_spec in resolved_subcategories:
                    filtered_doctors.append(doctor)
            continue

        # If category provided but not a main category, treat it as a specialization filter
        if category and main_selected is None:
            if doctor_spec.lower() == category.strip().lower() or doctor_sub.lower() == category.strip().lower():
                filtered_doctors.append(doctor)
            continue

        # No category filters: include
        filtered_doctors.append(doctor)

    # Limit results
    filtered_doctors = filtered_doctors[:limit]

    # OPTIMIZATION: Batch fetch all queues in single query (eliminates N+1)
    doctor_ids = [d.id for d in filtered_doctors]
    queues_map = batch_fetch_queues(doctor_ids, db)

    # Build response with queue info
    doctors_with_queue = []
    for doctor in filtered_doctors:
        doctor_data = {
            "id": doctor.id,
            "name": doctor.name,
            "specialization": doctor.specialization,
            "subcategory": doctor.subcategory,
            "hospital_id": doctor.hospital_id,
            "consultation_fee": doctor.consultation_fee,
            "session_fee": doctor.session_fee,
            "status": doctor.status,
            "available_days": doctor.available_days or [],
            "start_time": doctor.start_time,
            "end_time": doctor.end_time,
            "avatar_initials": doctor.avatar_initials,
            "rating": doctor.rating,
            "review_count": doctor.review_count,
            "created_at": doctor.created_at,
            "updated_at": doctor.updated_at,
        }
        
        doctor_response = DoctorResponse(**doctor_data)
        queue_obj = queues_map.get(doctor.id)
        queue = build_queue_status(doctor.id, queue_obj)
        doctors_with_queue.append(DoctorWithQueue(doctor=doctor_response, queue=queue))

    # Clean subcategories to avoid returning main labels and duplicates
    main_labels_norm = {k.strip().lower() for k in main_category_map.keys()}
    cleaned_subcats = sorted({
        s for s in (resolved_subcategories or [])
        if s and s.strip().lower() not in main_labels_norm
    }, key=lambda x: x.lower())

    return {
        "doctors": doctors_with_queue,
        "total_found": len(doctors_with_queue),
        "hospital_id": hospital_id,
        "category": category,
        "subcategories": cleaned_subcats
    }

@router.get("/search", response_model=DoctorSearchResponse)
async def search_doctors(
    query: str = Query(..., min_length=0, description="Search query for doctor name or specialization"),
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    category: Optional[str] = Query(None, description="Filter by specialization category"),
    subcategory: Optional[str] = Query(None, description="Filter by subcategory"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Search doctors by name, specialization, or subcategory - OPTIMIZED with DB-level filtering"""
    # Build query with database-level ILIKE filtering
    query_obj = db.query(Doctor)
    
    # Apply hospital filter
    if hospital_id:
        query_obj = query_obj.filter(Doctor.hospital_id == hospital_id)
    
    # Apply search query using ILIKE (case-insensitive)
    if query:
        search_pattern = f"%{query.strip()}%"
        query_obj = query_obj.filter(
            Doctor.name.ilike(search_pattern) |
            Doctor.specialization.ilike(search_pattern) |
            Doctor.subcategory.ilike(search_pattern)
        )
    
    # Apply category filter
    if category:
        query_obj = query_obj.filter(
            Doctor.specialization.ilike(f"%{category.strip()}%") |
            Doctor.subcategory.ilike(f"%{category.strip()}%")
        )
    
    # Apply subcategory filter
    if subcategory:
        query_obj = query_obj.filter(
            Doctor.subcategory.ilike(f"%{subcategory.strip()}%") |
            Doctor.specialization.ilike(f"%{subcategory.strip()}%")
        )
    
    # Fetch with limit
    doctors = query_obj.order_by(Doctor.name).limit(limit).all()
    
    # OPTIMIZATION: Batch fetch all queues in single query
    doctor_ids = [d.id for d in doctors]
    queues_map = batch_fetch_queues(doctor_ids, db)
    
    # Build response
    doctors_with_queue = []
    for doctor in doctors:
        doctor_data = {
            "id": doctor.id,
            "name": doctor.name,
            "specialization": doctor.specialization,
            "subcategory": doctor.subcategory,
            "hospital_id": doctor.hospital_id,
            "consultation_fee": doctor.consultation_fee,
            "session_fee": doctor.session_fee,
            "status": doctor.status,
            "available_days": doctor.available_days or [],
            "start_time": doctor.start_time,
            "end_time": doctor.end_time,
            "avatar_initials": doctor.avatar_initials,
            "rating": doctor.rating,
            "review_count": doctor.review_count,
            "created_at": doctor.created_at,
            "updated_at": doctor.updated_at,
        }
        
        doctor_response = DoctorResponse(**doctor_data)
        queue_obj = queues_map.get(doctor.id)
        queue = build_queue_status(doctor.id, queue_obj)
        doctors_with_queue.append(DoctorWithQueue(doctor=doctor_response, queue=queue))
    
    return DoctorSearchResponse(
        doctors=doctors_with_queue,
        total_found=len(doctors_with_queue),
        hospital_id=hospital_id or "",
        category=category
    )

@router.get("/categories")
@cached(ttl=CacheService.TTL_VERY_LONG)  # Cache for 24 hours - never changes
async def get_doctor_categories():
    """Get organized doctor categories with subcategories - CACHED"""
    return {
        "General Medical": [
            "General Medicine",
            "Family Medicine",
            "Internal Medicine",
            "Emergency Medicine"
        ],
        "Specialist": [
            "Cardiology",
            "Neurology", 
            "Dermatology",
            "Pediatrics",
            "Psychiatry",
            "Radiology",
            "Pathology",
            "Anesthesiology",
            "Oncology",
            "Endocrinology",
            "Gastroenterology",
            "Pulmonology",
            "Nephrology",
            "Rheumatology",
            "Ophthalmology",
            "ENT",
            "Gynecology",
            "Urology"
        ],
        "Surgeon": [
            "General Surgery",
            "Cardiac Surgery", 
            "Heart Surgeon",
            "Neuro Surgeon",
            "Ortho Surgeon",
            "Plastic Surgery",
            "Vascular Surgery",
            "Thoracic Surgery",
            "Pediatric Surgery",
            "Trauma Surgery",
            "Transplant Surgery",
            "Laparoscopic Surgery",
            "Reconstructive Surgery"
        ]
    }

@router.get("/subcategories")
async def get_subcategories(
    main_category: str = Query(..., description="One of: General Medical, Specialist, Surgeon"),
    hospital_id: Optional[str] = Query(None, description="If provided, returns only subcategories present in this hospital's doctors"),
    db: Session = Depends(get_db)
):
    """Return subcategories for a selected main category - OPTIMIZED"""

    category_mappings = {
        "General Medical": [
            "General Medicine", "Family Medicine", "Internal Medicine", "Emergency Medicine"
        ],
        "Specialist": [
            "Cardiology", "Neurology", "Dermatology", "Pediatrics", "Psychiatry",
            "Radiology", "Pathology", "Anesthesiology", "Oncology", "Endocrinology",
            "Gastroenterology", "Pulmonology", "Nephrology", "Rheumatology",
            "Ophthalmology", "ENT", "Gynecology", "Urology"
        ],
        "Surgeon": [
            "General Surgery", "Cardiac Surgery", "Heart Surgeon", "Neuro Surgeon",
            "Ortho Surgeon", "Plastic Surgery", "Vascular Surgery", "Thoracic Surgery",
            "Pediatric Surgery", "Trauma Surgery", "Transplant Surgery",
            "Laparoscopic Surgery", "Reconstructive Surgery", "Surgeon"
        ],
    }

    if main_category not in category_mappings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {list(category_mappings.keys())}"
        )

    # No hospital filter: return static list
    if not hospital_id:
        main_labels_norm = {k.strip().lower() for k in category_mappings.keys()}
        cleaned = sorted({ s for s in category_mappings[main_category] if s and s.strip().lower() not in main_labels_norm }, key=lambda x: x.lower())
        return {"main_category": main_category, "subcategories": cleaned}

    # Dynamic list constrained to a specific hospital
    doctors = db.query(Doctor).filter(Doctor.hospital_id == hospital_id).all()

    dyn: set[str] = set()
    general_set = set(category_mappings["General Medical"])  # for exclusions
    for doctor in doctors:
        sub = (doctor.subcategory or "").strip()
        spec = (doctor.specialization or "").strip()
        low_sub = sub.lower()
        low_spec = spec.lower()

        if main_category == "Surgeon":
            if "surgeon" in low_sub or "surgeon" in low_spec:
                if sub:
                    dyn.add(sub)
                if spec:
                    dyn.add(spec)
        elif main_category == "General Medical":
            if sub in category_mappings["General Medical"]:
                dyn.add(sub)
            if spec in category_mappings["General Medical"]:
                dyn.add(spec)
        else:  # Specialist
            if ("surgeon" not in low_sub and sub and sub not in general_set):
                dyn.add(sub)
            if ("surgeon" not in low_spec and spec and spec not in general_set):
                dyn.add(spec)

    main_labels_norm = {k.strip().lower() for k in category_mappings.keys()}
    cleaned = sorted({ s for s in dyn if s and s.strip().lower() not in main_labels_norm }, key=lambda x: x.lower())
    return {"main_category": main_category, "hospital_id": hospital_id, "subcategories": cleaned}


@router.get("/{doctor_id}", response_model=DoctorResponse)
async def get_doctor(
    doctor_id: str,
    db: Session = Depends(get_db)
):
    """Get doctor by ID"""
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    return DoctorResponse(
        id=doctor.id,
        name=doctor.name,
        specialization=doctor.specialization,
        subcategory=doctor.subcategory,
        hospital_id=doctor.hospital_id,
        consultation_fee=doctor.consultation_fee,
        session_fee=doctor.session_fee,
        status=doctor.status,
        available_days=doctor.available_days or [],
        start_time=doctor.start_time,
        end_time=doctor.end_time,
        avatar_initials=doctor.avatar_initials,
        rating=doctor.rating,
        review_count=doctor.review_count,
    )


@router.get("/{doctor_id}/availability")
async def get_doctor_availability(
    doctor_id: str,
    db: Session = Depends(get_db)
):
    """Return a doctor's availability schedule for pre-booking display."""
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    return {
        "doctor_id": doctor_id,
        "status": doctor.status,
        "available_days": doctor.available_days or [],
        "start_time": doctor.start_time,
        "end_time": doctor.end_time,
    }


@router.get("/{doctor_id}/availability/today")
async def get_doctor_availability_today(
    doctor_id: str,
    db: Session = Depends(get_db)
):
    """Return whether the doctor is available today and today's time window."""
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    status_val = str(doctor.status or "").lower()
    start_time = (doctor.start_time or "").strip()
    end_time = (doctor.end_time or "").strip()
    days = [str(x).strip().lower() for x in (doctor.available_days or [])]
    
    from datetime import timezone as tz
    today_name = datetime.now(tz.utc).strftime("%A").lower()
    available_today = (
        status_val not in {"offline", "on_leave"} and
        bool(start_time) and bool(end_time) and
        ((not days) or (today_name in days))
    )

    return {
        "doctor_id": doctor_id,
        "available_today": available_today,
        "today_window": f"{start_time}-{end_time}" if start_time and end_time else None,
        "status": doctor.status,
        "available_days": doctor.available_days or [],
    }


@router.get("/by-category/{main_category}")
async def get_doctors_by_main_category(
    main_category: str,
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    subcategory: Optional[str] = Query(None, description="Filter by subcategory"),
    limit: int = Query(20, ge=1, le=50),
    available_only: bool = Query(False, description="Show only doctors available RIGHT NOW"),
    db: Session = Depends(get_db)
):
    """Get doctors by main category - OPTIMIZED with real-time availability check"""
    
    category_mappings = {
        "General Medical": [
            "General Medicine", "Family Medicine", "Internal Medicine", "Emergency Medicine"
        ],
        "Specialist": [
            "Cardiology", "Neurology", "Dermatology", "Pediatrics", "Psychiatry",
            "Radiology", "Pathology", "Anesthesiology", "Oncology", "Endocrinology",
            "Gastroenterology", "Pulmonology", "Nephrology", "Rheumatology",
            "Ophthalmology", "ENT", "Gynecology", "Urology"
        ],
        "Surgeon": [
            "General Surgery", "Cardiac Surgery", "Heart Surgeon", "Neuro Surgeon",
            "Ortho Surgeon", "Plastic Surgery", "Vascular Surgery", "Thoracic Surgery",
            "Pediatric Surgery", "Trauma Surgery", "Transplant Surgery",
            "Laparoscopic Surgery", "Reconstructive Surgery", "Surgeon"
        ]
    }
    
    if main_category not in category_mappings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {list(category_mappings.keys())}"
        )
    
    # Build query with database-level filtering
    query_obj = db.query(Doctor)
    
    if hospital_id:
        query_obj = query_obj.filter(Doctor.hospital_id == hospital_id)
    
    # Fetch doctors and filter by category
    doctors = query_obj.limit(200).all()
    subcategories = category_mappings[main_category]
    
    results = []
    for doctor in doctors:
        doctor_specialization = doctor.specialization or ""
        doctor_subcategory = doctor.subcategory or ""
        
        # Check if matches category or specific subcategory
        if subcategory:
            if doctor_subcategory.lower() == subcategory.lower() or doctor_specialization.lower() == subcategory.lower():
                # Check real-time availability if requested
                if available_only and not _is_doctor_available_today(doctor):
                    continue
                results.append(doctor)
        else:
            # Include if doctor's subcategory OR specialization matches any subcategory in the main category
            if any(
                subcat.lower() == doctor_subcategory.lower() or subcat.lower() == doctor_specialization.lower()
                for subcat in subcategories
            ):
                # Check real-time availability if requested
                if available_only and not _is_doctor_available_today(doctor):
                    continue
                results.append(doctor)
            
        if len(results) >= limit:
            break
    
    # OPTIMIZATION: Batch fetch all queues in single query
    doctor_ids = [d.id for d in results]
    queues_map = batch_fetch_queues(doctor_ids, db)
    
    doctors_with_queue = []
    for doctor in results:
        doctor_data = {
            "id": doctor.id,
            "name": doctor.name,
            "specialization": doctor.specialization,
            "subcategory": doctor.subcategory,
            "hospital_id": doctor.hospital_id,
            "consultation_fee": doctor.consultation_fee,
            "session_fee": doctor.session_fee,
            "status": doctor.status,
            "available_days": doctor.available_days or [],
            "start_time": doctor.start_time,
            "end_time": doctor.end_time,
            "avatar_initials": doctor.avatar_initials,
            "rating": doctor.rating,
            "review_count": doctor.review_count,
            "created_at": doctor.created_at,
            "updated_at": doctor.updated_at,
        }
        
        doctor_response = DoctorResponse(**doctor_data)
        queue_obj = queues_map.get(doctor.id)
        queue = build_queue_status(doctor.id, queue_obj)
        doctors_with_queue.append(DoctorWithQueue(doctor=doctor_response, queue=queue))
    
    # Clean subcategories to avoid returning main labels and duplicates
    main_labels_norm = { k.strip().lower() for k in category_mappings.keys() }
    cleaned_subcats = sorted({ s for s in subcategories if s and s.strip().lower() not in main_labels_norm }, key=lambda x: x.lower())

    return {
        "doctors": doctors_with_queue,
        "total_found": len(doctors_with_queue),
        "main_category": main_category,
        "subcategories": cleaned_subcats
    }

@router.get("/{doctor_id}/queue", response_model=QueueStatus)
async def get_doctor_queue_status(doctor_id: str, db: Session = Depends(get_db)):
    """Get current queue status for a doctor"""
    # Verify doctor exists
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    # Get queue from database
    queue = db.query(DBQueue).filter(DBQueue.doctor_id == doctor_id).first()
    
    if queue:
        return QueueStatus(
            doctor_id=doctor_id,
            current_token=int(getattr(queue, "current_token", 0) or 0),
            pending_patients=int(getattr(queue, "waiting_patients", 0) or 0),
            in_progress_patients=0,  # Can be calculated from tokens if needed
            completed_patients=0,  # Can be calculated from tokens if needed
            estimated_wait_time=int(getattr(queue, "estimated_wait_time_minutes", 0) or 0),
            people_ahead=int(getattr(queue, "waiting_patients", 0) or 0),
            total_queue=int(getattr(queue, "waiting_patients", 0) or 0),
            total_patients=int(getattr(queue, "waiting_patients", 0) or 0)
        )
    
    # If no queue exists, calculate from tokens
    pending_tokens = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status.in_(["pending", "waiting", "confirmed"])
    ).count()
    
    in_progress_tokens = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status.in_(["called", "in_consultation"])
    ).count()
    
    completed_tokens = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status.in_(["completed", "cancelled"])
    ).count()
    
    total_in_queue = pending_tokens + in_progress_tokens
    
    return QueueStatus(
        doctor_id=doctor_id,
        current_token=0,
        pending_patients=pending_tokens,
        in_progress_patients=in_progress_tokens,
        completed_patients=completed_tokens,
        estimated_wait_time=pending_tokens * 3,  # Estimate 3 minutes per patient
        people_ahead=pending_tokens,
        total_queue=total_in_queue,
        total_patients=total_in_queue
    )

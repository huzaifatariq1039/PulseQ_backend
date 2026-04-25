from fastapi import APIRouter, HTTPException, status, Query, Depends
from typing import List, Optional, Dict, Any
from app.models import DoctorCreate, DoctorResponse, DoctorSearchResponse, DoctorWithQueue, QueueStatus
from app.database import get_db
from app.utils.responses import ok
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db_models import Doctor, Hospital, User
from app.security import get_current_active_user, require_roles, get_password_hash
from datetime import datetime
import random

router = APIRouter()


@router.patch("/status", dependencies=[Depends(require_roles("receptionist", "admin", "patient"))])
async def update_doctor_status(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
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
    return ok(data=merged, message="Doctor status updated")


@router.get("/manage", dependencies=[Depends(require_roles("receptionist", "admin", "patient"))])
async def receptionist_manage_doctors(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    hospital_id: Optional[str] = Query(None, description="Optional hospital scope"),
    department: Optional[str] = Query(None, description="Filter by department"),
    search: Optional[str] = Query(None, description="Search by doctor name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
):
    # Query doctors from PostgreSQL
    query = db.query(Doctor)
    if hospital_id:
        query = query.filter(Doctor.hospital_id == hospital_id)
    
    doctors = query.all()
    
    items: List[Dict[str, Any]] = []
    for doctor in doctors:
        data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
        
        # Add compatibility fields for frontend
        data["department"] = data.get("specialization")
        data["fee"] = data.get("consultation_fee")
        data["per_session_fee"] = data.get("session_fee")
        
        items.append(data)

    if department:
        dep = str(department).strip().lower()
        if dep:
            items = [
                it
                for it in items
                if dep
                in str(it.get("department") or it.get("specialization") or "").strip().lower()
            ]

    if search:
        s = str(search).strip().lower()
        if s:
            items = [it for it in items if s in str(it.get("name") or "").strip().lower()]

    def _sort_key(x: Dict[str, Any]):
        val = x.get("updated_at") or x.get("created_at")
        try:
            if isinstance(val, datetime):
                return val
            to_dt = getattr(val, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(val))
        except Exception:
            return datetime.min

    items.sort(key=_sort_key, reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    def _fmt_time_12h(v: Any) -> Optional[str]:
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

    out: List[Dict[str, Any]] = []
    for it in page_items:
        start_fmt = _fmt_time_12h(it.get("start_time"))
        end_fmt = _fmt_time_12h(it.get("end_time"))
        timings = f"{start_fmt} - {end_fmt}" if start_fmt and end_fmt else None
        dept = it.get("department") or it.get("specialization")
        fee_val = it.get("consultation_fee")
        out.append(
            {
                "id": it.get("id"),
                "name": it.get("name"),
                "department": dept,
                "qualifications": it.get("qualifications") or it.get("qualification") or it.get("degrees"),
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

    return ok(data=out, meta={"page": page, "page_size": page_size, "total": total})


@router.get("/departments")
async def list_departments(
    db: Session = Depends(get_db),
    hospital_id: Optional[str] = Query(None, description="Optional hospital scope"),
):
    # Departments table may not exist in PostgreSQL, fallback to extracting from doctors
    out: List[str] = []
    
    # Extract unique departments from doctors
    query = db.query(Doctor)
    if hospital_id:
        query = query.filter(Doctor.hospital_id == hospital_id)
    
    doctors = query.all()
    names = []
    for doctor in doctors:
        # Use getattr safely as Doctor model uses 'specialization' but some code expects 'department'
        dept = str(getattr(doctor, 'department', getattr(doctor, 'specialization', "")) or "").strip()
        if dept:
            names.append(dept)
    
    out = sorted(set(names), key=lambda x: x.lower())

    return ok(data=out)

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
    
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name is required")
    if not hospital_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hospital ID is required")
    
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found")
    
    existing = db.query(Department).filter(
        Department.name == name,
        Department.hospital_id == hospital_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department already exists")
    
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
    """Update department details - Edit button"""
    department = db.query(Department).filter(Department.id == department_id).first()
    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    
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
    """Delete a department - Delete button"""
    department = db.query(Department).filter(Department.id == department_id).first()
    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    
    doctors_count = db.query(Doctor).filter(
        Doctor.specialization == department.name,
        Doctor.hospital_id == department.hospital_id
    ).count()
    
    if doctors_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete department. {doctors_count} doctor(s) are assigned"
        )
    
    db.delete(department)
    db.commit()
    
    logger.info(f"Admin {current_user.user_id} deleted department: {department_id}")
    
    return ok(message="Department deleted successfully")



@router.get("/{doctor_id}/details")
async def get_doctor_details_alias(
    doctor_id: str,
    db: Session = Depends(get_db)
):
    """Alias for get_doctor to support frontend /details suffix"""
    return await get_doctor(doctor_id, db)


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
            "department": merged.get("department") or merged.get("specialization"),
            "specialization": merged.get("specialization") or merged.get("department"),
            "updated_at": merged.get("updated_at"),
        }
    )
    
    # Update doctor in PostgreSQL
    for key, value in persist.items():
        if hasattr(doctor, key):
            setattr(doctor, key, value)
    
    db.commit()
    db.refresh(doctor)
    
    if not merged.get("id"):
        merged["id"] = doctor_id
    return ok(data=merged, message="Doctor updated")

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

@router.post("", dependencies=[Depends(require_roles("receptionist", "admin"))])
async def create_doctor(
    doctor: DoctorCreate,
    db: Session = Depends(get_db)
):
    """Create a new doctor (Receptionist/Admin).
    
    This also creates a corresponding User record for doctor portal login.
    """
    # 1. Check if user with this email already exists
    existing_user = db.query(User).filter(func.lower(User.email) == doctor.email.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email {doctor.email} already exists"
        )



    import uuid
    user_id = str(uuid.uuid4())
    doctor_id = str(uuid.uuid4())
    doctor_data = doctor.dict()
    
    try:
        # 3. Create User record for credentials
        new_user = User(
            id=user_id,
            name=doctor.name,
            email=doctor.email.lower(),
            phone=None,  # Phone no longer required for doctors during creation
            password_hash=get_password_hash(doctor.password),
            role="doctor",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(new_user)
        db.flush()  # Ensure User is persisted before creating Doctor (avoids FK violation)
    
        # Normalize schedule times to 24-hour HH:MM if provided (support AM/PM input from frontend)
        norm_start = _normalize_time_to_hhmm(doctor_data.get("start_time"))
        norm_end = _normalize_time_to_hhmm(doctor_data.get("end_time"))
        if norm_start:
            doctor_data["start_time"] = norm_start
        if norm_end:
            doctor_data["end_time"] = norm_end
        
        doctor_data["id"] = doctor_id
        doctor_data["user_id"] = user_id
        doctor_data["created_at"] = datetime.utcnow()
        doctor_data["updated_at"] = datetime.utcnow()

        # Keep Firestore documents compatible with both field names.
        # Your DB uses `department`, but much of the code historically uses `specialization`.
        doctor_data["department"] = doctor_data.get("specialization")

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
        valid_fields = {c.name for c in Doctor.__table__.columns}
        filtered_doctor_data = {k: v for k, v in doctor_data.items() if k in valid_fields}
        
        new_doctor = Doctor(**filtered_doctor_data)
        db.add(new_doctor)
        db.commit()
        db.refresh(new_doctor)
        
        # Map DB model to response dict, then to Pydantic for validation, then to dict for JSON serialization
        out_dict = {k: v for k, v in new_doctor.__dict__.items() if not k.startswith('_')}
        response_obj = DoctorResponse(**out_dict)
        
        from app.utils.responses import ok
        return ok(data=response_obj.model_dump(), message="Doctor created successfully with login credentials")
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Doctor creation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create doctor: {str(e)}"
        )


@router.get("/{doctor_id}/available-slots")
async def get_available_slots(
    doctor_id: str,
    day: str = Query(..., description="DD-MM-YYYY"),
    slot_minutes: int = Query(15, ge=5, le=60),
    db: Session = Depends(get_db)
):
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

    return ok(data={
        "doctor_id": doctor_id,
        "day": day,
        "slot_minutes": slot_minutes,
        "slots": out
    })

@router.get("/")
async def list_doctors(
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    specialization: Optional[str] = Query(None, description="Filter by specialization"),
    subcategory: Optional[str] = Query(None, description="Filter by subcategory"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List all doctors with optional filtering and standardized response format"""
    # Build query
    query = db.query(Doctor)
    
    # Apply hospital filter
    if hospital_id:
        query = query.filter(Doctor.hospital_id == hospital_id)
    
    # Fetch doctors (standard limit for base query)
    doctors = query.all()
    
    # Filter in Python for case-insensitive matching
    spec_norm = (specialization or "").strip().lower()
    sub_norm = (subcategory or "").strip().lower()
    
    results = []
    for d in doctors:
        d_dict = {k: v for k, v in d.__dict__.items() if not k.startswith('_')}
        
        # Apply normalization/department compatibility
        d_dict["department"] = d_dict.get("specialization")
        
        # Apply filters if provided
        if spec_norm:
            if spec_norm not in (d_dict.get("specialization") or "").lower() and \
               spec_norm not in (d_dict.get("department") or "").lower():
                continue
        if sub_norm:
            if sub_norm not in (d_dict.get("subcategory") or "").lower():
                continue
                
        results.append(d_dict)

    # Manual Pagination
    total = len(results)
    start = (page - 1) * limit
    end = start + limit
    paginated_results = results[start:end]

    return {
        "success": True,
        "data": paginated_results,
        "meta": {
            "total": total,
            "page": page,
            "page_size": limit
        }
    }

@router.get("/hospital/{hospital_id}")
async def get_doctors_by_hospital(
    hospital_id: str,
    category: Optional[str] = Query(None, description="Filter by main category or specialization (General Medical, Specialist, Surgeon, or specific)"),
    subcategory: Optional[str] = Query(None, description="Filter by subcategory"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Get doctors for a specific hospital with optional main category & subcategory filter.

    Behavior:
    - If `category` is one of the main categories (General Medical, Specialist, Surgeon), we map it to its subcategories
      and filter doctors whose `subcategory` is in that list (or whose `specialization` matches a subcategory term).
    - If `subcategory` is provided, it takes precedence and we filter by it exactly.
    - Response includes the resolved `subcategories` list for the given main category to drive the UI dropdown.
    """
    # Query doctors from PostgreSQL
    doctors = db.query(Doctor).filter(Doctor.hospital_id == hospital_id).limit(500).all()

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
                resolved_subcategories = list(subs)  # start with static
                break

    # Build dynamic subcategories present in data for this hospital
    if main_selected is not None:
        dyn_set = set(resolved_subcategories)
        general_set = set(main_category_map["General Medical"])  # for exclusions
        for d in doctors:
            data = {k: v for k, v in d.__dict__.items() if not k.startswith('_')}
            doctor_sub = (data.get("subcategory") or "").strip()
            doctor_spec = (data.get("specialization") or "").strip()
            low_sub = doctor_sub.lower()
            low_spec = doctor_spec.lower()

            if main_selected == "Surgeon":
                if "surgeon" in low_sub or "surgeon" in low_spec:
                    if doctor_sub:
                        dyn_set.add(doctor_sub)
                    if doctor_spec:
                        dyn_set.add(doctor_spec)
            elif main_selected == "General Medical":
                # include known general subs and specs matching them
                if doctor_sub in main_category_map["General Medical"]:
                    dyn_set.add(doctor_sub)
                if doctor_spec in main_category_map["General Medical"]:
                    dyn_set.add(doctor_spec)
            else:  # Specialist
                # exclude surgeon-like and general-medical-like terms
                if ("surgeon" not in low_sub and doctor_sub and doctor_sub not in general_set):
                    dyn_set.add(doctor_sub)
                if ("surgeon" not in low_spec and doctor_spec and doctor_spec not in general_set):
                    dyn_set.add(doctor_spec)

        resolved_subcategories = sorted({s for s in dyn_set if s})

    # Now filter results according to category/subcategory
    results = []
    # Normalize map for case-insensitive matching
    norm_map = {k: [s.lower() for s in v] for k, v in main_category_map.items()}

    for d in doctors:
        data = {k: v for k, v in d.__dict__.items() if not k.startswith('_')}
        doctor_sub = str(data.get("subcategory") or "").strip().lower()
        doctor_spec = str(data.get("specialization") or "").strip().lower()

        # If a concrete subcategory is given, match it exactly
        if subcategory:
            sub_target = subcategory.strip().lower()
            if doctor_sub == sub_target or doctor_spec == sub_target:
                results.append(data)
            continue

        # If main category selected -> inclusion rules
        if main_selected == "Surgeon":
            if "surgeon" in doctor_sub or "surgeon" in doctor_spec or (
                resolved_subcategories and any(s.lower() in [doctor_sub, doctor_spec] for s in resolved_subcategories)
            ):
                results.append(data)
            continue
        elif main_selected == "General Medical":
            if doctor_sub in norm_map["General Medical"] or doctor_spec in norm_map["General Medical"]:
                results.append(data)
            continue
        elif main_selected == "Specialist":
            # Specialist = not General Medical and not Surgeon
            is_general = doctor_sub in norm_map["General Medical"] or doctor_spec in norm_map["General Medical"]
            is_surgeon = "surgeon" in doctor_sub or "surgeon" in doctor_spec
            
            if not is_general and not is_surgeon:
                # If we built subcategories, prefer those; else include
                if not resolved_subcategories:
                    results.append(data)
                else:
                    if any(s.lower() in [doctor_sub, doctor_spec] for s in resolved_subcategories):
                        results.append(data)
            continue

        # If category provided but not a main category, treat it as a specialization filter
        if category and main_selected is None:
            cat_target = category.strip().lower()
            # Check for partial match in specialization or subcategory
            if cat_target in doctor_spec or cat_target in doctor_sub:
                results.append(data)
            continue

        # No category filters: include
        results.append(data)

    results = results[:limit]

    doctors_with_queue = []
    for doctor_data in results:
        # Add compatibility fields for frontend/Pydantic validation
        doctor_data["department"] = doctor_data.get("specialization")
        doctor_data["fee"] = doctor_data.get("consultation_fee")
        doctor_data["per_session_fee"] = doctor_data.get("session_fee")
        if "updated_at" not in doctor_data:
            doctor_data["updated_at"] = doctor_data.get("created_at")
        
        try:
            doctor = DoctorResponse(**doctor_data)
            queue = await get_doctor_queue(doctor_data["id"], db=db)
            doctors_with_queue.append(DoctorWithQueue(doctor=doctor, queue=queue))
        except Exception as e:
            logger.error(f"Error validating doctor {doctor_data.get('id')}: {e}")
            continue

    # Clean subcategories to avoid returning main labels and duplicates
    main_labels_norm = {k.strip().lower() for k in main_category_map.keys()}
    cleaned_subcats = sorted({
        s for s in (resolved_subcategories or [])
        if s and s.strip().lower() not in main_labels_norm
    }, key=lambda x: x.lower())

    # Build response using ok() for consistent structure
    return ok(data={
        "doctors": doctors_with_queue,
        "total_found": len(doctors_with_queue),
        "hospital_id": hospital_id,
        "category": category,
        "subcategories": cleaned_subcats
    })

@router.get("/search")
async def search_doctors(
    query: str = Query(..., min_length=0, description="Search query for doctor name or specialization"),
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    category: Optional[str] = Query(None, description="Filter by specialization category"),
    subcategory: Optional[str] = Query(None, description="Filter by subcategory"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Search doctors by name, specialization, or subcategory"""
    doctors = db.query(Doctor).limit(100).all()
    
    results = []
    
    # Get all doctors and filter in memory (simpler approach for small datasets)
    for doctor in doctors:
        doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
        
        # Apply hospital filter if specified
        if hospital_id and doctor_data.get("hospital_id") != hospital_id:
            continue
            
        # Apply category filter if specified
        if category and doctor_data.get("specialization", "").lower() != category.lower():
            continue

        # Apply subcategory filter if specified
        if subcategory and doctor_data.get("subcategory", "").lower() != subcategory.lower():
            continue
            
        # Check if query matches name, specialization, or subcategory
        matches = False
        
        if query.lower() in doctor_data.get("name", "").lower():
            matches = True
        if query.lower() in doctor_data.get("specialization", "").lower():
            matches = True
        if query.lower() in doctor_data.get("subcategory", "").lower():
            matches = True
            
        if matches:
            results.append(doctor_data)
            
        if len(results) >= limit:
            break
    
    # Prepare response with queue information
    doctors_with_queue = []
    for doctor_data in results[:limit]:
        # Add compatibility fields
        doctor_data["department"] = doctor_data.get("specialization")
        doctor_data["fee"] = doctor_data.get("consultation_fee")
        doctor_data["per_session_fee"] = doctor_data.get("session_fee")

        try:
            doctor = DoctorResponse(**doctor_data)
            queue = await get_doctor_queue(doctor_data["id"], db=db)
            
            doctors_with_queue.append(DoctorWithQueue(
                doctor=doctor,
                queue=queue
            ))
        except Exception as e:
            logger.error(f"Error validating doctor {doctor_data.get('id')}: {e}")
            continue
    
    return ok(data={
        "doctors": doctors_with_queue,
        "total_found": len(doctors_with_queue),
        "hospital_id": hospital_id or "",
        "category": category
    })

@router.get("/categories")
async def get_doctor_categories():
    """Get organized doctor categories with subcategories"""
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
    """Return subcategories for a selected main category."""
    try:
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
            return ok(data={"main_category": main_category, "subcategories": cleaned})

        # Dynamic list constrained to a specific hospital
        doctors = db.query(Doctor).filter(Doctor.hospital_id == hospital_id).all()

        dyn: set[str] = set()
        general_set = set(category_mappings["General Medical"])  # for exclusions
        for d in doctors:
            sub = str(getattr(d, "subcategory", "") or "").strip()
            spec = str(getattr(d, "specialization", "") or "").strip()
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
        return ok(data={"main_category": main_category, "hospital_id": hospital_id, "subcategories": cleaned})

    except Exception:
        return ok(data={"main_category": main_category, "subcategories": []})


@router.get("/categories/{main_category}/hospitals/{hospital_id}/subcategories")
async def get_hospital_category_subcategories(
    main_category: str,
    hospital_id: str,
    db: Session = Depends(get_db),
):
    """Get unique subcategories for a given category within a specific hospital."""
    try:
        # Normalize category
        norm_cat = str(main_category or "").strip().lower()
        
        # Get doctors for this category in this hospital
        from sqlalchemy import or_
        doctors = db.query(Doctor).filter(
            Doctor.hospital_id == hospital_id,
            func.lower(Doctor.specialization) == norm_cat
        ).all()
        
        subs = []
        for d in doctors:
            if getattr(d, "subcategory", None):
                subs.append(str(d.subcategory).strip())
        
        cleaned = sorted(list(set(c for c in subs if c)))
        return ok(data={"main_category": main_category, "hospital_id": hospital_id, "subcategories": cleaned})
    except Exception:
        return ok(data={"main_category": main_category, "hospital_id": hospital_id, "subcategories": []})


@router.get("/by-category/{main_category}")
async def get_doctors_by_main_category(
    main_category: str,
    hospital_id: Optional[str] = Query(None, description="Filter by hospital ID"),
    subcategory: Optional[str] = Query(None, description="Filter by subcategory"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Get doctors by main category (General Medical, Specialist, Surgeon) and optional subcategory"""

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
    
    subcategories = category_mappings[main_category]

    query = db.query(Doctor)
    if hospital_id:
        query = query.filter(Doctor.hospital_id == hospital_id)

    # Keep same behavior: scan up to 200, stop after limit matched
    doctors = query.limit(200).all()
    results: List[Doctor] = []

    for d in doctors:
        doctor_specialization = str(getattr(d, "specialization", "") or "")
        doctor_subcategory = str(getattr(d, "subcategory", "") or "")

        if subcategory:
            if doctor_subcategory.lower() == subcategory.lower() or doctor_specialization.lower() == subcategory.lower():
                results.append(d)
        else:
            if any(
                subcat.lower() == doctor_subcategory.lower() or subcat.lower() == doctor_specialization.lower()
                for subcat in subcategories
            ):
                results.append(d)

        if len(results) >= limit:
            break
    
    doctors_with_queue = []
    for d in results:
        doctor_data = {k: v for k, v in d.__dict__.items() if not k.startswith('_')}
        # Add compatibility fields
        doctor_data["department"] = doctor_data.get("specialization")
        doctor_data["fee"] = doctor_data.get("consultation_fee")
        doctor_data["per_session_fee"] = doctor_data.get("session_fee")

        try:
            doctor = DoctorResponse(**doctor_data)
            queue = await get_doctor_queue(str(getattr(d, "id", "")), db=db)
            
            doctors_with_queue.append(DoctorWithQueue(
                doctor=doctor,
                queue=queue
            ))
        except Exception as e:
            logger.error(f"Error validating doctor {doctor_data.get('id')}: {e}")
            continue
    
    # Clean subcategories to avoid returning main labels and duplicates
    main_labels_norm = { k.strip().lower() for k in category_mappings.keys() }
    cleaned_subcats = sorted({ s for s in subcategories if s and s.strip().lower() not in main_labels_norm }, key=lambda x: x.lower())

    return ok(data={
        "doctors": doctors_with_queue,
        "total_found": len(doctors_with_queue),
        "main_category": main_category,
        "subcategories": cleaned_subcats
    })

@router.get("/{doctor_id}")
async def get_doctor(doctor_id: str, db: Session = Depends(get_db)):
    """Get doctor by ID"""
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    doctor_data = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
    
    # Add compatibility fields for frontend
    doctor_data["department"] = doctor_data.get("specialization")
    doctor_data["fee"] = doctor_data.get("consultation_fee")
    doctor_data["per_session_fee"] = doctor_data.get("session_fee")
    
    return ok(data=DoctorResponse(**doctor_data))

@router.get("/{doctor_id}/availability")
async def get_doctor_availability(doctor_id: str, db: Session = Depends(get_db)):
    """Return a doctor's availability schedule for pre-booking display.

    Response includes: available_days, start_time, end_time, status.
    """
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )

    return ok(data={
        "doctor_id": doctor_id,
        "status": getattr(doctor, "status", None),
        "available_days": getattr(doctor, "available_days", None) or [],
        "start_time": getattr(doctor, "start_time", None),
        "end_time": getattr(doctor, "end_time", None),
    })

@router.get("/{doctor_id}/availability/today")
async def get_doctor_availability_today(doctor_id: str, db: Session = Depends(get_db)):
    """Return whether the doctor is available today and today's time window.

    Computes availability based on `available_days`, `start_time`, `end_time`, and `status`.
    """
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )

    status_val = str(getattr(doctor, "status", "") or "").lower()
    start_time = str(getattr(doctor, "start_time", "") or "").strip()
    end_time = str(getattr(doctor, "end_time", "") or "").strip()
    days = [str(x).strip().lower() for x in (getattr(doctor, "available_days", None) or [])]

    today_name = datetime.utcnow().strftime("%A").lower()
    available_today = (
        status_val not in {"offline", "on_leave"} and
        bool(start_time) and bool(end_time) and
        ((not days) or (today_name in days))
    )

    return ok(data={
        "doctor_id": doctor_id,
        "available_today": available_today,
        "today_window": f"{start_time}-{end_time}" if start_time and end_time else None,
        "status": getattr(doctor, "status", None),
        "available_days": getattr(doctor, "available_days", None) or [],
    })


@router.get("/{doctor_id}/queue")
async def get_doctor_queue_status(
    doctor_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Get current queue status for a doctor"""
    return await get_doctor_queue(doctor_id, db=db)


async def get_doctor_queue(doctor_id: str, db: Session = None) -> QueueStatus:
    """Get or create queue information for a doctor"""
    if db is None:
        db = next(get_db())

    from app.db_models import Token, Doctor
    from datetime import datetime, date
    from app.config import AVG_CONSULTATION_TIME_MINUTES

    # Get doctor's timezone/current date
    now = datetime.utcnow()
    today = now.date()

    # Query active tokens for this doctor today
    active_tokens = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        func.date(Token.appointment_date) == today,
        Token.status.in_(["pending", "confirmed", "waiting", "called", "in_consultation"])
    ).all()

    # Query completed tokens for this doctor today
    completed_count = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        func.date(Token.appointment_date) == today,
        Token.status == "completed"
    ).count()

    waiting_patients = [t for t in active_tokens if t.status in ("pending", "confirmed", "waiting")]
    in_consultation = [t for t in active_tokens if t.status in ("called", "in_consultation")]

    # Sort waiting patients by token number
    waiting_patients.sort(key=lambda x: x.token_number)
    
    # Get currently serving token number
    current_token_num = None
    if in_consultation:
        # If multiple, the one with the highest token number is likely the latest called
        in_consultation.sort(key=lambda x: x.token_number, reverse=True)
        current_token_num = in_consultation[0].token_number

    # Calculate estimated wait time
    # Formula: waiting_patients * AVG_CONSULTATION_TIME
    # If no one is waiting, wait time is 0
    avg_time = int(AVG_CONSULTATION_TIME_MINUTES or 5)
    estimated_wait = len(waiting_patients) * avg_time

    return QueueStatus(
        doctor_id=doctor_id,
        current_token=current_token_num,
        pending_patients=len(waiting_patients),
        in_progress_patients=len(in_consultation),
        completed_patients=completed_count,
        estimated_wait_time=estimated_wait,
        total_queue=len(active_tokens),
        total_patients=len(active_tokens)
    )

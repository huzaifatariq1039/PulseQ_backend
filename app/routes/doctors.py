from fastapi import APIRouter, HTTPException, status, Query, Depends
from typing import List, Optional, Dict, Any
from app.models import DoctorCreate, DoctorResponse, DoctorSearchResponse, DoctorWithQueue, QueueStatus
from app.database import get_db, get_db_session
from sqlalchemy.orm import Session
from app.db_models import Doctor, Hospital, User, Queue as DBQueue, Department, Token, Refund
from app.security import get_current_active_user, require_roles, get_password_hash
from app.utils.responses import ok
from datetime import datetime, timezone
import random
import logging
from app.services.cache_service import CacheService, cached
 
# FIX 4: Split into two routers — public (read-only) and staff (write + auth-gated)
# main.py mounts:
#   public_router -> /api/v1/public/doctors
#   router        -> /api/v1/staff/doctors  AND  /api/v1/doctors
public_router = APIRouter(tags=["Public Discovery - Doctors"])
router = APIRouter(tags=["Staff Portal - Doctor Management"])
 
logger = logging.getLogger("performance.doctors")
 
 
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
 
def _is_doctor_available_today(doctor: Doctor) -> bool:
    try:
        status_val = str(doctor.status or "").lower()
        if status_val in {"offline", "on_leave"}:
            return False
        if not doctor.start_time or not doctor.end_time:
            return False
        if doctor.available_days:
            now_utc = datetime.now(timezone.utc)
            today_name = now_utc.strftime("%A").lower()
            available_days_lower = [str(d).strip().lower() for d in doctor.available_days]
            if available_days_lower and today_name not in available_days_lower:
                return False
        now_utc = datetime.now(timezone.utc)
        current_time_str = now_utc.strftime("%H:%M")
 
        def parse_time(time_str: str) -> Optional[str]:
            if not time_str:
                return None
            s = str(time_str).strip().lower()
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
        return start_time <= current_time_str <= end_time
    except Exception as e:
        logger.error(f"Error checking doctor availability: {e}")
        return False
 
 
def batch_fetch_queues(doctor_ids: List[str], db: Session) -> Dict[str, DBQueue]:
    if not doctor_ids:
        return {}
    queues = db.query(DBQueue).filter(DBQueue.doctor_id.in_(doctor_ids)).all()
    return {q.doctor_id: q for q in queues}
 
 
def build_queue_status(doctor_id: str, queue_obj: Optional[DBQueue]) -> QueueStatus:
    if queue_obj:
        return QueueStatus(
            doctor_id=doctor_id,
            current_token=int(getattr(queue_obj, "current_token", 0) or 0),
            waiting_patients=int(getattr(queue_obj, "waiting_patients", 0) or 0),
            estimated_wait_time_minutes=int(getattr(queue_obj, "estimated_wait_time_minutes", 0) or 0),
        )
    waiting_patients = random.randint(5, 25)
    return QueueStatus(
        doctor_id=doctor_id,
        current_token=random.randint(1, 10),
        waiting_patients=waiting_patients,
        estimated_wait_time_minutes=waiting_patients * 3,
    )
 
 
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
 
 
def _normalize_time_to_hhmm(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    val = str(s).strip()
    if not val:
        return None
    low = val.lower()
    try:
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
        parts = val.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            h = int(parts[0])
            mm = int(parts[1])
            if 0 <= h <= 23 and 0 <= mm <= 59:
                return f"{h:02d}:{mm:02d}"
            return None
        if val.isdigit():
            h = int(val)
            if 0 <= h <= 23:
                return f"{h:02d}:00"
            return None
        return None
    except Exception:
        return None
 
 
# ---------------------------------------------------------------------------
# FIX 3: Static/specific routes FIRST, dynamic /{doctor_id} routes LAST
# ---------------------------------------------------------------------------
 
# ==================== STAFF-ONLY ENDPOINTS (router) ====================
 
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
    hospital_id: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    query = db.query(Doctor)
    if hospital_id:
        query = query.filter(Doctor.hospital_id == hospital_id)
    if department:
        dep = str(department).strip()
        if dep:
            query = query.filter(Doctor.specialization.ilike(f"%{dep}%"))
    if search:
        s = str(search).strip()
        if s:
            query = query.filter(Doctor.name.ilike(f"%{s}%"))
 
    total = query.count()
    doctors = (
        query.order_by(Doctor.updated_at.desc(), Doctor.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
 
    out: List[Dict[str, Any]] = []
    for doctor in doctors:
        it = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
        start_fmt = _fmt_time_12h(it.get("start_time"))
        end_fmt = _fmt_time_12h(it.get("end_time"))
        timings = f"{start_fmt} - {end_fmt}" if start_fmt and end_fmt else None
        dept = it.get("specialization")
        fee_val = it.get("consultation_fee")
        out.append({
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
        })
 
    return {"success": True, "data": out, "meta": {"page": page, "page_size": page_size, "total": total}}
 
 
@router.get("/departments", dependencies=[Depends(require_roles("receptionist", "admin", "patient"))])
async def receptionist_list_departments(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
    hospital_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    query = db.query(Doctor)
    if hospital_id:
        query = query.filter(Doctor.hospital_id == hospital_id)
    doctors = query.all()
    names = [str(d.specialization or "").strip() for d in doctors if d.specialization]
    out = sorted(set(names), key=lambda x: x.lower())
    return {"success": True, "data": out}
 
 
# ==================== DEPARTMENT MANAGEMENT (Admin) ====================
 
@router.post("/departments", dependencies=[Depends(require_roles("admin"))])
async def create_department(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> Dict[str, Any]:
    import uuid
    name = str(payload.get("name") or "").strip()
    hospital_id = str(payload.get("hospital_id") or "").strip()
    description = str(payload.get("description") or "").strip()
 
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name is required")
    if not hospital_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hospital ID is required")
 
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found")
 
    existing = db.query(Department).filter(
        Department.name == name, Department.hospital_id == hospital_id
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department already exists")
 
    new_department = Department(
        id=str(uuid.uuid4()),
        name=name,
        hospital_id=hospital_id,
        created_at=datetime.utcnow(),
    )
    db.add(new_department)
    db.commit()
    db.refresh(new_department)
    logger.info(f"Admin {current_user.user_id} created department: {name}")
    return ok(
        data={"id": new_department.id, "name": new_department.name,
              "hospital_id": new_department.hospital_id, "created_at": new_department.created_at},
        message="Department created successfully",
    )
 
 
@router.get("/departments/list", dependencies=[Depends(require_roles("admin", "receptionist"))])
async def get_departments_list(
    db: Session = Depends(get_db),
    hospital_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    query = db.query(Department)
    if hospital_id:
        query = query.filter(Department.hospital_id == hospital_id)
    departments = query.order_by(Department.name.asc()).all()
    return ok(data=[
        {"id": d.id, "name": d.name, "hospital_id": d.hospital_id, "created_at": d.created_at}
        for d in departments
    ])
 
 
@router.put("/departments/{department_id}", dependencies=[Depends(require_roles("admin"))])
@router.patch("/departments/{department_id}", dependencies=[Depends(require_roles("admin"))])
async def update_department(
    department_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> Dict[str, Any]:
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
        data={"id": department.id, "name": department.name,
              "hospital_id": department.hospital_id, "created_at": department.created_at},
        message="Department updated successfully",
    )
 
 
@router.delete("/departments/{department_id}", dependencies=[Depends(require_roles("admin"))])
async def delete_department(
    department_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> Dict[str, Any]:
    department = db.query(Department).filter(Department.id == department_id).first()
    if not department:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
 
    doctors_count = db.query(Doctor).filter(
        Doctor.specialization == department.name,
        Doctor.hospital_id == department.hospital_id,
    ).count()
    if doctors_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete department. {doctors_count} doctor(s) are assigned to this department",
        )
 
    db.delete(department)
    db.commit()
    logger.info(f"Admin {current_user.user_id} deleted department: {department_id}")
    return ok(message="Department deleted successfully")
 
 
# FIX 5: Added auth guard — previously anyone could create a doctor
@router.post("/", response_model=DoctorResponse, dependencies=[Depends(require_roles("admin", "receptionist"))])
async def create_doctor(
    doctor: DoctorCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    existing_doctor = db.query(Doctor).filter(
        Doctor.name == doctor.name, Doctor.hospital_id == doctor.hospital_id
    ).first()
    if existing_doctor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doctor with this name already exists in this hospital",
        )
 
    import uuid
    doctor_data = doctor.dict()
        
    # Extract password before processing (it's for User account, not Doctor model)
    doctor_password = doctor_data.pop("password", None)
    
    norm_start = _normalize_time_to_hhmm(doctor_data.get("start_time"))
    norm_end = _normalize_time_to_hhmm(doctor_data.get("end_time"))
    if norm_start:
        doctor_data["start_time"] = norm_start
    if norm_end:
        doctor_data["end_time"] = norm_end
 
    doctor_data["id"] = str(uuid.uuid4())
    doctor_data["created_at"] = datetime.utcnow()
    doctor_data["updated_at"] = datetime.utcnow()
    
    # Handle department/specialization alias
    if "department" in doctor_data and "specialization" not in doctor_data:
        doctor_data["specialization"] = doctor_data["department"]
    doctor_data.pop("department", None)
    
    # Handle fee/consultation_fee alias (frontend may send 'fee')
    if "fee" in doctor_data:
        if "consultation_fee" not in doctor_data or doctor_data["consultation_fee"] is None:
            doctor_data["consultation_fee"] = doctor_data["fee"]
        doctor_data.pop("fee", None)
    
    # Remove frontend-only fields that don't exist in DB model
    doctor_data.pop("per_session_fee", None)  # 'per_session_fee' is alias for 'session_fee'
    
    dept_text = (
        f"{doctor_data.get('specialization') or ''} "
        f"{doctor_data.get('subcategory') or ''}"
    ).lower().strip()
    
    # Check if department supports session-based pricing
    # NOTE: This is optional - doctors in these departments MAY have session_fee, but it's not required
    inferred_has_session = any(
        kw in dept_text for kw in ("psychology", "psychiatry", "physiotherapist", "physiotherapy", "physio")
    )
    
    if inferred_has_session:
        # Session-based departments: session_fee is OPTIONAL
        # If provided, must be > 0. If not provided or 0, doctor uses standard consultation_fee
        try:
            session_fee_val = float(doctor_data.get("session_fee") or 0)
        except Exception:
            session_fee_val = 0
        
        if session_fee_val > 0:
            # Doctor charges per session
            doctor_data["has_session"] = True
            doctor_data["pricing_type"] = "session_based"
            doctor_data["session_fee"] = session_fee_val
        else:
            # Doctor uses standard consultation fee (no session pricing)
            doctor_data["has_session"] = False
            doctor_data["pricing_type"] = "standard"
            doctor_data["session_fee"] = None
    else:
        # Non-session departments: always standard pricing
        doctor_data["has_session"] = False
        doctor_data["pricing_type"] = "standard"
        doctor_data["session_fee"] = None
 
    if not doctor_data.get("avatar_initials"):
        name_parts = doctor.name.split()
        if len(name_parts) >= 2:
            doctor_data["avatar_initials"] = f"{name_parts[0][0]}{name_parts[1][0]}".upper()
        else:
            doctor_data["avatar_initials"] = doctor.name[:2].upper()
    
    # Create User account for the doctor if email and password are provided
    user_id = None
    if doctor.email and doctor_password:
        # Validate hospital_id before creating user
        if not doctor.hospital_id or doctor.hospital_id.strip() == "":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="hospital_id is required and cannot be empty",
            )
        
        # Check if hospital exists
        hospital = db.query(Hospital).filter(Hospital.id == doctor.hospital_id).first()
        if not hospital:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Hospital with id '{doctor.hospital_id}' not found",
            )
        
        # Check if user with this email already exists
        existing_user = db.query(User).filter(User.email == doctor.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with email {doctor.email} already exists",
            )
            
        # Create User account
        user_id = str(uuid.uuid4())
        new_user = User(
            id=user_id,
            name=doctor.name,
            email=doctor.email,
            password_hash=get_password_hash(doctor_password),
            role="doctor",
            hospital_id=doctor.hospital_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(new_user)
        db.flush()  # Flush to get the user_id without committing
        logger.info(f"Created user account for doctor: {doctor.email}")
    
    # Create Doctor record
    # Validate hospital_id for doctor record
    if not doctor_data.get("hospital_id") or doctor_data["hospital_id"].strip() == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="hospital_id is required for doctor",
        )
    
    doctor_data["user_id"] = user_id  # Link to User account
        
    new_doctor = Doctor(**doctor_data)
    db.add(new_doctor)
    db.commit()
    db.refresh(new_doctor)
        
    logger.info(f"Admin {current_user.user_id} created doctor: {doctor.name} (user_id={user_id})")
    return DoctorResponse(**doctor_data)
 
 
# ==================== PUBLIC ENDPOINTS (public_router) ====================
# FIX 3: Static paths before dynamic /{doctor_id} — on BOTH routers
 
@public_router.get("/", response_model=List[DoctorResponse])
async def list_doctors_public(
    hospital_id: Optional[str] = Query(None),
    specialization: Optional[str] = Query(None),
    subcategory: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Doctor)
    if hospital_id:
        query = query.filter(Doctor.hospital_id == hospital_id)
    if specialization:
        spec_norm = f"%{specialization.strip()}%"
        query = query.filter(
            Doctor.specialization.ilike(spec_norm) | Doctor.subcategory.ilike(spec_norm)
        )
    if subcategory:
        sub_norm = f"%{subcategory.strip()}%"
        query = query.filter(
            Doctor.subcategory.ilike(sub_norm) | Doctor.specialization.ilike(sub_norm)
        )
    doctors = query.order_by(Doctor.created_at.desc()).limit(limit).all()
    results = []
    for doctor in doctors:
        results.append(DoctorResponse(
            id=doctor.id, name=doctor.name, specialization=doctor.specialization,
            subcategory=doctor.subcategory, hospital_id=doctor.hospital_id,
            consultation_fee=doctor.consultation_fee, session_fee=doctor.session_fee,
            status=doctor.status, available_days=doctor.available_days or [],
            start_time=doctor.start_time, end_time=doctor.end_time,
            avatar_initials=doctor.avatar_initials, rating=doctor.rating,
            review_count=doctor.review_count, created_at=doctor.created_at,
            updated_at=doctor.updated_at,
        ))
    return results


@router.get("/", response_model=List[DoctorResponse])
async def list_doctors_staff(
    hospital_id: Optional[str] = Query(None),
    specialization: Optional[str] = Query(None),
    subcategory: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return await list_doctors_public(
        hospital_id=hospital_id,
        specialization=specialization,
        subcategory=subcategory,
        limit=limit,
        db=db,
    )
 
 
@public_router.get("/categories")
@router.get("/categories")
@cached(ttl=CacheService.TTL_VERY_LONG)
async def get_doctor_categories():
    return {
        "General Medical": ["General Medicine", "Family Medicine", "Internal Medicine", "Emergency Medicine"],
        "Specialist": [
            "Cardiology", "Neurology", "Dermatology", "Pediatrics", "Psychiatry",
            "Radiology", "Pathology", "Anesthesiology", "Oncology", "Endocrinology",
            "Gastroenterology", "Pulmonology", "Nephrology", "Rheumatology",
            "Ophthalmology", "ENT", "Gynecology", "Urology",
        ],
        "Surgeon": [
            "General Surgery", "Cardiac Surgery", "Heart Surgeon", "Neuro Surgeon",
            "Ortho Surgeon", "Plastic Surgery", "Vascular Surgery", "Thoracic Surgery",
            "Pediatric Surgery", "Trauma Surgery", "Transplant Surgery",
            "Laparoscopic Surgery", "Reconstructive Surgery",
        ],
    }
 
 
@public_router.get("/subcategories")
@router.get("/subcategories")
async def get_subcategories(
    main_category: str = Query(...),
    hospital_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    category_mappings = {
        "General Medical": ["General Medicine", "Family Medicine", "Internal Medicine", "Emergency Medicine"],
        "Specialist": [
            "Cardiology", "Neurology", "Dermatology", "Pediatrics", "Psychiatry",
            "Radiology", "Pathology", "Anesthesiology", "Oncology", "Endocrinology",
            "Gastroenterology", "Pulmonology", "Nephrology", "Rheumatology",
            "Ophthalmology", "ENT", "Gynecology", "Urology",
        ],
        "Surgeon": [
            "General Surgery", "Cardiac Surgery", "Heart Surgeon", "Neuro Surgeon",
            "Ortho Surgeon", "Plastic Surgery", "Vascular Surgery", "Thoracic Surgery",
            "Pediatric Surgery", "Trauma Surgery", "Transplant Surgery",
            "Laparoscopic Surgery", "Reconstructive Surgery", "Surgeon",
        ],
    }
    if main_category not in category_mappings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {list(category_mappings.keys())}",
        )
    main_labels_norm = {k.strip().lower() for k in category_mappings.keys()}
    if not hospital_id:
        cleaned = sorted(
            {s for s in category_mappings[main_category] if s and s.strip().lower() not in main_labels_norm},
            key=lambda x: x.lower(),
        )
        return {"main_category": main_category, "subcategories": cleaned}
 
    doctors = db.query(Doctor).filter(Doctor.hospital_id == hospital_id).all()
    dyn: set[str] = set()
    general_set = set(category_mappings["General Medical"])
    for doctor in doctors:
        sub = (doctor.subcategory or "").strip()
        spec = (doctor.specialization or "").strip()
        low_sub, low_spec = sub.lower(), spec.lower()
        if main_category == "Surgeon":
            if "surgeon" in low_sub or "surgeon" in low_spec:
                if sub: dyn.add(sub)
                if spec: dyn.add(spec)
        elif main_category == "General Medical":
            if sub in category_mappings["General Medical"]: dyn.add(sub)
            if spec in category_mappings["General Medical"]: dyn.add(spec)
        else:
            if "surgeon" not in low_sub and sub and sub not in general_set: dyn.add(sub)
            if "surgeon" not in low_spec and spec and spec not in general_set: dyn.add(spec)
 
    cleaned = sorted({s for s in dyn if s and s.strip().lower() not in main_labels_norm}, key=lambda x: x.lower())
    return {"main_category": main_category, "hospital_id": hospital_id, "subcategories": cleaned}
 
 
@public_router.get("/search", response_model=DoctorSearchResponse)
@router.get("/search", response_model=DoctorSearchResponse)
async def search_doctors(
    query: str = Query(..., min_length=0),
    hospital_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    subcategory: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    query_obj = db.query(Doctor)
    if hospital_id:
        query_obj = query_obj.filter(Doctor.hospital_id == hospital_id)
    if query:
        search_pattern = f"%{query.strip()}%"
        query_obj = query_obj.filter(
            Doctor.name.ilike(search_pattern)
            | Doctor.specialization.ilike(search_pattern)
            | Doctor.subcategory.ilike(search_pattern)
        )
    if category:
        query_obj = query_obj.filter(
            Doctor.specialization.ilike(f"%{category.strip()}%")
            | Doctor.subcategory.ilike(f"%{category.strip()}%")
        )
    if subcategory:
        query_obj = query_obj.filter(
            Doctor.subcategory.ilike(f"%{subcategory.strip()}%")
            | Doctor.specialization.ilike(f"%{subcategory.strip()}%")
        )
    doctors = query_obj.order_by(Doctor.name).limit(limit).all()
    doctor_ids = [d.id for d in doctors]
    queues_map = batch_fetch_queues(doctor_ids, db)
    doctors_with_queue = []
    for doctor in doctors:
        doctor_data = _doctor_to_dict(doctor)
        doctor_response = DoctorResponse(**doctor_data)
        queue = build_queue_status(doctor.id, queues_map.get(doctor.id))
        doctors_with_queue.append(DoctorWithQueue(doctor=doctor_response, queue=queue))
    return DoctorSearchResponse(
        doctors=doctors_with_queue,
        total_found=len(doctors_with_queue),
        hospital_id=hospital_id or "",
        category=category,
    )
 
 
@public_router.get("/hospital/{hospital_id}", response_model=DoctorSearchResponse)
@router.get("/hospital/{hospital_id}", response_model=DoctorSearchResponse)
async def get_doctors_by_hospital(
    hospital_id: str,
    category: Optional[str] = Query(None),
    subcategory: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    doctors = db.query(Doctor).filter(Doctor.hospital_id == hospital_id).limit(200).all()
    main_category_map = {
        "General Medical": ["General Medicine", "Family Medicine", "Internal Medicine", "Emergency Medicine"],
        "Specialist": [
            "Cardiology", "Neurology", "Dermatology", "Pediatrics", "Psychiatry",
            "Radiology", "Pathology", "Anesthesiology", "Oncology", "Endocrinology",
            "Gastroenterology", "Pulmonology", "Nephrology", "Rheumatology",
            "Ophthalmology", "ENT", "Gynecology", "Urology",
        ],
        "Surgeon": [
            "General Surgery", "Cardiac Surgery", "Heart Surgeon", "Neuro Surgeon",
            "Ortho Surgeon", "Plastic Surgery", "Vascular Surgery", "Thoracic Surgery",
            "Pediatric Surgery", "Trauma Surgery", "Transplant Surgery",
            "Laparoscopic Surgery", "Reconstructive Surgery", "Surgeon",
        ],
    }
    resolved_subcategories: Optional[List[str]] = None
    main_selected = None
    if category:
        for key, subs in main_category_map.items():
            if category.strip().lower() == key.lower():
                main_selected = key
                resolved_subcategories = list(subs)
                break
 
    filtered_doctors = []
    for doctor in doctors:
        doctor_sub = (doctor.subcategory or "").strip()
        doctor_spec = (doctor.specialization or "").strip()
        if subcategory:
            if doctor_sub.lower() == subcategory.strip().lower() or doctor_spec.lower() == subcategory.strip().lower():
                filtered_doctors.append(doctor)
            continue
        if main_selected == "Surgeon":
            if "surgeon" in doctor_sub.lower() or "surgeon" in doctor_spec.lower() or (
                resolved_subcategories and (doctor_sub in resolved_subcategories or doctor_spec in resolved_subcategories)
            ):
                filtered_doctors.append(doctor)
            continue
        elif main_selected == "General Medical":
            if doctor_sub in main_category_map["General Medical"] or doctor_spec in main_category_map["General Medical"]:
                filtered_doctors.append(doctor)
            continue
        elif main_selected == "Specialist":
            if (
                "surgeon" not in doctor_sub.lower()
                and "surgeon" not in doctor_spec.lower()
                and doctor_sub not in main_category_map["General Medical"]
                and doctor_spec not in main_category_map["General Medical"]
            ):
                if not resolved_subcategories or doctor_sub in resolved_subcategories or doctor_spec in resolved_subcategories:
                    filtered_doctors.append(doctor)
            continue
        if category and main_selected is None:
            if doctor_spec.lower() == category.strip().lower() or doctor_sub.lower() == category.strip().lower():
                filtered_doctors.append(doctor)
            continue
        filtered_doctors.append(doctor)
 
    filtered_doctors = filtered_doctors[:limit]
    doctor_ids = [d.id for d in filtered_doctors]
    queues_map = batch_fetch_queues(doctor_ids, db)
    doctors_with_queue = []
    for doctor in filtered_doctors:
        doctor_response = DoctorResponse(**_doctor_to_dict(doctor))
        queue = build_queue_status(doctor.id, queues_map.get(doctor.id))
        doctors_with_queue.append(DoctorWithQueue(doctor=doctor_response, queue=queue))
 
    main_labels_norm = {k.strip().lower() for k in main_category_map.keys()}
    cleaned_subcats = sorted(
        {s for s in (resolved_subcategories or []) if s and s.strip().lower() not in main_labels_norm},
        key=lambda x: x.lower(),
    )
    return {"doctors": doctors_with_queue, "total_found": len(doctors_with_queue),
            "hospital_id": hospital_id, "category": category, "subcategories": cleaned_subcats}
 
 
@public_router.get("/by-category/{main_category}")
@router.get("/by-category/{main_category}")
async def get_doctors_by_main_category(
    main_category: str,
    hospital_id: Optional[str] = Query(None),
    subcategory: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    available_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    category_mappings = {
        "General Medical": ["General Medicine", "Family Medicine", "Internal Medicine", "Emergency Medicine"],
        "Specialist": [
            "Cardiology", "Neurology", "Dermatology", "Pediatrics", "Psychiatry",
            "Radiology", "Pathology", "Anesthesiology", "Oncology", "Endocrinology",
            "Gastroenterology", "Pulmonology", "Nephrology", "Rheumatology",
            "Ophthalmology", "ENT", "Gynecology", "Urology",
        ],
        "Surgeon": [
            "General Surgery", "Cardiac Surgery", "Heart Surgeon", "Neuro Surgeon",
            "Ortho Surgeon", "Plastic Surgery", "Vascular Surgery", "Thoracic Surgery",
            "Pediatric Surgery", "Trauma Surgery", "Transplant Surgery",
            "Laparoscopic Surgery", "Reconstructive Surgery", "Surgeon",
        ],
    }
    if main_category not in category_mappings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {list(category_mappings.keys())}",
        )
    query_obj = db.query(Doctor)
    if hospital_id:
        query_obj = query_obj.filter(Doctor.hospital_id == hospital_id)
    doctors = query_obj.limit(200).all()
    subcategories = category_mappings[main_category]
    results = []
    for doctor in doctors:
        doctor_specialization = doctor.specialization or ""
        doctor_subcategory = doctor.subcategory or ""
        if subcategory:
            if doctor_subcategory.lower() == subcategory.lower() or doctor_specialization.lower() == subcategory.lower():
                if available_only and not _is_doctor_available_today(doctor):
                    continue
                results.append(doctor)
        else:
            if any(
                subcat.lower() == doctor_subcategory.lower() or subcat.lower() == doctor_specialization.lower()
                for subcat in subcategories
            ):
                if available_only and not _is_doctor_available_today(doctor):
                    continue
                results.append(doctor)
        if len(results) >= limit:
            break
 
    doctor_ids = [d.id for d in results]
    queues_map = batch_fetch_queues(doctor_ids, db)
    doctors_with_queue = []
    for doctor in results:
        doctor_response = DoctorResponse(**_doctor_to_dict(doctor))
        queue = build_queue_status(doctor.id, queues_map.get(doctor.id))
        doctors_with_queue.append(DoctorWithQueue(doctor=doctor_response, queue=queue))
 
    main_labels_norm = {k.strip().lower() for k in category_mappings.keys()}
    cleaned_subcats = sorted(
        {s for s in subcategories if s and s.strip().lower() not in main_labels_norm},
        key=lambda x: x.lower(),
    )
    return {"doctors": doctors_with_queue, "total_found": len(doctors_with_queue),
            "main_category": main_category, "subcategories": cleaned_subcats}
 
 
# ==================== DYNAMIC /{doctor_id} ROUTES — ALWAYS LAST ====================
# FIX 3: These must come after all static paths or FastAPI will match e.g.
#         GET /search → doctor_id="search" instead of the search endpoint.
 
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
        "name", "department", "specialization", "subcategory", "phone", "email",
        "experience_years", "fee", "consultation_fee", "session_fee", "available_days",
        "start_time", "end_time", "room", "room_number", "qualifications",
        "qualification", "degrees", "patients_per_day", "status",
    }
    update: Dict[str, Any] = {k: v for k, v in (payload or {}).items() if k in allowed}
 
    if "fee" in update and "consultation_fee" not in update:
        update["consultation_fee"] = update.get("fee")
    update.pop("fee", None)
 
    for field in ("start_time", "end_time"):
        if field in update:
            norm = _normalize_time_to_hhmm(update.get(field))
            if update.get(field) and not norm:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field} is invalid")
            if norm:
                update[field] = norm
 
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
    persist.update({
        "has_session": merged.get("has_session"),
        "session_fee": merged.get("session_fee"),
        "pricing_type": merged.get("pricing_type"),
        "specialization": merged.get("specialization") or merged.get("department"),
        "updated_at": merged.get("updated_at"),
    })
    for field in ("department", "room", "qualifications", "qualification", "degrees", "experience_years", "phone", "email"):
        persist.pop(field, None)
 
    for key, value in persist.items():
        if hasattr(doctor, key):
            setattr(doctor, key, value)
 
    db.commit()
    db.refresh(doctor)
    if not merged.get("id"):
        merged["id"] = doctor_id
    return {"success": True, "data": merged, "message": "Doctor updated"}
 
 
# FIX 4: delete_doctor now only on `router` (staff), not on public_router
@router.delete("/{doctor_id}", dependencies=[Depends(require_roles("admin", "receptionist"))])
async def delete_doctor(
    doctor_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
) -> Dict[str, Any]:
    try:
        doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
        if not doctor:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
 
        active_tokens = db.query(Token).filter(
            Token.doctor_id == doctor_id,
            Token.status.in_(["pending", "waiting", "confirmed", "called", "in_consultation"]),
        ).count()
        if active_tokens > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete doctor. They have {active_tokens} active token(s). Please cancel or complete them first.",
            )
 
        doctor_name = doctor.name
        doctor_specialization = doctor.specialization
        token_ids = [t[0] for t in db.query(Token.id).filter(Token.doctor_id == doctor_id).all()]
 
        refunds_deleted_count = 0
        tokens_deleted_count = 0
        if token_ids:
            refunds_deleted_count = db.query(Refund).filter(Refund.token_id.in_(token_ids)).delete(synchronize_session=False)
            db.flush()
            tokens_deleted_count = db.query(Token).filter(Token.doctor_id == doctor_id).delete(synchronize_session=False)
            db.flush()
 
        db.delete(doctor)
        db.commit()
        logger.info(f"User {current_user.user_id} deleted doctor: {doctor_id} ({doctor_name}) - {tokens_deleted_count} tokens, {refunds_deleted_count} refunds deleted")
 
        return {
            "success": True,
            "message": f"Doctor {doctor_name} ({doctor_specialization}) has been deleted successfully",
            "deleted_doctor_id": doctor_id,
            "deleted_doctor_name": doctor_name,
            "deleted_tokens_count": tokens_deleted_count,
            "deleted_refunds_count": refunds_deleted_count,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting doctor {doctor_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete doctor: {str(e)}")
 
 
@public_router.get("/{doctor_id}/details")
@router.get("/{doctor_id}/details")
async def get_doctor_details(doctor_id: str, db: Session = Depends(get_db)):
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    return {
        "id": doctor.id, "name": doctor.name, "specialization": doctor.specialization,
        "subcategory": doctor.subcategory, "hospital_id": doctor.hospital_id,
        "consultation_fee": doctor.consultation_fee, "session_fee": doctor.session_fee,
        "status": doctor.status, "department": doctor.specialization,
        "available_days": doctor.available_days or [], "start_time": doctor.start_time,
        "end_time": doctor.end_time, "avatar_initials": doctor.avatar_initials,
        "rating": doctor.rating, "review_count": doctor.review_count,
        "email": doctor.email if hasattr(doctor, 'email') else None,
        "created_at": doctor.created_at, "updated_at": doctor.updated_at,
        "qualifications": doctor.qualifications if hasattr(doctor, 'qualifications') else None,
        "experience": doctor.experience_years if hasattr(doctor, 'experience_years') else None,
        "languages": doctor.languages if hasattr(doctor, 'languages') else [],
        "about": doctor.about if hasattr(doctor, 'about') else None,
        "room_number": doctor.room_number if hasattr(doctor, 'room_number') else None,
    }
 
 
@public_router.get("/{doctor_id}/available-slots")
@router.get("/{doctor_id}/available-slots")
async def get_available_slots(
    doctor_id: str,
    day: str = Query(..., description="DD-MM-YYYY"),
    slot_minutes: int = Query(15, ge=5, le=60),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    doc = {k: v for k, v in doctor.__dict__.items() if not k.startswith('_')}
    status_val = str(doc.get("status") or "").lower()
    if status_val in {"offline", "on_leave"} or bool(doc.get("queue_paused")) or bool(doc.get("paused")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor unavailable")
    from app.services.slot_booking_service import _parse_day_dd_mm_yyyy, generate_slots_for_doctor
    d = _parse_day_dd_mm_yyyy(day)
    slots = generate_slots_for_doctor(doc, d, slot_minutes=slot_minutes)
    out = [{"time": s.get("time"), "available": True} for s in slots]
    return {"doctor_id": doctor_id, "day": day, "slot_minutes": slot_minutes, "slots": out}
 
 
@public_router.get("/{doctor_id}/queue", response_model=QueueStatus)
@router.get("/{doctor_id}/queue", response_model=QueueStatus)
async def get_doctor_queue_status(doctor_id: str, db: Session = Depends(get_db)):
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    queue = db.query(DBQueue).filter(DBQueue.doctor_id == doctor_id).first()
    if queue:
        return QueueStatus(
            doctor_id=doctor_id,
            current_token=int(getattr(queue, "current_token", 0) or 0),
            pending_patients=int(getattr(queue, "waiting_patients", 0) or 0),
            in_progress_patients=0, completed_patients=0,
            estimated_wait_time=int(getattr(queue, "estimated_wait_time_minutes", 0) or 0),
            people_ahead=int(getattr(queue, "waiting_patients", 0) or 0),
            total_queue=int(getattr(queue, "waiting_patients", 0) or 0),
            total_patients=int(getattr(queue, "waiting_patients", 0) or 0),
        )
    pending_tokens = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status.in_(["pending", "waiting", "confirmed"]),
    ).count()
    in_progress_tokens = db.query(Token).filter(
        Token.doctor_id == doctor_id, Token.status.in_(["called", "in_consultation"])
    ).count()
    completed_tokens = db.query(Token).filter(
        Token.doctor_id == doctor_id, Token.status.in_(["completed", "cancelled"])
    ).count()
    total_in_queue = pending_tokens + in_progress_tokens
    return QueueStatus(
        doctor_id=doctor_id, current_token=0,
        pending_patients=pending_tokens, in_progress_patients=in_progress_tokens,
        completed_patients=completed_tokens, estimated_wait_time=pending_tokens * 3,
        people_ahead=pending_tokens, total_queue=total_in_queue, total_patients=total_in_queue,
    )
 
 
@public_router.get("/{doctor_id}/availability/today")
@router.get("/{doctor_id}/availability/today")
async def get_doctor_availability_today(doctor_id: str, db: Session = Depends(get_db)):
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    status_val = str(doctor.status or "").lower()
    start_time = (doctor.start_time or "").strip()
    end_time = (doctor.end_time or "").strip()
    days = [str(x).strip().lower() for x in (doctor.available_days or [])]
    from datetime import timezone as tz
    today_name = datetime.now(tz.utc).strftime("%A").lower()
    available_today = (
        status_val not in {"offline", "on_leave"}
        and bool(start_time) and bool(end_time)
        and ((not days) or (today_name in days))
    )
    return {
        "doctor_id": doctor_id, "available_today": available_today,
        "today_window": f"{start_time}-{end_time}" if start_time and end_time else None,
        "status": doctor.status, "available_days": doctor.available_days or [],
    }
 
 
@public_router.get("/{doctor_id}/availability")
@router.get("/{doctor_id}/availability")
async def get_doctor_availability(doctor_id: str, db: Session = Depends(get_db)):
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    return {
        "doctor_id": doctor_id, "status": doctor.status,
        "available_days": doctor.available_days or [],
        "start_time": doctor.start_time, "end_time": doctor.end_time,
    }
 
 
@public_router.get("/{doctor_id}", response_model=DoctorResponse)
@router.get("/{doctor_id}", response_model=DoctorResponse)
async def get_doctor(doctor_id: str, db: Session = Depends(get_db)):
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    return DoctorResponse(
        id=doctor.id, name=doctor.name, specialization=doctor.specialization,
        subcategory=doctor.subcategory, hospital_id=doctor.hospital_id,
        consultation_fee=doctor.consultation_fee, session_fee=doctor.session_fee,
        status=doctor.status, available_days=doctor.available_days or [],
        start_time=doctor.start_time, end_time=doctor.end_time,
        avatar_initials=doctor.avatar_initials, rating=doctor.rating,
        review_count=doctor.review_count,
    )
 
 
# ---------------------------------------------------------------------------
# Helper to avoid repeating 15-field dict literals everywhere
# ---------------------------------------------------------------------------
def _doctor_to_dict(doctor: Doctor) -> Dict[str, Any]:
    return {
        "id": doctor.id, "name": doctor.name, "specialization": doctor.specialization,
        "subcategory": doctor.subcategory, "hospital_id": doctor.hospital_id,
        "consultation_fee": doctor.consultation_fee, "session_fee": doctor.session_fee,
        "status": doctor.status, "available_days": doctor.available_days or [],
        "start_time": doctor.start_time, "end_time": doctor.end_time,
        "avatar_initials": doctor.avatar_initials, "rating": doctor.rating,
        "review_count": doctor.review_count, "created_at": doctor.created_at,
        "updated_at": doctor.updated_at,
    }

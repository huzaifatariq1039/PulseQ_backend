from fastapi import APIRouter, HTTPException, status, Depends, Request, Body, Query
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models import QueueResponse, QueueStatus, NotificationType, TokenStatus as TokenStatusEnum
from app.database import get_db
from app.db_models import User, Doctor, Token, Hospital
from app.security import get_current_active_user
from app.security import require_roles
from app.services.token_service import SmartTokenService
from app.services.notification_scheduler_client import send_queue_alert, send_final_call
from app.services.notification_service import NotificationService
from datetime import datetime, date, time
from app.utils.responses import ok, fail
from app.utils.idempotency import Idempotency
from app.utils.state import is_transition_allowed, STATUS_COMPLETED
from app.utils.audit import log_action, get_user_role

router = APIRouter(prefix="/queue", tags=["Queue Management"])

# -------------------- Advanced queue management (queues collection) --------------------
from app.services.queue_management_service import QueueManagementService


@router.get("/doctor/{doctor_id}", response_model=QueueResponse)
async def get_doctor_queue_status(
    doctor_id: str,
    appointment_date: Optional[datetime] = Query(None),
    token_number: Optional[int] = Query(None),
    payload: Optional[Dict[str, Any]] = Body(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get current queue status for a doctor"""
    
    # Fallback for Postman testing: if params not in query string, look in JSON body
    if appointment_date is None and payload and "appointment_date" in payload:
        try:
            appointment_date = datetime.fromisoformat(str(payload["appointment_date"]).replace('Z', '+00:00'))
        except Exception:
            pass
    if token_number is None and payload and "token_number" in payload:
        token_number = payload.get("token_number")
    
    # Verify doctor exists
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    # Get queue status
    queue_status = SmartTokenService.get_queue_status(doctor_id, token_number, appointment_date, db=db)
    
    return QueueResponse(
        id=f"queue_{doctor_id}",
        doctor_id=doctor_id,
        current_token=queue_status["current_token"],
        total_patients=queue_status["total_queue"],
        estimated_wait_time=queue_status["estimated_wait_time"],
        people_ahead=queue_status["people_ahead"],
        total_queue=queue_status["total_queue"],
        is_future_appointment=bool(queue_status.get("is_future_appointment")),
        doctor_unavailable=bool(queue_status.get("doctor_unavailable")),
        updated_at=datetime.utcnow()
    )

@router.post("/doctor/{doctor_id}/advance")
@router.post("/doctor/{doctor_id}/advance-queue")
async def advance_queue(
    doctor_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Advance the queue to next patient (for doctor/admin use)"""
    # TODO: Add role-based access control for doctors/admins
    
    # Emergency/unavailability: block queue advancement
    try:
        doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
        if doctor:
            dstatus = str(doctor.status.value if hasattr(doctor.status, 'value') else doctor.status).lower()
            if dstatus in {"offline", "on_leave"}:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor unavailable")
    except HTTPException:
        raise
    except Exception:
        pass
    
    today = date.today()
    today_start = datetime.combine(today, time.min)
    today_end = datetime.combine(today, time.max)
    
    # Get current queue from PostgreSQL
    tokens = db.query(Token).filter(
        and_(
            Token.doctor_id == doctor_id,
            Token.appointment_date >= today_start,
            Token.appointment_date <= today_end,
            Token.status != TokenStatusEnum.CANCELLED
        )
    ).order_by(Token.token_number).all()
    
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tokens in queue"
        )
    
    # Find current token and mark as completed
    current_token = None
    for token in tokens:
        status_val = str(token.status.value if hasattr(token.status, 'value') else token.status).lower()
        if status_val not in [STATUS_COMPLETED, "cancelled"]:
            current_token = token
            break
    
    if current_token:
        # Mark current token as completed (Testing bypass: allow from any state for now)
        current_token.status = TokenStatusEnum.COMPLETED
        end_time = datetime.utcnow()
        start_time = current_token.start_time
        duration_minutes = 0
        try:
            if start_time is not None:
                duration_minutes = max(0, int((end_time - start_time).total_seconds() // 60))
        except Exception:
            duration_minutes = 0

        # Mark current token as completed
        current_token.status = TokenStatusEnum.COMPLETED
        current_token.completed_at = datetime.utcnow()
        current_token.end_time = end_time
        current_token.duration_minutes = duration_minutes
        current_token.updated_at = datetime.utcnow()
        db.commit()
        
        # Notify next patient if exists
        next_token = None
        for token in tokens:
            if (token.token_number > current_token.token_number and 
                token.status not in [TokenStatusEnum.COMPLETED, TokenStatusEnum.CANCELLED]):
                next_token = token
                break
        
        if next_token:
            # Get patient phone number
            patient = db.query(User).filter(User.id == next_token.patient_id).first()
            
            if patient and patient.phone:
                # Get doctor info
                doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
                
                # Prefer display_code for user messages
                display_label = next_token.display_code or SmartTokenService.format_token(next_token.token_number)
                await NotificationService.send_appointment_ready_notification(
                    token_id=next_token.id,
                    phone_number=patient.phone,
                    token_number=display_label,
                    doctor_name=doctor.name if doctor else "Doctor",
                    notification_types=[NotificationType.WHATSAPP, NotificationType.SMS]
                )
    
    # Audit: DONE
    try:
        role = get_user_role(current_user.user_id)
        log_action(current_user.user_id, role, action="DONE", token_id=current_token.id if current_token else None)
    except Exception:
        pass

    # Return updated queue status
    updated_queue = SmartTokenService.get_queue_status(doctor_id)
    
    return {
        "message": "Queue advanced successfully",
        "previous_token": current_token.token_number if current_token else None,
        "current_token": updated_queue["current_token"],
        "total_queue": updated_queue["total_queue"]
    }

@router.post("/doctor/{doctor_id}/advance-idempotent")
async def advance_queue_idempotent(
    doctor_id: str,
    request: Request,
    current_user = Depends(get_current_active_user)
):
    """Idempotent variant of advance_queue using Idempotency-Key header.

    Prevents duplicate "DONE" actions from double-clicks in web UI.
    """

    key = request.headers.get(Idempotency.HEADER_NAME)
    if not key:
        return fail("Missing Idempotency-Key header", status_code=status.HTTP_400_BAD_REQUEST)
    key = Idempotency.validate_key(key)

    async def _runner():
        # Reuse the original advance logic by calling it directly
        res = await advance_queue(doctor_id, current_user)  # type: ignore
        return res

    result = await Idempotency.get_or_run_async(current_user.user_id, key, action=f"queue_advance_{doctor_id}", ttl_minutes=10, runner_async=_runner)
    # Normalize into standardized envelope
    return ok(data=result, message="Queue advanced (idempotent)")


@router.post("/token/{token_id}/start", dependencies=[Depends(require_roles("doctor", "admin"))])
async def start_consultation(
    token_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Transition a token from waiting -> in_consultation with strict validation."""
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    
    # Emergency/unavailability: block starting consultation
    try:
        doctor = db.query(Doctor).filter(Doctor.id == token.doctor_id).first()
        if doctor:
            dstatus = str(doctor.status.value if hasattr(doctor.status, 'value') else doctor.status).lower()
            if dstatus in {"offline", "on_leave"}:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor unavailable")
    except HTTPException:
        raise
    except Exception:
        pass

    # Ownership: doctor can only start their own token (admin allowed)
    try:
        role = get_user_role(current_user.user_id)
    except Exception:
        role = None
    if role != "admin":
        if str(token.doctor_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    curr = str(token.status.value if hasattr(token.status, 'value') else token.status).lower()
    target = "in_consultation"
    if not is_transition_allowed(curr, target):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="START only allowed from waiting/confirmed")
    
    token.status = TokenStatusEnum.IN_PROGRESS
    token.start_time = datetime.utcnow()
    token.updated_at = datetime.utcnow()
    db.commit()
    
    try:
        log_action(current_user.user_id, role, action="START", token_id=token_id)
    except Exception:
        pass
    return ok(data={"token_id": token_id, "from": curr, "to": target}, message="Token moved to in_consultation")


@router.post("/token/{token_id}/skip", dependencies=[Depends(require_roles("doctor", "admin"))])
async def skip_patient(
    token_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Mark a token as skipped (doctor/admin).

    Used by doctor portal to skip a patient from current consultation or waiting list.
    """
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    try:
        role = get_user_role(current_user.user_id)
    except Exception:
        role = None
    if role != "admin":
        if str(token.doctor_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    curr = str(token.status.value if hasattr(token.status, 'value') else token.status).lower()
    if curr in ("completed", "cancelled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot skip a completed/cancelled token")

    token.status = TokenStatusEnum.CANCELLED  # Using CANCELLED as skipped
    token.updated_at = datetime.utcnow()
    db.commit()
    
    try:
        log_action(current_user.user_id, role, action="SKIP", token_id=token_id)
    except Exception:
        pass
    return ok(data={"token_id": token_id, "from": curr, "to": "skipped"}, message="Token skipped")


@router.post("/token/{token_id}/complete", dependencies=[Depends(require_roles("doctor", "admin"))])
async def complete_consultation(
    token_id: str,
    payload: Optional[Dict[str, Any]] = Body(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user),
):
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    curr_status = str(token.status.value if hasattr(token.status, 'value') else token.status).lower()
    if not is_transition_allowed(curr_status, STATUS_COMPLETED):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="DONE only allowed from in_consultation")

    # Ownership: doctor can only complete their own token (admin allowed)
    try:
        role = get_user_role(current_user.user_id)
    except Exception:
        role = None
    if role != "admin":
        if str(token.doctor_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    end_time = datetime.utcnow()
    start_time = token.start_time
    duration_minutes = 0
    try:
        if start_time is not None:
            duration_minutes = max(0, int((end_time - start_time).total_seconds() // 60))
    except Exception:
        duration_minutes = 0

    # Update token
    token.status = TokenStatusEnum.COMPLETED
    token.completed_at = datetime.utcnow()
    token.end_time = end_time
    token.duration_minutes = duration_minutes
    token.updated_at = datetime.utcnow()

    # Persist consultation details (optional)
    if isinstance(payload, dict):
        if payload.get("consultation_notes") is not None:
            # You may want to store this in a separate consultation table
            pass
        if payload.get("diagnosis") is not None:
            pass
        if payload.get("prescription") is not None:
            pass
        if payload.get("medical_records_url") is not None:
            pass
        if payload.get("lab_reports") is not None:
            pass
        if payload.get("uploaded_files") is not None:
            pass
        if payload.get("attachments") is not None:
            pass

    db.commit()

    try:
        log_action(current_user.user_id, role, action="DONE", token_id=token_id)
    except Exception:
        pass

    return ok(data={"token_id": token_id, "status": "completed"}, message="Consultation completed")


@router.post("/token/{token_id}/start-idempotent")
async def start_consultation_idempotent(token_id: str, request: Request, current_user = Depends(get_current_active_user)):
    key = request.headers.get(Idempotency.HEADER_NAME)
    if not key:
        return fail("Missing Idempotency-Key header", status_code=status.HTTP_400_BAD_REQUEST)
    key = Idempotency.validate_key(key)

    async def _runner():
        return await start_consultation(token_id, current_user)  # type: ignore

    result = await Idempotency.get_or_run_async(current_user.user_id, key, action=f"token_start_{token_id}", ttl_minutes=10, runner_async=_runner)
    return ok(data=result, message="Token moved to in_consultation (idempotent)")


@router.post("/token/{token_id}/skip-idempotent")
async def skip_patient_idempotent(token_id: str, request: Request, current_user = Depends(get_current_active_user)):
    key = request.headers.get(Idempotency.HEADER_NAME)
    if not key:
        return fail("Missing Idempotency-Key header", status_code=status.HTTP_400_BAD_REQUEST)
    key = Idempotency.validate_key(key)

    async def _runner():
        return await skip_patient(token_id, current_user)  # type: ignore

    result = await Idempotency.get_or_run_async(current_user.user_id, key, action=f"token_skip_{token_id}", ttl_minutes=10, runner_async=_runner)
    return ok(data=result, message="Token skipped (idempotent)")

@router.get("/my-position")
async def get_my_queue_position(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get queue position for all active tokens of current user"""
    today = date.today()
    today_start = datetime.combine(today, time.min)
    today_end = datetime.combine(today, time.max)
    
    # Get user's active tokens for today from PostgreSQL
    user_tokens = db.query(Token).filter(
        and_(
            Token.patient_id == current_user.user_id,
            Token.appointment_date >= today_start,
            Token.appointment_date <= today_end,
            Token.status != TokenStatusEnum.CANCELLED
        )
    ).all()
    
    result_tokens = []
    for token in user_tokens:
        # Get queue status for this token
        queue_status = SmartTokenService.get_queue_status(
            token.doctor_id, 
            token.token_number
        )
        
        # Get doctor info
        doctor = db.query(Doctor).filter(Doctor.id == token.doctor_id).first()
        
        result_tokens.append({
            "token_id": token.id,
            "display_code": token.display_code,
            "token_number": token.token_number,
            "doctor_name": doctor.name if doctor else "Unknown Doctor",
            "doctor_specialization": doctor.specialization if doctor else "",
            "people_ahead": queue_status["people_ahead"],
            "estimated_wait_time": queue_status["estimated_wait_time"],
            "total_queue": queue_status["total_queue"],
            "status": token.status.value if hasattr(token.status, 'value') else token.status
        })
    
    return {
        "active_tokens": result_tokens,
        "total_active": len(result_tokens)
    }

@router.get("/snapshot/{room}")
async def queue_snapshot(
    room: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Explicit snapshot API for resilient web UIs.

    Room formats supported:
    - doctor_{doctorId}
    - hospital_{hospitalId}
    - token_{tokenId}
    - user_{userId} (only for the authenticated user)
    """
    try:
        if not room or "_" not in room:
            return fail("Invalid room", status_code=status.HTTP_400_BAD_REQUEST)

        prefix, ident = room.split("_", 1)
        prefix = prefix.lower().strip()
        ident = ident.strip()

        if prefix == "doctor":
            # Verify doctor exists
            doctor = db.query(Doctor).filter(Doctor.id == ident).first()
            if not doctor:
                return fail("Doctor not found", status_code=status.HTTP_404_NOT_FOUND)
            q = SmartTokenService.get_queue_status(ident)
            return ok(
                data={
                    "room": room,
                    "type": "doctor",
                    "doctor_id": ident,
                    "queue": q,
                },
                message="Doctor queue snapshot",
            )

        if prefix == "token":
            token = db.query(Token).filter(Token.id == ident).first()
            if not token:
                return fail("Token not found", status_code=status.HTTP_404_NOT_FOUND)
            q = SmartTokenService.get_queue_status(token.doctor_id, token.token_number)
            return ok(
                data={
                    "room": room,
                    "type": "token",
                    "token": {
                        "id": token.id,
                        "patient_id": token.patient_id,
                        "doctor_id": token.doctor_id,
                        "token_number": token.token_number,
                        "status": token.status.value if hasattr(token.status, 'value') else token.status,
                    },
                    "queue": q,
                },
                message="Token queue snapshot",
            )

        if prefix == "hospital":
            hospital = db.query(Hospital).filter(Hospital.id == ident).first()
            if not hospital:
                return fail("Hospital not found", status_code=status.HTTP_404_NOT_FOUND)
            # Aggregate per-doctor status
            doctors = db.query(Doctor).filter(Doctor.hospital_id == ident).all()
            per_doctor = []
            total_waiting = 0
            for doctor in doctors:
                q = SmartTokenService.get_queue_status(doctor.id)
                per_doctor.append({"doctor_id": doctor.id, "queue": q})
                try:
                    total_waiting += int(q.get("total_queue") or 0)
                except Exception:
                    pass
            return ok(
                data={
                    "room": room,
                    "type": "hospital",
                    "hospital_id": ident,
                    "total_queue": total_waiting,
                    "doctors": per_doctor,
                },
                message="Hospital queue snapshot",
            )

        if prefix == "user":
            # Restrict to self for privacy
            if ident != current_user.user_id:
                return fail("Forbidden", status_code=status.HTTP_403_FORBIDDEN)
            # Reuse my-position logic
            today = date.today()
            today_start = datetime.combine(today, time.min)
            today_end = datetime.combine(today, time.max)
            
            tokens = db.query(Token).filter(
                and_(
                    Token.patient_id == ident,
                    Token.appointment_date >= today_start,
                    Token.appointment_date <= today_end,
                    Token.status != TokenStatusEnum.CANCELLED
                )
            ).all()
            
            user_tokens = []
            for token in tokens:
                q = SmartTokenService.get_queue_status(token.doctor_id, token.token_number)
                user_tokens.append({
                    "token_id": token.id,
                    "display_code": token.display_code,
                    "token_number": token.token_number,
                    "doctor_id": token.doctor_id,
                    "people_ahead": q.get("people_ahead"),
                    "estimated_wait_time": q.get("estimated_wait_time"),
                    "total_queue": q.get("total_queue"),
                    "status": token.status.value if hasattr(token.status, 'value') else token.status,
                })
            return ok(
                data={"room": room, "type": "user", "user_id": ident, "active_tokens": user_tokens, "total_active": len(user_tokens)},
                message="User queue snapshot",
            )

        return fail("Unknown room type", status_code=status.HTTP_400_BAD_REQUEST)

    except HTTPException as he:
        # Preserve existing behavior for raised HTTPExceptions
        raise he
    except Exception:
        return fail("Failed to fetch snapshot", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.post("/advanced/add", dependencies=[Depends(require_roles("patient", "receptionist", "admin"))])
async def advanced_add_to_queue(payload: Dict[str, Any], current_user=Depends(get_current_active_user)):
    """Add patient to Firestore `queues` collection (FCFS)."""
    hospital_id = str(payload.get("hospital_id") or "").strip()
    doctor_id = str(payload.get("doctor_id") or "").strip()
    patient_id = str(payload.get("patient_id") or current_user.user_id or "").strip()
    if not hospital_id or not doctor_id or not patient_id:
        return fail("hospital_id, doctor_id, patient_id are required", status_code=status.HTTP_400_BAD_REQUEST)

    try:
        entry = await QueueManagementService.add_patient_to_queue(hospital_id=hospital_id, doctor_id=doctor_id, patient_id=patient_id)
        return ok(data=entry, message="Added to queue")
    except Exception as e:
        return fail(f"Failed to add to queue: {e}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.post("/advanced/call-next/{doctor_id}", dependencies=[Depends(require_roles("doctor", "receptionist", "admin"))])
async def advanced_call_next(
    doctor_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user)
):
    """Call the next waiting patient (sets status=called + called_at)."""
    try:
        called = await QueueManagementService.call_next_patient(doctor_id=str(doctor_id))
        if not called:
            return ok(data={"called": None}, message="No waiting patients")

        # Fire final-call WhatsApp via Node service (best-effort)
        try:
            patient_id = str(called.get("patient_id") or "")
            phone = None
            if patient_id:
                patient = db.query(User).filter(User.id == patient_id).first()
                if patient:
                    phone = patient.phone
            token_like = {
                "id": called.get("queue_id"),
                "patient_id": patient_id,
                "patient_phone": phone,
            }
            await send_final_call(token_like)
        except Exception:
            pass

        return ok(data={"called": called}, message="Next patient called")
    except ValueError as ve:
        return fail(str(ve), status_code=status.HTTP_409_CONFLICT)
    except Exception as e:
        return fail(f"Failed to call next: {e}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.post("/advanced/complete/{queue_id}", dependencies=[Depends(require_roles("doctor", "admin"))])
async def advanced_complete(queue_id: str, current_user=Depends(get_current_active_user)):
    """Complete a consultation and auto-call next."""
    try:
        res = await QueueManagementService.complete_consultation(queue_id=str(queue_id))
        return ok(data=res, message="Consultation completed")
    except KeyError:
        return fail("Queue entry not found", status_code=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return fail(f"Failed to complete: {e}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.post("/advanced/rejoin", dependencies=[Depends(require_roles("patient", "receptionist", "admin"))])
async def advanced_rejoin(payload: Dict[str, Any], current_user=Depends(get_current_active_user)):
    """Rejoin queue at the end (late arrival)."""
    hospital_id = str(payload.get("hospital_id") or "").strip()
    doctor_id = str(payload.get("doctor_id") or "").strip()
    patient_id = str(payload.get("patient_id") or current_user.user_id or "").strip()
    from_queue_id = payload.get("from_queue_id")
    if not hospital_id or not doctor_id or not patient_id:
        return fail("hospital_id, doctor_id, patient_id are required", status_code=status.HTTP_400_BAD_REQUEST)
    try:
        entry = await QueueManagementService.rejoin_queue(
            hospital_id=hospital_id,
            doctor_id=doctor_id,
            patient_id=patient_id,
            from_queue_id=str(from_queue_id) if from_queue_id else None,
        )
        return ok(data=entry, message="Rejoined queue at end")
    except Exception as e:
        return fail(f"Failed to rejoin: {e}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.post("/advanced/pause/{doctor_id}", dependencies=[Depends(require_roles("doctor", "admin"))])
async def advanced_pause(doctor_id: str, payload: Dict[str, Any] | None = None, current_user=Depends(get_current_active_user)):
    reason = "paused"
    if isinstance(payload, dict) and payload.get("reason"):
        reason = str(payload.get("reason"))
    try:
        await QueueManagementService.pause_queue(doctor_id=str(doctor_id), reason=reason)
        return ok(data={"doctor_id": doctor_id, "queue_paused": True, "reason": reason}, message="Queue paused")
    except Exception as e:
        return fail(f"Failed to pause: {e}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.post("/advanced/resume/{doctor_id}", dependencies=[Depends(require_roles("doctor", "admin"))])
async def advanced_resume(doctor_id: str, current_user=Depends(get_current_active_user)):
    try:
        await QueueManagementService.resume_queue(doctor_id=str(doctor_id))
        return ok(data={"doctor_id": doctor_id, "queue_paused": False}, message="Queue resumed")
    except Exception as e:
        return fail(f"Failed to resume: {e}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.post("/advanced/recalculate/{doctor_id}", dependencies=[Depends(require_roles("doctor", "receptionist", "admin"))])
async def advanced_recalculate(doctor_id: str, payload: Dict[str, Any] | None = None, current_user=Depends(get_current_active_user)):
    hospital_id = None
    if isinstance(payload, dict):
        hospital_id = payload.get("hospital_id")
    try:
        await QueueManagementService.recalculate_for_doctor(doctor_id=str(doctor_id), hospital_id=str(hospital_id) if hospital_id else None, reason="manual")
        return ok(data={"doctor_id": doctor_id}, message="Queue recalculated")
    except Exception as e:
        return fail(f"Failed to recalculate: {e}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

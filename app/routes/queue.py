from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import List, Dict, Any, Optional
from app.models import QueueResponse, QueueStatus, NotificationType
from app.database import get_db
from app.config import COLLECTIONS
from app.security import get_current_active_user
from app.security import require_roles
from app.services.token_service import SmartTokenService
from app.services.notification_scheduler_client import send_queue_alert, send_final_call
from app.services.notification_service import NotificationService
from datetime import datetime
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
    current_user = Depends(get_current_active_user)
):
    """Get current queue status for a doctor"""
    db = get_db()
    
    # Verify doctor exists
    doctor_ref = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id)
    if not doctor_ref.get().exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    # Get queue status
    queue_status = SmartTokenService.get_queue_status(doctor_id)
    
    return QueueResponse(
        id=f"queue_{doctor_id}",
        doctor_id=doctor_id,
        current_token=queue_status["current_token"],
        total_patients=queue_status["total_queue"],
        estimated_wait_time=queue_status["estimated_wait_time"],
        people_ahead=0,  # This is for general queue, not specific to a token
        total_queue=queue_status["total_queue"],
        doctor_unavailable=bool(queue_status.get("doctor_unavailable")),
        updated_at=datetime.utcnow()
    )

@router.post("/doctor/{doctor_id}/advance")
async def advance_queue(
    doctor_id: str,
    current_user = Depends(get_current_active_user)
):
    """Advance the queue to next patient (for doctor/admin use)"""
    # TODO: Add role-based access control for doctors/admins
    
    db = get_db()
    # Emergency/unavailability: block queue advancement
    try:
        d = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id).get().to_dict() or {}
        dstatus = str(d.get("status") or "").lower()
        if dstatus in {"offline", "on_leave"} or bool(d.get("queue_paused")) or bool(d.get("paused")):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor unavailable")
    except HTTPException:
        raise
    except Exception:
        pass
    today = datetime.now().date()
    
    # Get current queue - use simple query to avoid composite index requirement
    tokens_ref = db.collection(COLLECTIONS["TOKENS"])
    query = tokens_ref.where("doctor_id", "==", doctor_id)
    
    tokens = []
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    
    for doc in query.stream():
        token_data = doc.to_dict()
        token_data["doc_id"] = doc.id
        
        # Filter in memory to avoid composite index requirement
        appointment_date = token_data.get("appointment_date")
        if isinstance(appointment_date, str):
            appointment_date = datetime.fromisoformat(appointment_date.replace('Z', '+00:00'))
        
        # Convert to naive datetime for comparison if it's offset-aware
        if appointment_date and appointment_date.tzinfo is not None:
            appointment_date = appointment_date.replace(tzinfo=None)
        
        # Only include tokens for today that are not cancelled
        if (appointment_date and 
            today_start <= appointment_date <= today_end and 
            token_data.get("status") != "cancelled"):
            tokens.append(token_data)
    
    tokens.sort(key=lambda x: x.get("token_number", 0))
    
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tokens in queue"
        )
    
    # Find current token and mark as completed
    current_token = None
    for token in tokens:
        if token.get("status") not in ["completed"]:
            current_token = token
            break
    
    if current_token:
        # Enforce state machine: DONE only from in_consultation
        curr_status = str(current_token.get("status", "")).lower()
        if not is_transition_allowed(curr_status, STATUS_COMPLETED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="DONE only allowed from in_consultation"
            )
        def _to_dt(v):
            try:
                if v is None:
                    return None
                if isinstance(v, datetime):
                    return v
                to_dt = getattr(v, "to_datetime", None)
                if callable(to_dt):
                    return to_dt()
                return datetime.fromisoformat(str(v))
            except Exception:
                return None

        end_time = datetime.utcnow()
        start_time = _to_dt(current_token.get("start_time"))
        duration_minutes = 0
        try:
            if start_time is not None:
                duration_minutes = max(0, int((end_time - start_time).total_seconds() // 60))
        except Exception:
            duration_minutes = 0

        # Mark current token as completed
        token_ref = db.collection(COLLECTIONS["TOKENS"]).document(current_token["doc_id"])
        token_ref.update({
            "status": "completed",
            "completed_at": datetime.utcnow(),
            "end_time": end_time,
            "duration_minutes": duration_minutes,
            "updated_at": datetime.utcnow()
        })
        
        # Notify next patient if exists
        next_token = None
        for token in tokens:
            if (token.get("token_number", 0) > current_token.get("token_number", 0) and 
                token.get("status") not in ["completed", "cancelled"]):
                next_token = token
                break
        
        if next_token:
            # Get patient phone number
            user_ref = db.collection(COLLECTIONS["USERS"]).document(next_token["patient_id"])
            user_data = user_ref.get().to_dict()
            
            if user_data and user_data.get("phone"):
                # Send notification to next patient
                doctor_ref = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id)
                doctor_data = doctor_ref.get().to_dict()
                
                # Prefer display_code for user messages
                display_label = next_token.get("display_code") or SmartTokenService.format_token(next_token["token_number"])
                await NotificationService.send_appointment_ready_notification(
                    token_id=next_token["doc_id"],
                    phone_number=user_data["phone"],
                    token_number=display_label,
                    doctor_name=doctor_data.get("name", "Doctor"),
                    notification_types=[NotificationType.WHATSAPP, NotificationType.SMS]
                )
    
    # Audit: DONE
    try:
        role = get_user_role(current_user.user_id)
        log_action(current_user.user_id, role, action="DONE", token_id=(current_token or {}).get("doc_id"))
    except Exception:
        pass

    # Return updated queue status
    updated_queue = SmartTokenService.get_queue_status(doctor_id)
    
    return {
        "message": "Queue advanced successfully",
        "previous_token": current_token.get("token_number") if current_token else None,
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
async def start_consultation(token_id: str, current_user = Depends(get_current_active_user)):
    """Transition a token from waiting -> in_consultation with strict validation."""
    db = get_db()
    tref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    snap = tref.get()
    if not snap.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    t = snap.to_dict() or {}
    # Emergency/unavailability: block starting consultation
    try:
        did = str(t.get("doctor_id") or "")
        if did:
            d = db.collection(COLLECTIONS["DOCTORS"]).document(did).get().to_dict() or {}
            dstatus = str(d.get("status") or "").lower()
            if dstatus in {"offline", "on_leave"} or bool(d.get("queue_paused")) or bool(d.get("paused")):
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
        if str(t.get("doctor_id") or "") != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    curr = str(t.get("status", "")).lower()
    target = "in_consultation"
    if not is_transition_allowed(curr, target):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="START only allowed from waiting/confirmed")
    tref.update({"status": target, "start_time": datetime.utcnow(), "updated_at": datetime.utcnow()})
    try:
        log_action(current_user.user_id, role, action="START", token_id=token_id)
    except Exception:
        pass
    return ok(data={"token_id": token_id, "from": curr, "to": target}, message="Token moved to in_consultation")


@router.post("/token/{token_id}/skip", dependencies=[Depends(require_roles("doctor", "admin"))])
async def skip_patient(token_id: str, current_user = Depends(get_current_active_user)):
    """Mark a token as skipped (doctor/admin).

    Used by doctor portal to skip a patient from current consultation or waiting list.
    """
    db = get_db()
    tref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    snap = tref.get()
    if not getattr(snap, "exists", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    t = snap.to_dict() or {}

    try:
        role = get_user_role(current_user.user_id)
    except Exception:
        role = None
    if role != "admin":
        if str(t.get("doctor_id") or "") != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    curr = str(t.get("status") or "").lower()
    if curr in ("completed", "cancelled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot skip a completed/cancelled token")

    tref.set({"status": "skipped", "skipped_at": datetime.utcnow(), "updated_at": datetime.utcnow()}, merge=True)
    try:
        log_action(current_user.user_id, role, action="SKIP", token_id=token_id)
    except Exception:
        pass
    return ok(data={"token_id": token_id, "from": curr, "to": "skipped"}, message="Token skipped")


@router.post("/token/{token_id}/complete", dependencies=[Depends(require_roles("doctor", "admin"))])
async def complete_consultation(
    token_id: str,
    payload: Dict[str, Any],
    current_user = Depends(get_current_active_user),
):
    db = get_db()
    tref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    snap = tref.get()
    if not getattr(snap, "exists", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    t = snap.to_dict() or {}
    curr_status = str(t.get("status") or "").lower()
    if not is_transition_allowed(curr_status, STATUS_COMPLETED):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="DONE only allowed from in_consultation")

    # Ownership: doctor can only complete their own token (admin allowed)
    try:
        role = get_user_role(current_user.user_id)
    except Exception:
        role = None
    if role != "admin":
        if str(t.get("doctor_id") or "") != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    def _to_dt(v: Any) -> Optional[datetime]:
        try:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            to_dt = getattr(v, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(v))
        except Exception:
            return None

    end_time = datetime.utcnow()
    start_time = _to_dt(t.get("start_time"))
    duration_minutes = 0
    try:
        if start_time is not None:
            duration_minutes = max(0, int((end_time - start_time).total_seconds() // 60))
    except Exception:
        duration_minutes = 0

    updates: Dict[str, Any] = {
        "status": "completed",
        "completed_at": datetime.utcnow(),
        "end_time": end_time,
        "duration_minutes": duration_minutes,
        "updated_at": datetime.utcnow(),
    }

    # Persist consultation details (optional)
    if isinstance(payload, dict):
        if payload.get("consultation_notes") is not None:
            updates["consultation_notes"] = payload.get("consultation_notes")
        if payload.get("diagnosis") is not None:
            updates["diagnosis"] = payload.get("diagnosis")
        if payload.get("prescription") is not None:
            updates["prescription"] = payload.get("prescription")
        if payload.get("medical_records_url") is not None:
            updates["medical_records_url"] = payload.get("medical_records_url")
        if payload.get("lab_reports") is not None:
            updates["lab_reports"] = payload.get("lab_reports")
        if payload.get("uploaded_files") is not None:
            updates["uploaded_files"] = payload.get("uploaded_files")
        if payload.get("attachments") is not None and "uploaded_files" not in updates:
            updates["uploaded_files"] = payload.get("attachments")

    tref.set(updates, merge=True)

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
async def get_my_queue_position(current_user = Depends(get_current_active_user)):
    """Get queue position for all active tokens of current user"""
    db = get_db()
    today = datetime.now().date()
    
    # Get user's active tokens for today - use simple query to avoid composite index requirement
    tokens_ref = db.collection(COLLECTIONS["TOKENS"])
    query = tokens_ref.where("patient_id", "==", current_user.user_id)
    
    user_tokens = []
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    
    for doc in query.stream():
        token_data = doc.to_dict()
        
        # Filter in memory to avoid composite index requirement
        appointment_date = token_data.get("appointment_date")
        if isinstance(appointment_date, str):
            appointment_date = datetime.fromisoformat(appointment_date.replace('Z', '+00:00'))
        
        # Convert to naive datetime for comparison if it's offset-aware
        if appointment_date and appointment_date.tzinfo is not None:
            appointment_date = appointment_date.replace(tzinfo=None)
        
        # Only include tokens for today that are not cancelled
        if (appointment_date and 
            today_start <= appointment_date <= today_end and 
            token_data.get("status") != "cancelled"):
            
            # Get queue status for this token
            queue_status = SmartTokenService.get_queue_status(
                token_data["doctor_id"], 
                token_data["token_number"]
            )
            
            # Get doctor info
            doctor_ref = db.collection(COLLECTIONS["DOCTORS"]).document(token_data["doctor_id"])
            doctor_data = doctor_ref.get().to_dict()
            
            user_tokens.append({
                "token_id": doc.id,
                "display_code": token_data.get("display_code"),
                "token_number": token_data["token_number"],
                "doctor_name": doctor_data.get("name", "Unknown Doctor"),
                "doctor_specialization": doctor_data.get("specialization", ""),
                "people_ahead": queue_status["people_ahead"],
                "estimated_wait_time": queue_status["estimated_wait_time"],
                "total_queue": queue_status["total_queue"],
                "status": token_data.get("status", "pending")
            })
    
    return {
        "active_tokens": user_tokens,
        "total_active": len(user_tokens)
    }

@router.get("/snapshot/{room}")
async def queue_snapshot(room: str, current_user = Depends(get_current_active_user)):
    """Explicit snapshot API for resilient web UIs.

    Room formats supported:
    - doctor_{doctorId}
    - hospital_{hospitalId}
    - token_{tokenId}
    - user_{userId} (only for the authenticated user)
    """
    db = get_db()

    try:
        if not room or "_" not in room:
            return fail("Invalid room", status_code=status.HTTP_400_BAD_REQUEST)

        prefix, ident = room.split("_", 1)
        prefix = prefix.lower().strip()
        ident = ident.strip()

        if prefix == "doctor":
            # Verify doctor exists
            dref = db.collection(COLLECTIONS["DOCTORS"]).document(ident)
            if not dref.get().exists:
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
            tref = db.collection(COLLECTIONS["TOKENS"]).document(ident)
            tdoc = tref.get()
            if not tdoc.exists:
                return fail("Token not found", status_code=status.HTTP_404_NOT_FOUND)
            t = tdoc.to_dict()
            q = SmartTokenService.get_queue_status(t.get("doctor_id"), t.get("token_number"))
            return ok(
                data={
                    "room": room,
                    "type": "token",
                    "token": t,
                    "queue": q,
                },
                message="Token queue snapshot",
            )

        if prefix == "hospital":
            href = db.collection(COLLECTIONS["HOSPITALS"]).document(ident)
            if not href.get().exists:
                return fail("Hospital not found", status_code=status.HTTP_404_NOT_FOUND)
            # Aggregate per-doctor status
            docs = list(db.collection(COLLECTIONS["DOCTORS"]).where("hospital_id", "==", ident).stream())
            per_doctor = []
            total_waiting = 0
            for d in docs:
                did = d.id
                q = SmartTokenService.get_queue_status(did)
                per_doctor.append({"doctor_id": did, "queue": q})
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
            today = datetime.now().date()
            tokens_ref = db.collection(COLLECTIONS["TOKENS"]).where("patient_id", "==", ident)
            user_tokens = []
            today_start = datetime.combine(today, datetime.min.time())
            today_end = datetime.combine(today, datetime.max.time())
            for doc in tokens_ref.stream():
                token_data = doc.to_dict()
                appointment_date = token_data.get("appointment_date")
                if isinstance(appointment_date, str):
                    appointment_date = datetime.fromisoformat(appointment_date.replace('Z', '+00:00'))
                if appointment_date and appointment_date.tzinfo is not None:
                    appointment_date = appointment_date.replace(tzinfo=None)
                if (
                    appointment_date
                    and today_start <= appointment_date <= today_end
                    and token_data.get("status") != "cancelled"
                ):
                    q = SmartTokenService.get_queue_status(token_data["doctor_id"], token_data["token_number"])
                    user_tokens.append({
                        "token_id": doc.id,
                        "display_code": token_data.get("display_code"),
                        "token_number": token_data.get("token_number"),
                        "doctor_id": token_data.get("doctor_id"),
                        "people_ahead": q.get("people_ahead"),
                        "estimated_wait_time": q.get("estimated_wait_time"),
                        "total_queue": q.get("total_queue"),
                        "status": token_data.get("status", "pending"),
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
async def advanced_call_next(doctor_id: str, current_user=Depends(get_current_active_user)):
    """Call the next waiting patient (sets status=called + called_at)."""
    try:
        called = await QueueManagementService.call_next_patient(doctor_id=str(doctor_id))
        if not called:
            return ok(data={"called": None}, message="No waiting patients")

        # Fire final-call WhatsApp via Node service (best-effort)
        try:
            db = get_db()
            patient_id = str(called.get("patient_id") or "")
            phone = None
            if patient_id:
                usnap = db.collection(COLLECTIONS["USERS"]).document(patient_id).get()
                if getattr(usnap, "exists", False):
                    u = usnap.to_dict() or {}
                    phone = u.get("phone")
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

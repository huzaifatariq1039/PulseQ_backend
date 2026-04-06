from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta

from app.security import get_current_active_user
from app.config import COLLECTIONS
from app.database import get_db
from app.security import require_roles
from app.utils.responses import ok
from app.utils.audit import get_user_role, log_action
from app.services.notification_service import NotificationService
from app.services.whatsapp_service import send_template_message
from app.templates import TEMPLATES


router = APIRouter(tags=["Consultation Flow"])


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


def _is_empty(v: Any) -> bool:
    return v is None or str(v).strip() == ""


def _auto_skip_called_tokens(db, hospital_id: Optional[str] = None, doctor_id: Optional[str] = None) -> int:
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=3)
    ref = db.collection(COLLECTIONS["TOKENS"])
    if hospital_id:
        ref = ref.where("hospital_id", "==", hospital_id)
    if doctor_id:
        ref = ref.where("doctor_id", "==", doctor_id)
    updated = 0
    docs = [d for d in ref.limit(5000).stream()]
    for d in docs:
        data = d.to_dict() or {}
        st = str(getattr(data.get("status"), "value", data.get("status")) or "").lower()
        if st != "called":
            continue
        called_at = _to_dt(data.get("called_at"))
        if called_at is None or called_at > cutoff:
            continue
        try:
            db.collection(COLLECTIONS["TOKENS"]).document(d.id).set(
                {"status": "skipped", "skipped_at": now, "updated_at": now},
                merge=True,
            )
            updated += 1
        except Exception:
            continue
    return updated


@router.get("/doctor/current-patient/{doctor_id}", dependencies=[Depends(require_roles("doctor", "admin"))])
async def doctor_current_patient(
    doctor_id: str,
    current_user=Depends(get_current_active_user),
    hospital_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    db = get_db()

    try:
        role = get_user_role(current_user.user_id)
    except Exception:
        role = None
    if role != "admin" and str(current_user.user_id) != str(doctor_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    _auto_skip_called_tokens(db, hospital_id=hospital_id, doctor_id=doctor_id)

    ref = db.collection(COLLECTIONS["TOKENS"]).where("doctor_id", "==", doctor_id)
    if hospital_id:
        ref = ref.where("hospital_id", "==", hospital_id)

    docs = [d for d in ref.limit(2000).stream()]
    items: List[Dict[str, Any]] = []
    today = datetime.utcnow().date()
    for d in docs:
        t = d.to_dict() or {}
        st = str(getattr(t.get("status"), "value", t.get("status")) or "").lower()
        if st != "called":
            continue
        appt = _to_dt(t.get("appointment_date"))
        if appt and appt.date() != today:
            continue
        if _is_empty(t.get("assigned_to_doctor")):
            continue
        if str(t.get("assigned_to_doctor")) != str(doctor_id):
            continue
        if not t.get("id"):
            t["id"] = d.id
        items.append(t)

    items.sort(key=lambda x: int(x.get("token_number") or 0))
    token = items[0] if items else None
    return ok(data={"token": token})


@router.post("/consultation/start", dependencies=[Depends(require_roles("doctor", "admin"))])
async def consultation_start(payload: Dict[str, Any], current_user=Depends(get_current_active_user)) -> Dict[str, Any]:
    token_id = str((payload or {}).get("token_id") or "").strip()
    doctor_id = str((payload or {}).get("doctor_id") or "").strip()
    if not token_id or not doctor_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token_id and doctor_id are required")

    db = get_db()

    try:
        role = get_user_role(current_user.user_id)
    except Exception:
        role = None
    if role != "admin" and str(current_user.user_id) != str(doctor_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    _auto_skip_called_tokens(db, doctor_id=doctor_id)

    dref = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id)
    dsnap = dref.get()
    if not getattr(dsnap, "exists", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    d = dsnap.to_dict() or {}
    dstatus = str(d.get("status") or "").lower()
    queue_paused = bool(d.get("queue_paused")) or bool(d.get("paused"))
    if dstatus in {"offline", "on_leave"} or queue_paused:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor unavailable")
    if dstatus == "busy":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Doctor busy")

    tref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    tsnap = tref.get()
    if not getattr(tsnap, "exists", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    t = tsnap.to_dict() or {}

    if str(t.get("doctor_id") or "") != str(doctor_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token not assigned to this doctor")

    st = str(getattr(t.get("status"), "value", t.get("status")) or "").lower()
    if st in ("completed", "cancelled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token already completed")

    # Allow starting from "called" as well as waiting-like states (some UIs don't explicitly call first).
    if st not in ("called", "pending", "waiting", "confirmed"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token cannot be started from current status")

    # Enforce opt-in queue behavior
    if t.get("queue_opt_in") is not True:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Patient has not opted in to the queue")

    if not _is_empty(t.get("assigned_to_doctor")) and str(t.get("assigned_to_doctor")) != str(doctor_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Token is assigned to a different doctor")

    now = datetime.utcnow()
    try:
        tref.set(
            {
                "status": "in_consultation",
                "started_at": now,
                "started_by": doctor_id,
                "assigned_to_doctor": doctor_id,
                "called_at": t.get("called_at") or now,
                "updated_at": now,
            },
            merge=True,
        )
        dref.set({"status": "busy", "updated_at": now}, merge=True)
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to start consultation")

    try:
        log_action(current_user.user_id, role, action="START", token_id=token_id)
    except Exception:
        pass

    return ok(data={"token_id": token_id, "doctor_id": doctor_id, "status": "in_consultation"}, message="Consultation started")


@router.post("/consultation/end", dependencies=[Depends(require_roles("doctor", "admin"))])
async def consultation_end(payload: Dict[str, Any], current_user=Depends(get_current_active_user)) -> Dict[str, Any]:
    token_id = str((payload or {}).get("token_id") or "").strip()
    doctor_id = str((payload or {}).get("doctor_id") or "").strip()
    if not token_id or not doctor_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token_id and doctor_id are required")

    db = get_db()

    try:
        role = get_user_role(current_user.user_id)
    except Exception:
        role = None
    if role != "admin" and str(current_user.user_id) != str(doctor_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    dref = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id)
    dsnap = dref.get()
    if not getattr(dsnap, "exists", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    tref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    tsnap = tref.get()
    if not getattr(tsnap, "exists", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    t = tsnap.to_dict() or {}

    if str(t.get("doctor_id") or "") != str(doctor_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token not assigned to this doctor")

    st = str(getattr(t.get("status"), "value", t.get("status")) or "").lower()
    if st == "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token already completed")
    if st != "in_consultation":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token not in consultation")

    now = datetime.utcnow()
    try:
        tref.set({"status": "completed", "completed_at": now, "updated_at": now}, merge=True)
        dref.set({"status": "available", "updated_at": now}, merge=True)
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to end consultation")

    # THANKYOU message (best-effort)
    try:
        tpl = str(TEMPLATES.get("THANKYOU") or "").strip()
    except Exception:
        tpl = ""
    if tpl:
        try:
            phone = str(t.get("patient_phone") or "").strip()
            if not phone and t.get("patient_id"):
                us = db.collection(COLLECTIONS["USERS"]).document(str(t.get("patient_id"))).get()
                if getattr(us, "exists", False):
                    u = us.to_dict() or {}
                    phone = str(u.get("phone") or u.get("mobile") or "").strip()
            if phone:
                await send_template_message(phone, tpl, [])
        except Exception:
            pass

    # Auto-call next token in FCFS order (today only, opted-in only)
    next_token: Optional[Dict[str, Any]] = None
    try:
        hospital_id = str((payload or {}).get("hospital_id") or (t.get("hospital_id") or "")).strip() or None
        ref = db.collection(COLLECTIONS["TOKENS"]).where("doctor_id", "==", doctor_id)
        if hospital_id:
            ref = ref.where("hospital_id", "==", hospital_id)
        docs = [d for d in ref.limit(5000).stream()]
        today = datetime.utcnow().date()

        cur_num = 0
        try:
            cur_num = int(t.get("token_number") or 0)
        except Exception:
            cur_num = 0

        candidates: List[Dict[str, Any]] = []
        for d in docs:
            td = d.to_dict() or {}
            st2 = str(getattr(td.get("status"), "value", td.get("status")) or "").lower()
            if st2 in {"completed", "cancelled", "rescheduled"}:
                continue
            if td.get("queue_opt_in") is not True:
                continue
            appt = _to_dt(td.get("appointment_date"))
            if appt and appt.date() != today:
                continue
            try:
                n = int(td.get("token_number") or 0)
            except Exception:
                continue
            if n <= cur_num:
                continue
            # waiting-like only
            if st2 not in {"pending", "waiting", "confirmed"}:
                continue
            td["id"] = td.get("id") or d.id
            candidates.append(td)

        candidates.sort(key=lambda x: int(x.get("token_number") or 0))
        next_token = candidates[0] if candidates else None

        if next_token:
            nref = db.collection(COLLECTIONS["TOKENS"]).document(str(next_token.get("id")))
            nref.set(
                {
                    "status": "called",
                    "called_at": now,
                    "assigned_to_doctor": doctor_id,
                    "updated_at": now,
                },
                merge=True,
            )
            # Best-effort patient notify
            try:
                phone = str(next_token.get("patient_phone") or "").strip()
                if not phone and next_token.get("patient_id"):
                    us = db.collection(COLLECTIONS["USERS"]).document(str(next_token.get("patient_id"))).get()
                    if getattr(us, "exists", False):
                        u = us.to_dict() or {}
                        phone = str(u.get("phone") or u.get("mobile") or "").strip()
                if phone:
                    display_label = next_token.get("display_code")
                    if not display_label:
                        try:
                            display_label = str(next_token.get("token_number"))
                        except Exception:
                            display_label = ""

                    patient_name = str(next_token.get("patient_name") or "").strip()
                    if not patient_name and next_token.get("patient_id"):
                        try:
                            us2 = db.collection(COLLECTIONS["USERS"]).document(str(next_token.get("patient_id"))).get()
                            if getattr(us2, "exists", False):
                                u2 = us2.to_dict() or {}
                                patient_name = str(u2.get("name") or u2.get("full_name") or "").strip()
                        except Exception:
                            patient_name = patient_name

                    body_params: List[str] = []
                    if patient_name:
                        body_params.append(patient_name)
                    if display_label:
                        body_params.append(str(display_label))

                    await NotificationService.send_whatsapp_template(
                        phone_number=phone,
                        template_name="patient_call_alert",
                        body_parameters=body_params,
                    )
            except Exception:
                pass
    except Exception:
        next_token = None

    try:
        log_action(current_user.user_id, role, action="DONE", token_id=token_id)
    except Exception:
        pass

    return ok(
        data={
            "token_id": token_id,
            "doctor_id": doctor_id,
            "status": "completed",
            "next_called_token": next_token,
        },
        message="Consultation completed",
    )

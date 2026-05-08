from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from app.config import COLLECTIONS
from app.database import get_db


def _parse_day_dd_mm_yyyy(day: str) -> datetime.date:
    try:
        return datetime.strptime(str(day).strip(), "%d-%m-%Y").date()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid day format. Use DD-MM-YYYY")


def _parse_time_hhmm_ampm(t: str) -> Tuple[int, int]:
    s = str(t or "").strip()
    if not s:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="time is required")
    # Accept "09:00 AM" or "9:00 AM"
    try:
        dt = datetime.strptime(s.upper(), "%I:%M %p")
        return dt.hour, dt.minute
    except Exception:
        pass
    # Accept 24h "HH:MM"
    try:
        dt = datetime.strptime(s, "%H:%M")
        return dt.hour, dt.minute
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid time format. Use HH:MM AM/PM")


def _fmt_time_12h(h: int, m: int) -> str:
    dt = datetime(2000, 1, 1, h, m)
    return dt.strftime("%I:%M %p")


def _weekday_name(d: datetime.date) -> str:
    return d.strftime("%A").strip().lower()


def _doctor_availability(doc: Dict[str, Any]) -> Tuple[List[str], str, str]:
    days = [str(x).strip().lower() for x in (doc.get("available_days") or []) if str(x).strip()]
    start_time = str(doc.get("start_time") or "").strip()
    end_time = str(doc.get("end_time") or "").strip()
    return days, start_time, end_time


def _parse_doctor_hhmm(v: str) -> Tuple[int, int]:
    s = str(v or "").strip()
    if not s:
        raise ValueError("missing")
    # Accept already in HH:MM
    try:
        dt = datetime.strptime(s, "%H:%M")
        return dt.hour, dt.minute
    except Exception:
        pass
    # Accept AM/PM
    dt = datetime.strptime(s.upper(), "%I:%M %p")
    return dt.hour, dt.minute


def slot_id_for(doctor_id: str, day: datetime.date, hour: int, minute: int) -> str:
    return f"slot_{doctor_id}_{day.strftime('%Y%m%d')}_{hour:02d}{minute:02d}"


def appointment_dt_utc_for(day: datetime.date, hour: int, minute: int) -> datetime:
    # Treat selected time as UTC for storage consistency.
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)


def generate_slots_for_doctor(doctor_doc: Dict[str, Any], day: datetime.date, slot_minutes: int = 15) -> List[Dict[str, Any]]:
    # Emergency/unavailability: hide slots to avoid new bookings.
    dstatus = str(doctor_doc.get("status") or "").lower()
    if dstatus in {"offline", "on_leave"} or bool(doctor_doc.get("queue_paused")) or bool(doctor_doc.get("paused")):
        return []

    days, start_s, end_s = _doctor_availability(doctor_doc)
    if days:
        if _weekday_name(day) not in days:
            return []

    try:
        sh, sm = _parse_doctor_hhmm(start_s)
        eh, em = _parse_doctor_hhmm(end_s)
    except Exception:
        return []

    start = datetime(day.year, day.month, day.day, sh, sm, tzinfo=timezone.utc)
    end = datetime(day.year, day.month, day.day, eh, em, tzinfo=timezone.utc)
    if end <= start:
        return []

    step = max(5, int(slot_minutes or 15))
    out: List[Dict[str, Any]] = []
    cur = start
    while cur + timedelta(minutes=step) <= end:
        out.append({"time": _fmt_time_12h(cur.hour, cur.minute)})
        cur = cur + timedelta(minutes=step)
    return out


def reserve_slot_transactionally(doctor_id: str, hospital_id: str, patient_id: str, day: str, time: str) -> Dict[str, Any]:
    """Reserve a slot in COLLECTIONS['APPOINTMENTS'] to prevent double booking.

    Creates/updates an appointment-slot doc with status 'reserved'. Caller should finalize to 'booked' once token exists.
    """
    db = get_db()
    # Block reservations when doctor is unavailable (including emergency leave).
    try:
        dref = db.collection(COLLECTIONS["DOCTORS"]).document(str(doctor_id)).get()
        if not getattr(dref, "exists", False):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
        d = dref.to_dict() or {}
        dstatus = str(d.get("status") or "").lower()
        if dstatus in {"offline", "on_leave"} or bool(d.get("queue_paused")) or bool(d.get("paused")):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor unavailable")
    except HTTPException:
        raise
    except Exception:
        # Fail-open for safety: slot reservation should still work if status lookup fails.
        pass
    d = _parse_day_dd_mm_yyyy(day)
    h, m = _parse_time_hhmm_ampm(time)
    slot_id = slot_id_for(doctor_id, d, h, m)
    appt_dt_utc = appointment_dt_utc_for(d, h, m)

    ref = db.collection(COLLECTIONS["APPOINTMENTS"]).document(slot_id)
    now = datetime.utcnow()

    try:
        from google.cloud import firestore  # type: ignore
        tx = db.transaction()

        @firestore.transactional
        def _reserve(transaction):
            snap = ref.get(transaction=transaction)
            if getattr(snap, "exists", False):
                data = snap.to_dict() or {}
                st = str(data.get("status") or "").lower()
                if st in ("reserved", "booked"):
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slot already booked")
            payload = {
                "id": slot_id,
                "slot_id": slot_id,
                "doctor_id": doctor_id,
                "hospital_id": hospital_id,
                "patient_id": patient_id,
                "day": day,
                "time": time,
                "appointment_date": appt_dt_utc,
                "status": "reserved",
                "updated_at": now,
                "created_at": now,
            }
            transaction.set(ref, payload, merge=True)
            return payload

        return _reserve(tx)
    except HTTPException:
        raise
    except Exception:
        # Fallback non-transactional (best effort)
        snap = ref.get()
        if getattr(snap, "exists", False):
            data = snap.to_dict() or {}
            st = str(data.get("status") or "").lower()
            if st in ("reserved", "booked"):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slot already booked")
        payload = {
            "id": slot_id,
            "slot_id": slot_id,
            "doctor_id": doctor_id,
            "hospital_id": hospital_id,
            "patient_id": patient_id,
            "day": day,
            "time": time,
            "appointment_date": appt_dt_utc,
            "status": "reserved",
            "updated_at": now,
            "created_at": now,
        }
        ref.set(payload, merge=True)
        return payload


def finalize_slot_booking(slot_id: str, token_id: str) -> None:
    db = get_db()
    ref = db.collection(COLLECTIONS["APPOINTMENTS"]).document(slot_id)
    try:
        ref.set({"status": "booked", "token_id": token_id, "updated_at": datetime.utcnow()}, merge=True)
    except Exception:
        pass


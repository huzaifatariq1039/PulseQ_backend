from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ai_engine import ai_engine
from app.database import get_db
import app.database as db_mod

router = APIRouter()


class AIPredictRequest(BaseModel):
    name: str
    age: int
    doctor: str
    disease_type: str


def get_current_hour() -> int:
    return datetime.now().hour


def get_current_day() -> int:
    # Monday=0 .. Sunday=6
    return datetime.now().weekday()


def calculate_patients_ahead(doctor: str) -> int:
    db = get_db()
    tokens_ref = db.collection(db_mod.COLLECTIONS["TOKENS"])  # type: ignore
    waiting = tokens_ref.where("doctor", "==", doctor).where("status", "==", "waiting").get()
    confirmed = tokens_ref.where("doctor", "==", doctor).where("status", "==", "confirmed").get()
    pending = tokens_ref.where("doctor", "==", doctor).where("status", "==", "pending").get()
    return len(waiting) + len(confirmed) + len(pending)


def calculate_queue_length(doctor: str) -> int:
    # TODO: integrate with queue snapshot for real-time value
    return 0


def calculate_queue_velocity(doctor: str) -> float:
    db = get_db()
    now = datetime.utcnow()
    window_start = now - timedelta(hours=2)
    tokens_ref = db.collection(db_mod.COLLECTIONS["TOKENS"])  # type: ignore
    completed = tokens_ref.where("doctor", "==", doctor).where("status", "==", "completed").get()
    cnt = 0
    for doc in completed:
        data = doc.to_dict() or {}
        ts = data.get("completed_at") or data.get("updated_at")
        if ts and hasattr(ts, "timestamp"):
            dt = ts
        else:
            dt = None
        if dt and dt >= window_start:
            cnt += 1
    hours = max((now - window_start).total_seconds() / 3600.0, 0.01)
    return float(cnt) / float(hours)


def get_last_patient_duration(doctor: str) -> float:
    db = get_db()
    tokens_ref = db.collection(db_mod.COLLECTIONS["TOKENS"])  # type: ignore
    completed = tokens_ref.where("doctor", "==", doctor).where("status", "==", "completed").order_by("completed_at", direction="DESCENDING").limit(1).get()
    for doc in completed:
        dur = _extract_duration_minutes(doc.to_dict() or {})
        return dur
    return 0.0


def avg_last_5(doctor: str) -> float:
    return _avg_last_n(doctor, 5)


def avg_last_30(doctor: str) -> float:
    return _avg_last_n(doctor, 30)


def count_available_doctors() -> int:
    db = get_db()
    try:
        doctors_ref = db.collection(db_mod.COLLECTIONS["DOCTORS"])  # type: ignore
        available = doctors_ref.where("available", "==", True).get()
        return len(available)
    except Exception:
        return 1


def get_hour_history() -> float:
    return 0.0


def get_weekday_history() -> float:
    return 0.0


def get_doctor_history(doctor: str) -> float:
    db = get_db()
    tokens_ref = db.collection(db_mod.COLLECTIONS["TOKENS"])  # type: ignore
    completed = tokens_ref.where("doctor", "==", doctor).where("status", "==", "completed").order_by("completed_at", direction="DESCENDING").limit(200).get()
    durations: List[float] = []
    for doc in completed:
        durations.append(_extract_duration_minutes(doc.to_dict() or {}))
    if not durations:
        return 0.0
    return float(sum(durations) / len(durations))


def get_weather_code() -> int:
    db = get_db()
    try:
        ref = db.collection(db_mod.COLLECTIONS.get("WEATHER", "WEATHER")).document("current")  # type: ignore
        snap = ref.get()
        if snap.exists:
            data = snap.to_dict() or {}
            code = data.get("code")
            if isinstance(code, int):
                return code
    except Exception:
        pass
    return 0


def get_clinic_duration() -> float:
    start_of_day = datetime.combine(datetime.now().date(), datetime.min.time())
    return float((datetime.now() - start_of_day).total_seconds() / 60.0)


def _extract_duration_minutes(t: Dict[str, Any]) -> float:
    dur = t.get("service_duration")
    if isinstance(dur, (int, float)):
        return float(dur)
    started = t.get("started_at")
    completed = t.get("completed_at")
    if started and completed and hasattr(started, "timestamp") and hasattr(completed, "timestamp"):
        try:
            return float((completed - started).total_seconds() / 60.0)
        except Exception:
            return 0.0
    return 0.0


def _avg_last_n(doctor: str, n: int) -> float:
    db = get_db()
    tokens_ref = db.collection(db_mod.COLLECTIONS["TOKENS"])  # type: ignore
    completed = tokens_ref.where("doctor", "==", doctor).where("status", "==", "completed").order_by("completed_at", direction="DESCENDING").limit(n).get()
    durations: List[float] = []
    for doc in completed:
        durations.append(_extract_duration_minutes(doc.to_dict() or {}))
    if not durations:
        return 0.0
    return float(sum(durations) / len(durations))


@router.post("/predict-wait-time")
def predict_wait_time(req: AIPredictRequest):
    # STEP 6 — Calculate 13 backend features
    backend_features: Dict[str, Any] = {
        "hour_of_day": get_current_hour(),
        "day_of_week": get_current_day(),
        "patients_ahead_of_user": calculate_patients_ahead(req.doctor),
        "patients_in_queue": calculate_queue_length(req.doctor),
        "queue_velocity": calculate_queue_velocity(req.doctor),
        "last_patient_duration": get_last_patient_duration(req.doctor),
        "avg_service_time_last_5": avg_last_5(req.doctor),
        "avg_service_time_last_30": avg_last_30(req.doctor),
        "doctors_available": count_available_doctors(),
        "avg_wait_time_this_hour_past_week": get_hour_history(),
        "avg_wait_time_this_weekday_past_month": get_weekday_history(),
        "avg_service_time_doctor_history": get_doctor_history(req.doctor),
        "weather": get_weather_code(),
        "total_clinic_duration": get_clinic_duration(),
    }

    # Combine frontend + backend features according to AIEngine feature order
    input_data: Dict[str, Any] = {
        **backend_features,
        "doctor": req.doctor,
        "disease_type": req.disease_type,
        "age": req.age,
    }

    predicted_duration = ai_engine.predict_duration(input_data)

    estimated_wait = backend_features["patients_ahead_of_user"] * predicted_duration

    return {
        "predicted_consultation_duration": predicted_duration,
        "estimated_wait_time": round(float(estimated_wait), 2),
    }

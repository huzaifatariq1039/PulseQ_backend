from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.services.ai_engine import ai_engine
from app.database import get_db
from app.db_models import User, Doctor, Hospital, Token

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


def calculate_patients_ahead(doctor_id: str, db: Session) -> int:
    # Get today's tokens for this doctor that are in waiting/confirmed/pending status
    today = datetime.utcnow().date()
    count = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status.in_(["waiting", "confirmed", "pending"]),
        func.date(Token.appointment_date) == today
    ).count()
    return count


def calculate_queue_length(doctor_id: str, db: Session) -> int:
    """Returns the total number of patients currently in the queue for a doctor."""
    today = datetime.utcnow().date()
    return db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status.in_(["waiting", "confirmed", "pending", "called", "in_consultation"]),
        func.date(Token.appointment_date) == today
    ).count()


def calculate_queue_velocity(doctor_id: str, db: Session) -> float:
    now = datetime.utcnow()
    window_start = now - timedelta(hours=2)
    
    completed_count = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status == "completed",
        Token.completed_at >= window_start
    ).count()
    
    hours = max((now - window_start).total_seconds() / 3600.0, 0.01)
    return float(completed_count) / float(hours)


def get_last_patient_duration(doctor_id: str, db: Session) -> float:
    last_token = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status == "completed"
    ).order_by(Token.completed_at.desc()).first()
    
    if last_token:
        return _extract_duration_minutes(last_token)
    return 0.0


def avg_last_5(doctor_id: str, db: Session) -> float:
    return _avg_last_n(doctor_id, 5, db)


def avg_last_30(doctor_id: str, db: Session) -> float:
    return _avg_last_n(doctor_id, 30, db)


def count_available_doctors(db: Session) -> int:
    try:
        count = db.query(Doctor).filter(Doctor.status == "available").count()
        return max(count, 1)
    except Exception:
        return 1


def get_hour_history(db: Session) -> float:
    """Average duration for all doctors during the current hour of the day."""
    current_hour = get_current_hour()
    tokens = db.query(Token).filter(
        Token.status == "completed",
        func.extract('hour', Token.completed_at) == current_hour
    ).limit(100).all()
    
    durations = [_extract_duration_minutes(t) for t in tokens]
    if not durations:
        return 12.0 # Default fallback for empty history
    return float(sum(durations) / len(durations))


def get_weekday_history(db: Session) -> float:
    """Average duration for all doctors on the current day of the week."""
    current_day = get_current_day()
    tokens = db.query(Token).filter(
        Token.status == "completed",
        func.extract('dow', Token.completed_at) == current_day
    ).limit(100).all()
    
    durations = [_extract_duration_minutes(t) for t in tokens]
    if not durations:
        return 15.0 # Default fallback for empty history
    return float(sum(durations) / len(durations))


def get_doctor_history(doctor_id: str, db: Session) -> float:
    tokens = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status == "completed"
    ).order_by(Token.completed_at.desc()).limit(200).all()
    
    durations = [_extract_duration_minutes(t) for t in tokens]
    if not durations:
        return 0.0
    return float(sum(durations) / len(durations))


def get_weather_code() -> int:
    # TODO: Implement weather integration for PostgreSQL
    return 0


def get_clinic_duration() -> float:
    start_of_day = datetime.combine(datetime.now().date(), datetime.min.time())
    return float((datetime.now() - start_of_day).total_seconds() / 60.0)


def _extract_duration_minutes(t: Token) -> float:
    # Assuming duration fields exist in Token model
    if hasattr(t, 'duration_minutes') and t.duration_minutes:
        return float(t.duration_minutes)
    
    if t.started_at and t.completed_at:
        try:
            return float((t.completed_at - t.started_at).total_seconds() / 60.0)
        except Exception:
            return 0.0
    return 0.0


def _avg_last_n(doctor_id: str, n: int, db: Session) -> float:
    tokens = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status == "completed"
    ).order_by(Token.completed_at.desc()).limit(n).all()
    
    durations = [_extract_duration_minutes(t) for t in tokens]
    if not durations:
        return 0.0
    return float(sum(durations) / len(durations))


@router.post("/predict-wait-time")
def predict_wait_time(req: AIPredictRequest, db: Session = Depends(get_db)):
    # Calculate backend features using SQLAlchemy
    backend_features: Dict[str, Any] = {
        "hour_of_day": get_current_hour(),
        "day_of_week": get_current_day(),
        "patients_ahead_of_user": calculate_patients_ahead(req.doctor, db),
        "patients_in_queue": calculate_queue_length(req.doctor, db),
        "queue_velocity": calculate_queue_velocity(req.doctor, db),
        "last_patient_duration": get_last_patient_duration(req.doctor, db),
        "avg_service_time_last_5": avg_last_5(req.doctor, db),
        "avg_service_time_last_30": avg_last_30(req.doctor, db),
        "doctors_available": count_available_doctors(db),
        "avg_wait_time_this_hour_past_week": get_hour_history(db),
        "avg_wait_time_this_weekday_past_month": get_weekday_history(db),
        "avg_service_time_doctor_history": get_doctor_history(req.doctor, db),
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

from datetime import datetime, timedelta
from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.services.ai_engine import ai_engine
from app.database import get_db
from app.db_models import Token, Doctor

router = APIRouter()

# Global Trust Dial for the standalone endpoint
ALPHA = 0.6  

class AIPredictRequest(BaseModel):
    name: str
    age: int
    doctor: str
    disease_type: str

# --- Helper Functions ---
def get_current_hour() -> int:
    return datetime.now().hour

def get_current_day() -> int:
    # Monday=0 .. Sunday=6
    return datetime.now().weekday()

def calculate_patients_ahead(doctor_id: str, db: Session) -> int:
    today = datetime.utcnow().date()
    return db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status.in_(["waiting", "confirmed", "pending"]),
        func.date(Token.appointment_date) == today
    ).count()

def calculate_queue_length(doctor_id: str, db: Session) -> int:
    today = datetime.utcnow().date()
    return db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status.in_(["waiting", "confirmed", "pending", "called", "in_consultation"]),
        func.date(Token.appointment_date) == today
    ).count()

def calculate_completed_today(doctor_id: str, db: Session) -> int:
    today = datetime.utcnow().date()
    return db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status == "completed",
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

def avg_last_10(doctor_id: str, db: Session) -> float:
    return _avg_last_n(doctor_id, 10, db)

def count_available_doctors(db: Session) -> int:
    try:
        count = db.query(Doctor).filter(Doctor.status == "available").count()
        return max(count, 1)
    except Exception:
        return 1

def get_hour_history(db: Session) -> float:
    current_hour = get_current_hour()
    tokens = db.query(Token).filter(
        Token.status == "completed",
        func.extract('hour', Token.completed_at) == current_hour
    ).limit(100).all()
    durations = [_extract_duration_minutes(t) for t in tokens]
    return float(sum(durations) / len(durations)) if durations else 12.0

def get_weekday_history(db: Session) -> float:
    current_day = get_current_day()
    tokens = db.query(Token).filter(
        Token.status == "completed",
        func.extract('dow', Token.completed_at) == current_day
    ).limit(100).all()
    durations = [_extract_duration_minutes(t) for t in tokens]
    return float(sum(durations) / len(durations)) if durations else 15.0

def get_doctor_history(doctor_id: str, db: Session) -> float:
    tokens = db.query(Token).filter(
        Token.doctor_id == doctor_id,
        Token.status == "completed"
    ).order_by(Token.completed_at.desc()).limit(200).all()
    durations = [_extract_duration_minutes(t) for t in tokens]
    return float(sum(durations) / len(durations)) if durations else 0.0

def _extract_duration_minutes(t: Token) -> float:
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
    return float(sum(durations) / len(durations)) if durations else 0.0

# --- Endpoint ---
@router.post("/predict-wait-time")
def predict_wait_time(req: AIPredictRequest, db: Session = Depends(get_db)):
    patients_ahead = calculate_patients_ahead(req.doctor, db)
    completed_today = calculate_completed_today(req.doctor, db)

    # 1. PHASE 1: "Fast-Start" Override (No patients completed today yet)
    if completed_today == 0:
        estimated_wait = (patients_ahead + 1) * 5
        predicted_duration = 5.0

    # 2. PHASE 2: Live AI Engine
    else:
        doctor_history = get_doctor_history(req.doctor, db) or 10.0
        rolling_last_5 = avg_last_5(req.doctor, db) or doctor_history
        rolling_last_10 = avg_last_10(req.doctor, db) or doctor_history

        ai_input: Dict[str, Any] = {
            "hour_of_day": get_current_hour(),
            "day_of_week": get_current_day(),
            "patients_ahead_of_user": patients_ahead,
            "patients_in_queue": calculate_queue_length(req.doctor, db),
            "queue_length_last_10_min": 0, 
            "queue_velocity": calculate_queue_velocity(req.doctor, db),
            "last_patient_duration": get_last_patient_duration(req.doctor, db),
            "avg_service_time_last_5": rolling_last_5,
            "avg_service_time_last_10": rolling_last_10,
            "doctors_available": count_available_doctors(db),
            "doctor_type": "General Medicine", 
            "clinic_type": "General Medicine", 
            "avg_wait_time_this_hour_past_week": get_hour_history(db),
            "avg_wait_time_this_weekday_past_month": get_weekday_history(db),
            "avg_service_time_doctor_historic": doctor_history,
            "Name": req.name,
            "Doctor Name": req.doctor,
            "Service_Duration": 0, 
            "Disease": req.disease_type,
            "Age": req.age,
        }

        predicted_duration = ai_engine.predict_duration(ai_input)
        predicted_duration = max(predicted_duration, 3.5) 

        ai_eta = patients_ahead * predicted_duration
        heuristic_eta = patients_ahead * rolling_last_5
        estimated_wait = (ALPHA * ai_eta) + ((1 - ALPHA) * heuristic_eta)

    return {
        "predicted_consultation_duration": round(float(predicted_duration), 2),
        "estimated_wait_time": max(int(estimated_wait), 0),
    }
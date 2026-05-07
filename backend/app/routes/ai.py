from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.ai_engine import ai_engine
from app.database import get_db
from app.services.queue_management_service import (
    get_current_hour,
    get_current_day,
    calculate_patients_ahead,
    calculate_queue_length,
    calculate_completed_today,
    calculate_queue_velocity,
    get_last_patient_duration,
    avg_last_5,
    avg_last_10,
    count_available_doctors,
    get_hour_history,
    get_weekday_history,
    get_doctor_history,
)

router = APIRouter()

# Global Trust Dial for the standalone endpoint
ALPHA = 0.6  

class AIPredictRequest(BaseModel):
    name: str
    age: int
    doctor: str
    disease_type: str

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
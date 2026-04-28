# routers/ratings.py  — final version matching your exact db_models.py

from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List
import uuid

from app.database import get_db
from app.db_models import DoctorRating, Token, Doctor, User
from app.models import RatingCreate, RatingResponse, DoctorRatingSummary
from app.security import get_current_active_user
router = APIRouter(
    prefix="",
    tags=["Ratings"]
)


# ─── Helper ───────────────────────────────────────────────────────────────────

def _make_initials(name: str) -> str:
    parts = (name or "").strip().split()
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[-1][0]}".upper()
    return (name or "?")[0].upper()


def _recalculate_doctor_rating(doctor_id: str, db: Session):
    """Recalculate avg rating and review_count, write back to doctors table."""
    all_ratings = db.query(DoctorRating.rating)\
                    .filter(DoctorRating.doctor_id == doctor_id)\
                    .all()

    if not all_ratings:
        return

    values = [r.rating for r in all_ratings]
    avg    = round(sum(values) / len(values), 1)
    count  = len(values)

    db.query(Doctor)\
      .filter(Doctor.id == doctor_id)\
      .update({"rating": avg, "review_count": count})
    db.commit()


# ─── POST /api/ratings ────────────────────────────────────────────────────────

@router.post("", response_model=RatingResponse, status_code=201)
@router.post("/", response_model=RatingResponse, status_code=201)
def submit_rating(
    payload: RatingCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    # 1. Only patients can rate
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can submit ratings")

    patient_id = current_user.id

    # 2. Fetch the token
    token = db.query(Token).filter(Token.id == payload.token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Appointment token not found")

    # 3. Must belong to this patient
    if token.patient_id != patient_id:
        raise HTTPException(status_code=403, detail="You can only rate your own appointments")

    # 4. Must be completed
    if token.status != "completed":
        raise HTTPException(status_code=400, detail="You can only rate completed appointments")

    # 5. Not already rated
    if db.query(DoctorRating).filter_by(token_id=payload.token_id, patient_id=patient_id).first():
        raise HTTPException(status_code=400, detail="You have already rated this appointment")

    # 6. Fetch patient name for snapshot
    patient      = db.query(User).filter(User.id == patient_id).first()
    patient_name = patient.name if patient else "Unknown Patient"

    # 7. Save rating
    now        = datetime.utcnow()
    new_rating = DoctorRating(
        id                      = str(uuid.uuid4()),
        token_id                = payload.token_id,
        doctor_id               = token.doctor_id,
        patient_id              = patient_id,
        rating                  = payload.rating,
        review                  = payload.review,
        patient_name            = patient_name,
        patient_avatar_initials = _make_initials(patient_name),
        appointment_date        = token.appointment_date,
        created_at              = now,
        updated_at              = now,
    )
    db.add(new_rating)

    # 8. Mark token as rated
    token.is_rated = True
    token.rating   = payload.rating

    db.commit()
    db.refresh(new_rating)

    # 9. Recalculate doctor's average
    _recalculate_doctor_rating(token.doctor_id, db)

    return new_rating


# ─── GET /api/ratings/doctor/{doctor_id} ─────────────────────────────────────

@router.get("/doctor/{doctor_id}", response_model=DoctorRatingSummary)
def get_doctor_ratings(
    doctor_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    role = current_user.role
    if role not in ("doctor", "admin") and current_user.id != doctor_id:
        raise HTTPException(status_code=403, detail="Access denied")

    ratings = db.query(DoctorRating)\
                .filter(DoctorRating.doctor_id == doctor_id)\
                .order_by(DoctorRating.created_at.desc())\
                .all()

    avg = round(sum(r.rating for r in ratings) / len(ratings), 1) if ratings else 0.0

    return DoctorRatingSummary(
        doctor_id      = doctor_id,
        average_rating = avg,
        total_reviews  = len(ratings),
        ratings        = ratings
    )


# ─── GET /api/ratings/token/{token_id} ───────────────────────────────────────

@router.get("/token/{token_id}", response_model=RatingResponse)
def get_rating_by_token(
    token_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    rating = db.query(DoctorRating).filter(DoctorRating.token_id == token_id).first()
    if not rating:
        raise HTTPException(status_code=404, detail="No rating found for this appointment")
    return rating


# ─── GET /api/ratings/patient/me ─────────────────────────────────────────────

@router.get("/patient/me", response_model=List[RatingResponse])
def get_my_ratings(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Access denied")

    return db.query(DoctorRating)\
             .filter(DoctorRating.patient_id == current_user.id)\
             .order_by(DoctorRating.created_at.desc())\
             .all()
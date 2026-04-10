from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, status
from app.security import require_roles
from app.services.ai_engine import ai_engine
from app.schemas.ml_schema import PredictionRequest

router = APIRouter()


@router.post("/predict", dependencies=[Depends(require_roles("admin", "doctor", "patient"))])
async def predict(req: PredictionRequest) -> Dict[str, float]:
    """Predict consultation duration using the raw model. Role-protected (admin/doctor)."""
    # Ensure model is loaded
    model = getattr(ai_engine, "model", None)
    if model is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI model not loaded")

    # Validate features length
    if not isinstance(req.features, list) or len(req.features) != 17:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feature shape mismatch, expected length 17"
        )

    try:
        prediction = model.predict([req.features])
        value = float(prediction[0])
    except HTTPException:
        raise
    except Exception:
        # Avoid leaking model internals; return generic error
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Prediction failed")

    return {"predicted_consultation_duration": value}

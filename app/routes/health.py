from fastapi import APIRouter
from app.database import get_db
from app.services.ai_engine import ai_engine

router = APIRouter(tags=["Health"]) 

@router.get("/health")
async def health_check():
    db_connected = False
    try:
        db = get_db()
        # Light touch: attempt collection ref creation
        _ = db.collection("_health_check")
        db_connected = True
    except Exception:
        db_connected = False

    # Consider AI loaded if model object is present
    ml_loaded = getattr(ai_engine, "model", None) is not None

    return {"status": "ok", "ml_loaded": ml_loaded, "db_connected": db_connected}

from fastapi import APIRouter
from app.database import get_db, get_engine
from app.services.ai_engine import ai_engine
from sqlalchemy import text

router = APIRouter(tags=["Health"]) 

@router.get("/health")
async def health_check():
    db_connected = False
    db_error = None
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_connected = True
    except Exception as e:
        db_connected = False
        db_error = str(e)

    # Consider AI loaded if model object is present
    ml_loaded = getattr(ai_engine, "model", None) is not None

    return {
        "status": "ok", 
        "ml_loaded": ml_loaded, 
        "db_connected": db_connected,
        "db_error": db_error
    }

@router.get("/test-db")
async def test_db():
    """Test database connection with detailed output"""
    try:
        from app.config import DATABASE_URL
        # Mask password in URL for security
        masked_url = DATABASE_URL
        if "://" in masked_url:
            parts = masked_url.split("://")
            if "@" in parts[1]:
                creds, host = parts[1].split("@", 1)
                if ":" in creds:
                    user, _ = creds.split(":", 1)
                    masked_url = f"{parts[0]}://{user}:****@{host}"
        
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
        
        return {
            "status": "success",
            "database_url_masked": masked_url,
            "postgres_version": version
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

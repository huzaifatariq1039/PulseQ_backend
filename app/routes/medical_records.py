from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File
from typing import List, Optional, Dict, Any
from app.models import ActivityType
from app.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db_models import User, ActivityLog # Assuming MedicalRecord model exists
from app.security import get_current_active_user
from datetime import datetime, timedelta
import uuid

router = APIRouter(prefix="/medical-records", tags=["Medical Records"])

# Allowed content-types and limits for uploads (frontend can use /allowed-types)
ALLOWED_TYPES = ["image/jpeg", "image/png", "application/pdf"]
MAX_FILE_MB = 10  # hard limit to prevent very large uploads

async def create_activity_log(db: Session, user_id: str, activity_type: ActivityType, description: str, metadata: dict = None):
    """Helper function to create activity logs in PostgreSQL"""
    activity = ActivityLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        activity_type=activity_type.value if hasattr(activity_type, 'value') else str(activity_type),
        description=description,
        metadata=metadata or {},
        created_at=datetime.utcnow()
    )
    db.add(activity)
    db.commit()

@router.get("/")
async def get_medical_records(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get user's medical records with stats from PostgreSQL"""
    from app.db_models import MedicalRecord # Assuming it exists
    
    query = db.query(MedicalRecord).filter(MedicalRecord.user_id == current_user.user_id)
    records_objs = query.order_by(MedicalRecord.created_at.desc()).all()
    
    now = datetime.utcnow()
    recent_window = now - timedelta(days=30)
    
    records = []
    total_count = 0
    recent_count = 0
    follow_up_count = 0

    for r in records_objs:
        total_count += 1
        data = {k: v for k, v in r.__dict__.items() if not k.startswith('_')}
        
        if r.created_at and r.created_at >= recent_window:
            recent_count += 1
        if (data.get("record_type") or "").lower() == "follow_up":
            follow_up_count += 1
            
        records.append(data)
    
    return {
        "records": records,
        "total_records": total_count,
        "recent_records": recent_count,
        "follow_up_records": follow_up_count,
    }

@router.get("/stats")
async def get_medical_record_stats(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Return only the stats needed by the dashboard (Total, Recent, Follow-up)."""
    from app.db_models import MedicalRecord
    
    now = datetime.utcnow()
    recent_window = now - timedelta(days=30)
    
    total_count = db.query(MedicalRecord).filter(MedicalRecord.user_id == current_user.user_id).count()
    recent_count = db.query(MedicalRecord).filter(
        MedicalRecord.user_id == current_user.user_id,
        MedicalRecord.created_at >= recent_window
    ).count()
    follow_up_count = db.query(MedicalRecord).filter(
        MedicalRecord.user_id == current_user.user_id,
        func.lower(MedicalRecord.record_type) == 'follow_up'
    ).count()
    
    return {
        "total_records": total_count,
        "recent_records": recent_count,
        "follow_up_records": follow_up_count,
        "recent_window_days": 30,
    }

@router.get("/allowed-types")
async def get_allowed_types():
    """Return allowed content-types and size limits."""
    return {
        "allowed_content_types": ALLOWED_TYPES,
        "max_file_mb": MAX_FILE_MB,
        "notes": "Supported formats include JPEG, PNG, and PDF up to 10 MB"
    }

@router.post("/upload")
async def upload_medical_record(
    file: UploadFile = File(...),
    record_type: str = "general",
    description: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Upload a medical record file to PostgreSQL"""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, and PDF files are allowed"
        )
    
    contents = await file.read()
    size_bytes = len(contents or b"")
    max_bytes = MAX_FILE_MB * 1024 * 1024
    if size_bytes <= 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if size_bytes > max_bytes:
        raise HTTPException(status_code=400, detail=f"File is too large. Max size is {MAX_FILE_MB} MB")
    
    file_extension = file.filename.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    
    from app.db_models import MedicalRecord
    record_id = str(uuid.uuid4())
    new_record = MedicalRecord(
        id=record_id,
        user_id=current_user.user_id,
        filename=file.filename,
        file_path=f"medical_records/{current_user.user_id}/{unique_filename}",
        file_type=file.content_type,
        file_size=size_bytes,
        record_type=record_type,
        description=description,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(new_record)
    db.commit()
    
    await create_activity_log(
        db,
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        f"Medical record uploaded: {file.filename}",
        {
            "record_id": record_id,
            "filename": file.filename,
            "record_type": record_type
        }
    )
    
    # Inline stats calculation
    now = datetime.utcnow()
    recent_window = now - timedelta(days=30)
    total_count = db.query(MedicalRecord).filter(MedicalRecord.user_id == current_user.user_id).count()
    recent_count = db.query(MedicalRecord).filter(
        MedicalRecord.user_id == current_user.user_id,
        MedicalRecord.created_at >= recent_window
    ).count()
    follow_up_count = db.query(MedicalRecord).filter(
        MedicalRecord.user_id == current_user.user_id,
        func.lower(MedicalRecord.record_type) == 'follow_up'
    ).count()

    return {
        "message": "Medical record uploaded successfully",
        "record_id": record_id,
        "filename": unique_filename,
        "stats": {
            "total_records": total_count,
            "recent_records": recent_count,
            "follow_up_records": follow_up_count,
        }
    }

@router.delete("/{record_id}")
async def delete_medical_record(
    record_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Delete a medical record from PostgreSQL"""
    from app.db_models import MedicalRecord
    record = db.query(MedicalRecord).filter(MedicalRecord.id == record_id).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Medical record not found")
    
    if record.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    filename = record.filename
    db.delete(record)
    db.commit()
    
    await create_activity_log(
        db,
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        f"Medical record deleted: {filename}",
        {"record_id": record_id}
    )
    
    return {"message": "Medical record deleted successfully"}

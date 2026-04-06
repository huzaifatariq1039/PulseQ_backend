from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File
from typing import List, Optional
from app.models import ActivityType
from app.database import get_db
from app.config import COLLECTIONS
from app.security import get_current_active_user
from datetime import datetime
import uuid

router = APIRouter(prefix="/medical-records", tags=["Medical Records"])

# Allowed content-types and limits for uploads (frontend can use /allowed-types)
ALLOWED_TYPES = ["image/jpeg", "image/png", "application/pdf"]
MAX_FILE_MB = 10  # hard limit to prevent very large uploads

async def create_activity_log(user_id: str, activity_type: ActivityType, description: str, metadata: dict = None):
    """Helper function to create activity logs"""
    db = get_db()
    activities_ref = db.collection("activities")
    
    activity_ref = activities_ref.document()
    activity_data = {
        "id": activity_ref.id,
        "user_id": user_id,
        "activity_type": activity_type,
        "description": description,
        "metadata": metadata or {},
        "created_at": datetime.utcnow()
    }
    
    activity_ref.set(activity_data)

@router.get("/")
async def get_medical_records(current_user = Depends(get_current_active_user)):
    """Get user's medical records with stats for Total, Recent and Follow-up.

    - Total: all records owned by the user
    - Recent: records created in the last 30 days
    - Follow-up: records whose record_type == 'follow_up'
    """
    db = get_db()
    records_ref = db.collection("medical_records")
    
    # Use simple query to avoid composite index requirement
    query = records_ref.where("user_id", "==", current_user.user_id)
    
    records = []
    record_docs = []
    
    # Get all documents first
    for doc in query.stream():
        record_data = doc.to_dict()
        record_data["doc_id"] = doc.id
        record_docs.append(record_data)
    
    # Sort in memory by created_at descending
    record_docs.sort(key=lambda x: x.get("created_at", datetime.min), reverse=True)
    
    # Compute stats
    from datetime import timedelta
    now = datetime.utcnow()
    recent_window = now - timedelta(days=30)
    total_count = 0
    recent_count = 0
    follow_up_count = 0

    for record_data in record_docs:
        total_count += 1
        try:
            created_at = record_data.get("created_at")
            # Firestore timestamp compatibility
            to_dt = getattr(created_at, 'to_datetime', None)
            created_dt = to_dt() if callable(to_dt) else created_at
        except Exception:
            created_dt = None
        if created_dt and created_dt >= recent_window:
            recent_count += 1
        if (record_data.get("record_type") or "").lower() == "follow_up":
            follow_up_count += 1
        records.append(record_data)
    
    return {
        "records": records,
        "total_records": total_count,
        "recent_records": recent_count,
        "follow_up_records": follow_up_count,
    }

@router.get("/stats")
async def get_medical_record_stats(current_user = Depends(get_current_active_user)):
    """Return only the stats needed by the dashboard (Total, Recent, Follow-up)."""
    db = get_db()
    records_ref = db.collection("medical_records").where("user_id", "==", current_user.user_id)
    docs = [d.to_dict() for d in records_ref.stream()]
    from datetime import timedelta
    now = datetime.utcnow()
    recent_window = now - timedelta(days=30)
    total_count = len(docs)
    def _to_dt(v):
        try:
            to_dt = getattr(v, 'to_datetime', None)
            return to_dt() if callable(to_dt) else v
        except Exception:
            return None
    recent_count = sum(1 for d in docs if (_to_dt(d.get('created_at')) or datetime.min) >= recent_window)
    follow_up_count = sum(1 for d in docs if (d.get('record_type') or '').lower() == 'follow_up')
    return {
        "total_records": total_count,
        "recent_records": recent_count,
        "follow_up_records": follow_up_count,
        "recent_window_days": 30,
    }

@router.get("/allowed-types")
async def get_allowed_types():
    """Return allowed content-types and size limits so the app can show a PDF option."""
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
    current_user = Depends(get_current_active_user)
):
    """Upload a medical record file"""
    # Validate file type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, and PDF files are allowed"
        )
    # Validate file size (read into memory since we don't persist the actual file here)
    try:
        contents = await file.read()
        size_bytes = len(contents or b"")
        max_bytes = MAX_FILE_MB * 1024 * 1024
        if size_bytes <= 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        if size_bytes > max_bytes:
            raise HTTPException(status_code=400, detail=f"File is too large. Max size is {MAX_FILE_MB} MB")
    finally:
        try:
            await file.seek(0)
        except Exception:
            pass
    
    # Generate unique filename
    file_extension = file.filename.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    
    # In a real implementation, you would upload to cloud storage (Firebase Storage, AWS S3, etc.)
    # For now, we'll just store metadata
    
    db = get_db()
    records_ref = db.collection("medical_records")
    record_ref = records_ref.document()
    
    record_data = {
        "id": record_ref.id,
        "user_id": current_user.user_id,
        "filename": file.filename,
        "file_path": f"medical_records/{current_user.user_id}/{unique_filename}",
        "file_type": file.content_type,
        "file_size": size_bytes,
        "record_type": record_type,
        "description": description,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    record_ref.set(record_data)
    
    # Create activity log
    await create_activity_log(
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        f"Medical record uploaded: {file.filename}",
        {
            "record_id": record_ref.id,
            "filename": file.filename,
            "record_type": record_type
        }
    )
    
    # Compute updated stats to return inline
    try:
        from datetime import timedelta
        now = datetime.utcnow()
        recent_window = now - timedelta(days=30)
        docs = [d.to_dict() for d in db.collection("medical_records").where("user_id", "==", current_user.user_id).stream()]
        total_count = len(docs)
        def _to_dt(v):
            try:
                to_dt = getattr(v, 'to_datetime', None)
                return to_dt() if callable(to_dt) else v
            except Exception:
                return None
        recent_count = sum(1 for d in docs if (_to_dt(d.get('created_at')) or datetime.min) >= recent_window)
        follow_up_count = sum(1 for d in docs if (d.get('record_type') or '').lower() == 'follow_up')
    except Exception:
        total_count = None
        recent_count = None
        follow_up_count = None

    return {
        "message": "Medical record uploaded successfully",
        "record_id": record_ref.id,
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
    current_user = Depends(get_current_active_user)
):
    """Delete a medical record"""
    db = get_db()
    record_ref = db.collection("medical_records").document(record_id)
    record_doc = record_ref.get()
    
    if not record_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medical record not found"
        )
    
    record_data = record_doc.to_dict()
    
    # Check if user owns this record
    if record_data.get("user_id") != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Delete record
    record_ref.delete()
    
    # Create activity log
    await create_activity_log(
        current_user.user_id,
        ActivityType.PROFILE_UPDATED,
        f"Medical record deleted: {record_data.get('filename')}",
        {"record_id": record_id}
    )
    
    return {"message": "Medical record deleted successfully"}

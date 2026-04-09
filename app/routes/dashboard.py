from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models import (
    DashboardData, UserStatistics, ActivityLog as ActivityLogModel, ActivityLogCreate,
    QuickAction as QuickActionModel, QuickActionCreate, ActivityType,
    HospitalResponse, HospitalSearchResponse,
    HospitalLite, HospitalUnifiedSearchResponse,
)
from app.database import get_db
from app.db_models import User, Token, ActivityLog, QuickAction, Hospital, Doctor
from app.security import get_current_active_user
from datetime import datetime, timedelta
from app.services.token_service import SmartTokenService
import math
from time import time
import httpx

# Simple in-memory cache with TTL (best-effort, per-process)
_CACHE_TTL_SECONDS = 30
_cache_store: dict[str, tuple[float, object]] = {}

def _cache_get(key: str):
    try:
        exp, val = _cache_store.get(key, (0.0, None))
        if exp >= time():
            return val
        # expired
        if key in _cache_store:
            del _cache_store[key]
        return None
    except Exception:
        return None

def _cache_set(key: str, val: object, ttl: int = _CACHE_TTL_SECONDS):
    try:
        _cache_store[key] = (time() + ttl, val)
    except Exception:
        pass

def _cache_invalidate_prefix(prefix: str) -> int:
    """Invalidate cache entries whose keys start with the given prefix.

    Returns the number of removed keys.
    """
    removed = 0
    try:
        for k in list(_cache_store.keys()):
            if k.startswith(prefix):
                del _cache_store[k]
                removed += 1
    except Exception:
        return removed
    return removed

def invalidate_dashboard_cache_for_user(user_id: str) -> int:
    """Invalidate cached dashboard data for a specific user.

    This clears both the main dashboard payload and any cached nearby hospitals
    derived for the dashboard for the given user.
    """
    total_removed = 0
    total_removed += _cache_invalidate_prefix(f"dashboard:root:{user_id}")
    total_removed += _cache_invalidate_prefix(f"dashboard:nearby:{user_id}")
    total_removed += _cache_invalidate_prefix(f"dashboard:nearby_unified:{user_id}")
    return total_removed

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the distance between two points on the Earth's surface using the Haversine formula.

    Args:
        lat1 (float): Latitude of the first point.
        lon1 (float): Longitude of the first point.
        lat2 (float): Latitude of the second point.
        lon2 (float): Longitude of the second point.

    Returns:
        float: Distance between the two points in kilometers.
    """
    earth_radius = 6371  # kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) * math.sin(dlat / 2) + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dlon / 2) * math.sin(dlon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = earth_radius * c
    return distance

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("")
@router.get("/")
async def get_dashboard_data(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get complete dashboard data for the current user"""
    # Try cache first
    cache_key = f"dashboard:root:{current_user.user_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    # Get user data
    user = db.query(User).filter(User.id == current_user.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user_data = {k: v for k, v in user.__dict__.items() if not k.startswith('_')}
    user_data.pop("password", None)
    
    # Get statistics
    statistics = await get_user_statistics(current_user.user_id, db=db)
    
    # Get recent activities
    recent_activities = await get_recent_activities(current_user.user_id, limit=5, db=db)
    
    # Get quick actions
    quick_actions = await get_user_quick_actions(current_user.user_id, db=db)
    
    # Get recent tokens
    recent_tokens = await get_recent_tokens(current_user.user_id, limit=3, db=db)
    
    result = DashboardData(
        user=user_data,
        statistics=statistics,
        recent_activities=recent_activities,
        quick_actions=quick_actions,
        recent_tokens=recent_tokens
    )

    _cache_set(cache_key, result)
    return result

@router.get("/active-overview")
async def get_dashboard_active_overview(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Return the user's active token overview for Dashboard tiles:

    - active token visible label
    - queue_position (1-based, 0 if future appointment)
    - estimated_wait_time (minutes)
    - total_patients (queue size)
    - token_status and appointment_time
    - now_serving (current token from queue if available)

    This endpoint is focused on live token/queue metrics for the dashboard and intentionally
    does NOT return nearby hospitals. Nearby hospitals are for the Search page via
    `/hospitals/search-unified`.
    """
    tokens = db.query(Token).filter(Token.patient_id == current_user.user_id).all()

    if not tokens:
        return {"token": None, "queue": None}

    # Pick the most recent non-cancelled/non-completed token
    candidates = []
    for t in tokens:
        data = {k: v for k, v in t.__dict__.items() if not k.startswith('_')}
        status_val = str(data.get("status") or "").lower()
        if status_val not in ["cancelled", "completed"]:
            candidates.append(data)
    if not candidates:
        return {"token": None, "queue": None}

    candidates.sort(key=lambda x: x.get("updated_at") or x.get("created_at"), reverse=True)
    token = candidates[0]

    # Visible token label (align with tokens endpoints)
    def _visible_token_label(t: dict) -> str:
        for k in ("display_code", "displayCode"):
            v = t.get(k)
            if v:
                return str(v)
        # Prefer formatting numeric token numbers as A-XXX
        for k in ("token_number", "tokenNumber"):
            v = t.get(k)
            if v is None:
                continue
            try:
                # If already formatted like A-001, keep as-is
                sv = str(v)
                if "-" in sv and any(ch.isalpha() for ch in sv):
                    return sv
                return SmartTokenService.format_token(int(v))
            except Exception:
                return str(v)
        for k in ("display_number", "displayNumber"):
            v = t.get(k)
            if v:
                return str(v)
        for k in ("hex_code", "hexCode", "code"):
            v = t.get(k)
            if v:
                return str(v)
        tid = t.get("id")
        return tid[-8:].upper() if tid else "—"

    visible = _visible_token_label(token)

    # Live queue status
    queue_status = SmartTokenService.get_queue_status(
        token.get("doctor_id"),
        token.get("token_number"),
        appointment_date=token.get("appointment_date")
    ) or {}

    doctor_unavailable = bool(queue_status.get("doctor_unavailable"))

    try:
        people_ahead = 0 if doctor_unavailable else int(queue_status.get("people_ahead") or 0)
    except Exception:
        people_ahead = 0
    is_future = bool(queue_status.get("is_future_appointment"))
    queue_position = 0 if (doctor_unavailable or is_future) else (people_ahead + 1)

    estimated_wait_time = None if doctor_unavailable else queue_status.get("estimated_wait_time")
    if estimated_wait_time is not None:
        try:
            estimated_wait_time = int(estimated_wait_time)
        except Exception:
            estimated_wait_time = None

    overview = {
        "token_id": token.get("id"),
        "visible_token": visible,
        "token_status": token.get("status"),
        "appointment_time": token.get("appointment_date"),
        "doctor_unavailable": doctor_unavailable,
        "queue_position": queue_position,
        "people_ahead": people_ahead,
        "estimated_wait_time": estimated_wait_time,
        "total_patients": int(queue_status.get("total_queue") or 0),
        "now_serving": queue_status.get("current_token"),
        # Additional UI-friendly fields (does not break existing clients)
        "your_token": {
            "label": visible,
            "status": str(token.get("status") or "").lower() or None,
            "estimated_wait_minutes": estimated_wait_time,
            "queue_position": queue_position,
        },
        "doctor": {
            "id": token.get("doctor_id"),
            "name": token.get("doctor_name")
        },
        "hospital": {
            "id": token.get("hospital_id"),
            "name": token.get("hospital_name")
        }
    }

    # Live Status convenience: expected time based on ETA
    if estimated_wait_time is None:
        overview["expected_time"] = None
        overview["expected_time_label"] = "Doctor unavailable"
    else:
        try:
            eta_min = int(estimated_wait_time)
        except Exception:
            eta_min = 0
        expected_dt = datetime.utcnow() + timedelta(minutes=max(0, eta_min))
        overview["expected_time"] = expected_dt.isoformat() + "Z"
        try:
            overview["expected_time_label"] = expected_dt.strftime("%I:%M %p")
        except Exception:
            overview["expected_time_label"] = ""

    # Live Status convenience: formatted now serving label
    try:
        curr_num2 = queue_status.get("current_token")
        overview["now_serving_label"] = SmartTokenService.format_token(int(curr_num2)) if curr_num2 is not None else None
    except Exception:
        overview["now_serving_label"] = None

    # Currently serving card (format A-XXX + doctor dept/room)
    currently_serving = None
    try:
        curr_num = queue_status.get("current_token")
        if curr_num is not None:
            curr_label = SmartTokenService.format_token(int(curr_num))
        else:
            curr_label = None
    except Exception:
        curr_label = None

    doctor_meta = {}
    try:
        did = token.get("doctor_id")
        if did:
            doctor_obj = db.query(Doctor).filter(Doctor.id == str(did)).first()
            if doctor_obj:
                doctor_meta = {k: v for k, v in doctor_obj.__dict__.items() if not k.startswith('_')}
    except Exception:
        doctor_meta = {}

    if curr_label:
        currently_serving = {
            "token": curr_label,
            "department": doctor_meta.get("specialization") or doctor_meta.get("department"),
            "room": doctor_meta.get("room") or doctor_meta.get("room_number"),
            "doctor_name": doctor_meta.get("name") or token.get("doctor_name"),
        }
    overview["currently_serving"] = currently_serving

    # Hospital updates card (best-effort)
    hospital_updates = {
        "title": "Hospital Updates",
        "message": "Please arrive 10 minutes before your estimated time. Wearing a mask is recommended in the waiting area.",
        "cta": "View Live Screen",
    }
    try:
        hid = token.get("hospital_id")
        if hid:
            hospital_obj = db.query(Hospital).filter(Hospital.id == str(hid)).first()
            if hospital_obj:
                msg = hospital_obj.updates or hospital_obj.update_message or hospital_obj.notice or hospital_obj.announcement
                if isinstance(msg, str) and msg.strip():
                    hospital_updates["message"] = msg.strip()
    except Exception:
        pass
    overview["hospital_updates"] = hospital_updates

    return {"token": overview, "queue": queue_status}

@router.get("/nearby-hospitals-unified", response_model=HospitalUnifiedSearchResponse)
async def get_dashboard_nearby_hospitals_unified(
    current_user = Depends(get_current_active_user),
    # Accept multiple aliases
    lat: Optional[float] = Query(None, description="User latitude (alias 1)"),
    lng: Optional[float] = Query(None, description="User longitude (alias 1)"),
    user_lat: Optional[float] = Query(None, description="User latitude (alias 2)"),
    user_lng: Optional[float] = Query(None, description="User longitude (alias 2)"),
    latitude: Optional[float] = Query(None, description="User latitude (alias 3)"),
    longitude: Optional[float] = Query(None, description="User longitude (alias 3)"),
    radius_km: float = Query(50.0, gt=0, le=200, description="Search radius (km) for nearby"),
    limit: int = Query(20, ge=1, le=100, description="Max hospitals to return"),
    city: Optional[str] = Query(None, description="Optional city filter for DB entries (unused when include_db=False)"),
    include_db: bool = Query(True, description="Include SmartToken database hospitals (default: True)"),
    include_osm: bool = Query(True, description="Include OSM nearby hospitals (live GPS)"),
    db: Session = Depends(get_db),
):
    """Unified nearby hospitals for the dashboard (DB + OSM), de-duplicated.

    - Uses Overpass for OSM when coordinates provided
    - Includes DB hospitals by default, with distance calculated for display
    - Sorted: nearby first (by distance), then DB by name
    """
    # Coalesce coordinate aliases
    lat_val = user_lat if user_lat is not None else (lat if lat is not None else latitude)
    lng_val = user_lng if user_lng is not None else (lng if lng is not None else longitude)

    # Require coordinates for live nearby
    if lat_val is None or lng_val is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location required. Please pass lat and lng from device GPS for nearby hospitals.")

    cache_key = (
        f"dashboard:nearby_unified:{current_user.user_id}:lat={lat_val}:lng={lng_val}:r={radius_km}:l={limit}:"
        f"city={(city or '').strip().lower()}:db={include_db}:osm={include_osm}"
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    items: list[HospitalLite] = []

    # 1) DB hospitals (optional)
    if include_db:
        hospitals = db.query(Hospital).limit(300).all()
        for h_obj in hospitals:
            h = {k: v for k, v in h_obj.__dict__.items() if not k.startswith('_')}
            if city and h.get("city", "").lower() != city.lower():
                continue
            # Compute distance if coords provided
            dist = None
            if lat_val is not None and lng_val is not None and h.get("latitude") and h.get("longitude"):
                try:
                    dist = calculate_distance(lat_val, lng_val, h["latitude"], h["longitude"])  # type: ignore[arg-type]
                    h["distance_km"] = round(dist, 1)
                    h["estimated_time_minutes"] = int((h["distance_km"] or 0) * 2)
                except Exception:
                    dist = None
            # If coordinates are provided, enforce radius filtering for dashboard
            if lat_val is not None and lng_val is not None:
                if dist is None or dist > radius_km:
                    # Skip DB entries outside the nearby radius for dashboard view
                    continue
            items.append(HospitalLite(
                id=h.get("id"),
                name=h.get("name", "Hospital"),
                address=h.get("address"),
                city=h.get("city"),
                state=h.get("state"),
                latitude=h.get("latitude"),
                longitude=h.get("longitude"),
                distance_km=h.get("distance_km"),
                estimated_time_minutes=h.get("estimated_time_minutes"),
                rating=h.get("rating"),
                review_count=h.get("review_count", 0),
                status=h.get("status"),
                source="db",
                is_nearby=(lat_val is not None and lng_val is not None),
                is_database=True,
            ))

    # 2) OSM nearby logic...
    if include_osm and lat_val is not None and lng_val is not None:
        overpass_url = "https://overpass-api.de/api/interpreter"
        radius_m = int(radius_km * 1000)
        query_overpass = f"""
        [out:json][timeout:25];
        (
          node["amenity"="hospital"](around:{radius_m},{lat_val},{lng_val});
          way["amenity"="hospital"](around:{radius_m},{lat_val},{lng_val});
          relation["amenity"="hospital"](around:{radius_m},{lat_val},{lng_val});
        );
        out center;
        """
        overpass_ok = False
        try:
            async with httpx.AsyncClient(headers={"User-Agent": "SmartTokenApp/1.0"}, timeout=20) as client:
                resp = await client.get(overpass_url, params={"data": query_overpass})
                data = resp.json()
            for el in data.get("elements", []):
                tags = el.get("tags", {})
                name = tags.get("name") or "Unknown Hospital"
                olat = el.get("lat") or el.get("center", {}).get("lat")
                olng = el.get("lon") or el.get("center", {}).get("lon")
                if olat is None or olng is None:
                    continue
                try:
                    dist_km = round(calculate_distance(lat_val, lng_val, float(olat), float(olng)), 1)
                    eta = int(dist_km * 2)
                except Exception:
                    dist_km = None
                    eta = None
                items.append(HospitalLite(
                    id=str(el.get("id")),
                    name=name,
                    address=tags.get("addr:street"),
                    city=tags.get("addr:city"),
                    state=tags.get("addr:state"),
                    latitude=float(olat),
                    longitude=float(olng),
                    distance_km=dist_km,
                    estimated_time_minutes=eta,
                    rating=None,
                    review_count=0,
                    status=None,
                    source="osm_overpass",
                    is_nearby=True,
                    is_database=False,
                ))
            overpass_ok = len(data.get("elements", [])) > 0
        except Exception:
            overpass_ok = False

        if not overpass_ok:
            try:
                nominatim_url = "https://nominatim.openstreetmap.org/search"
                params = {
                    "q": "hospital",
                    "format": "json",
                    "limit": "50",
                    "lat": str(lat_val),
                    "lon": str(lng_val),
                    "addressdetails": "1",
                    "extratags": "1",
                }
                async with httpx.AsyncClient(headers={"User-Agent": "SmartTokenApp/1.0"}, timeout=20) as client:
                    resp2 = await client.get(nominatim_url, params=params)
                    data2 = resp2.json()
                for it in (data2 if isinstance(data2, list) else []):
                    try:
                        olat = float(it.get("lat"))
                        olng = float(it.get("lon"))
                    except Exception:
                        continue
                    try:
                        dist_km = round(calculate_distance(lat_val, lng_val, olat, olng), 1)
                        if dist_km is not None and dist_km > radius_km:
                            continue
                        eta = int(dist_km * 2) if dist_km is not None else None
                    except Exception:
                        dist_km = None
                        eta = None
                    name = it.get("display_name") or "Unknown Hospital"
                    addr = None
                    if isinstance(it.get("address"), dict):
                        addr = it["address"].get("road")
                    items.append(HospitalLite(
                        id=str(it.get("osm_id") or it.get("place_id")),
                        name=name,
                        address=addr,
                        city=(it.get("address", {}) or {}).get("city") if isinstance(it.get("address"), dict) else None,
                        state=(it.get("address", {}) or {}).get("state") if isinstance(it.get("address"), dict) else None,
                        latitude=olat,
                        longitude=olng,
                        distance_km=dist_km,
                        estimated_time_minutes=eta,
                        rating=None,
                        review_count=0,
                        status=None,
                        source="osm_nominatim",
                        is_nearby=True,
                        is_database=False,
                    ))
            except Exception:
                pass

    # 3) De-duplicate by name+city preferring DB
    def _key(it: HospitalLite) -> str:
        nm = (it.name or "").strip().lower()
        ct = (it.city or "").strip().lower()
        return f"{nm}|{ct}"

    dedup: dict[str, HospitalLite] = {}
    for it in items:
        k = _key(it)
        if k not in dedup:
            dedup[k] = it
        else:
            if dedup[k].is_database is False and it.is_database is True:
                dedup[k] = it

    merged = list(dedup.values())

    # Sort: nearby first, then DB by name
    def _sort_key(m: HospitalLite):
        if m.is_nearby:
            return (0, m.distance_km or 1e9)
        return (1, (m.name or "").lower())

    merged.sort(key=_sort_key)
    merged = merged[:limit]

    result = HospitalUnifiedSearchResponse(
        hospitals=merged,
        total_found=len(merged),
        search_query=f"lat={lat_val},lng={lng_val},radius_km={radius_km}"
    )
    _cache_set(cache_key, result)
    return result

@router.get("/statistics", response_model=UserStatistics)
async def get_user_statistics_endpoint(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get user statistics"""
    return await get_user_statistics(current_user.user_id, db=db)

async def get_user_statistics(user_id: str, db: Session = None) -> UserStatistics:
    """Calculate user statistics"""
    if db is None:
        db = next(get_db())
    
    user_tokens = db.query(Token).filter(Token.patient_id == user_id).all()
    
    total_tokens = len(user_tokens)
    
    # Filter active and completed tokens in memory
    today = datetime.now().date()
    active_tokens = 0
    completed_appointments = 0
    
    for token in user_tokens:
        appointment_date = token.appointment_date
        
        if appointment_date:
            if isinstance(appointment_date, datetime):
                appt_date = appointment_date.date()
            else:
                appt_date = appointment_date
            
            if appt_date >= today:
                active_tokens += 1
            else:
                completed_appointments += 1
    
    # Get payment statistics
    pending_payments = 0
    total_payments = 0
    
    for token in user_tokens:
        payment_status = str(token.payment_status or "pending").lower()
        
        if payment_status == "pending":
            pending_payments += 1
        
        if payment_status in ["completed", "processing", "paid"]:
            total_payments += 1
    
    return UserStatistics(
        total_tokens=total_tokens,
        active_tokens=active_tokens,
        completed_appointments=completed_appointments,
        total_payments=total_payments,
        pending_payments=pending_payments
    )

@router.get("/activities", response_model=List[ActivityLogModel])
async def get_user_activities(
    current_user = Depends(get_current_active_user),
    limit: int = Query(10, ge=1, le=50),
    activity_type: Optional[ActivityType] = None,
    db: Session = Depends(get_db),
):
    """Get user activity logs"""
    return await get_recent_activities(current_user.user_id, limit, activity_type, db=db)

async def get_recent_activities(user_id: str, limit: int = 10, activity_type: Optional[ActivityType] = None, db: Session = None) -> List[ActivityLogModel]:
    """Get recent activities for a user"""
    if db is None:
        db = next(get_db())
    
    query = db.query(ActivityLog).filter(ActivityLog.user_id == user_id)
    if activity_type:
        query = query.filter(ActivityLog.activity_type == activity_type)
    
    activities_objs = query.order_by(ActivityLog.created_at.desc()).limit(limit).all()
    
    activities = []
    for obj in activities_objs:
        activity_data = {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
        # Explicitly map meta_data (DB name) to metadata (Pydantic model name)
        if "meta_data" in activity_data:
            activity_data["metadata"] = activity_data.pop("meta_data")
        activities.append(ActivityLogModel(**activity_data))
    
    return activities

@router.post("/activities", response_model=ActivityLogModel)
async def create_activity_log_endpoint(
    activity: ActivityLogCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Create a new activity log entry"""
    import uuid
    activity_id = str(uuid.uuid4())
    activity_data = activity.dict()
    activity_data["id"] = activity_id
    activity_data["user_id"] = current_user.user_id
    activity_data["created_at"] = datetime.utcnow()
    
    new_activity = ActivityLog(**activity_data)
    db.add(new_activity)
    db.commit()
    db.refresh(new_activity)
    
    return ActivityLogModel(**activity_data)

@router.get("/quick-actions", response_model=List[QuickActionModel])
async def get_user_quick_actions_endpoint(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Get user's quick actions"""
    return await get_user_quick_actions(current_user.user_id, db=db)

async def get_user_quick_actions(user_id: str, db: Session = None) -> List[QuickActionModel]:
    """Get quick actions for a user"""
    if db is None:
        db = next(get_db())
    
    # Get user-specific actions first
    user_actions_objs = db.query(QuickAction).filter(QuickAction.user_id == user_id).all()
    user_actions = [{k: v for k, v in obj.__dict__.items() if not k.startswith('_')} for obj in user_actions_objs]
    
    # If no user-specific actions, get default actions
    if not user_actions:
        default_actions = [
            {
                "id": "generate_token",
                "user_id": user_id,
                "action_type": "generate_token",
                "title": "Generate Token",
                "description": "Create a new SmartToken for appointment",
                "icon": "ticket",
                "route": "/tokens/generate",
                "is_enabled": True,
                "created_at": datetime.utcnow()
            },
            {
                "id": "my_tokens",
                "user_id": user_id,
                "action_type": "view_tokens",
                "title": "My Tokens",
                "description": "View all your SmartTokens",
                "icon": "list",
                "route": "/tokens/my-tokens",
                "is_enabled": True,
                "created_at": datetime.utcnow()
            },
            {
                "id": "find_hospitals",
                "user_id": user_id,
                "action_type": "find_hospitals",
                "title": "Find Hospitals",
                "description": "Search for nearby hospitals",
                "icon": "hospital",
                "route": "/hospitals/search",
                "is_enabled": True,
                "created_at": datetime.utcnow()
            },
            {
                "id": "profile",
                "user_id": user_id,
                "action_type": "profile",
                "title": "Profile",
                "description": "Update your profile information",
                "icon": "user",
                "route": "/auth/me",
                "is_enabled": True,
                "created_at": datetime.utcnow()
            }
        ]
        
        # Save default actions
        for action_data in default_actions:
            import uuid
            action_data["id"] = str(uuid.uuid4())
            new_action = QuickAction(**action_data)
            db.add(new_action)
            user_actions.append(action_data)
        db.commit()
    
    return [QuickActionModel(**action) for action in user_actions]

@router.post("/quick-actions", response_model=QuickActionModel)
async def create_quick_action(
    action: QuickActionCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Create a new quick action for the user"""
    import uuid
    action_id = str(uuid.uuid4())
    action_data = action.dict()
    action_data["id"] = action_id
    action_data["user_id"] = current_user.user_id
    action_data["created_at"] = datetime.utcnow()
    
    new_action = QuickAction(**action_data)
    db.add(new_action)
    db.commit()
    db.refresh(new_action)
    
    return QuickActionModel(**action_data)

@router.put("/quick-actions/{action_id}")
async def update_quick_action(
    action_id: str,
    is_enabled: bool,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Update quick action status"""
    action_obj = db.query(QuickAction).filter(QuickAction.id == action_id).first()
    
    if not action_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quick action not found"
        )
    
    if action_obj.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    action_obj.is_enabled = is_enabled
    db.commit()
    
    return {"message": "Quick action updated successfully"}

async def get_recent_tokens(user_id: str, limit: int = 3, db: Session = None) -> List[dict]:
    """Get recent tokens for a user"""
    if db is None:
        db = next(get_db())
    
    tokens_objs = db.query(Token).filter(Token.patient_id == user_id).order_by(Token.created_at.desc()).limit(limit).all()
    
    tokens = []
    for obj in tokens_objs:
        token_data = {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
        tokens.append(token_data)
    
    return tokens

@router.get("/recent-tokens")
async def get_recent_tokens_endpoint(
    current_user = Depends(get_current_active_user),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Get recent tokens for the current user"""
    return await get_recent_tokens(current_user.user_id, limit, db=db)

@router.get("/active-token")
async def get_active_token(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Return the most recent active token for today with live queue status.

    Changes:
    - Compare by calendar day only (date-based) to avoid timezone issues hiding same-day tokens.
    - Include a precomputed `visible_token` that prefers `display_code`, then `token_number`, then safe fallbacks.
    """
    tokens = db.query(Token).filter(Token.patient_id == current_user.user_id).all()

    if not tokens:
        return {"token": None, "queue": None}

    # Use local server date; compare by date only (ignore time/tz)
    today = datetime.now().date()

    # Filter to today's tokens that are not cancelled/completed, then pick latest by created_at
    active_today = []
    for t in tokens:
        data = {k: v for k, v in t.__dict__.items() if not k.startswith('_')}
        appt = data.get("appointment_date")
        appt_date = None
        if appt is not None:
            try:
                if isinstance(appt, datetime):
                    appt_date = appt.date()
                else:
                    appt_date = datetime.fromisoformat(str(appt).replace('Z', '+00:00')).date()
            except Exception:
                appt_date = None

        status_val = str(data.get("status") or "").lower()
        if (appt_date == today) and (status_val not in ["cancelled", "completed"]):
            active_today.append(data)

    if not active_today:
        return {"token": None, "queue": None}

    active_today.sort(key=lambda x: x.get("created_at") or datetime.min, reverse=True)
    token_data = active_today[0]

    # Get live queue status for this token
    queue_status = SmartTokenService.get_queue_status(
        token_data["doctor_id"],
        token_data["token_number"]
    )

    # Precompute a visible token label for dashboard tile
    def _visible_token_label(t: dict) -> str:
        for k in ("display_code", "displayCode"):
            v = t.get(k)
            if v:
                return str(v)
        for k in ("token_number", "tokenNumber", "display_number", "displayNumber"):
            v = t.get(k)
            if v:
                try:
                    return SmartTokenService.format_token(int(v))
                except Exception:
                    return str(v)
        for k in ("hex_code", "hexCode", "code"):
            v = t.get(k)
            if v:
                return str(v)
        return "—"

    # Attach label without mutating stored record
    token_view = dict(token_data)
    token_view["visible_token"] = _visible_token_label(token_view)
    
    return {"token": token_view, "queue": queue_status}


@router.get("/nearby-hospitals", response_model=HospitalSearchResponse)
async def get_dashboard_nearby_hospitals(
    current_user = Depends(get_current_active_user),
    # Accept multiple aliases like the hospitals endpoint for maximum compatibility
    lat: Optional[float] = Query(None, description="User latitude (alias 1)"),
    lng: Optional[float] = Query(None, description="User longitude (alias 1)"),
    user_lat: Optional[float] = Query(None, description="User latitude (alias 2)"),
    user_lng: Optional[float] = Query(None, description="User longitude (alias 2)"),
    latitude: Optional[float] = Query(None, description="User latitude (alias 3)"),
    longitude: Optional[float] = Query(None, description="User longitude (alias 3)"),
    radius_km: float = Query(25.0, gt=0, le=200, description="Search radius (km) when lat/lng provided"),
    limit: int = Query(20, ge=1, le=100, description="Max hospitals to return"),
    city: Optional[str] = Query(None, description="Fallback city filter if no coordinates provided"),
    db: Session = Depends(get_db),
):
    """Return nearby hospitals for the dashboard.
    ...
    """
    # Coalesce coordinate aliases
    lat_val = user_lat if user_lat is not None else (lat if lat is not None else latitude)
    lng_val = user_lng if user_lng is not None else (lng if lng is not None else longitude)
    
    # Require coordinates for live nearby
    if lat_val is None or lng_val is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location required. Please pass lat and lng from device GPS for nearby hospitals.")

    # Per-user+params cache key
    cache_key = (
        f"dashboard:nearby:{current_user.user_id}:lat={lat_val}:lng={lng_val}:r={radius_km}:l={limit}:city={(city or '').strip().lower()}"
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    hospitals: List[HospitalResponse] = []

    # Coordinates branch
    if lat_val is not None and lng_val is not None:
        hospitals_objs = db.query(Hospital).limit(500).all()
        results: List[dict] = []
        for h_obj in hospitals_objs:
            h = {k: v for k, v in h_obj.__dict__.items() if not k.startswith('_')}
            h_lat = h.get("latitude")
            h_lng = h.get("longitude")
            if h_lat is None or h_lng is None:
                continue
            dist = calculate_distance(lat_val, lng_val, h_lat, h_lng)
            if dist <= radius_km:
                h["distance_km"] = round(dist, 1)
                h["estimated_time_minutes"] = int(dist * 2)
                results.append(h)
        results.sort(key=lambda x: x.get("distance_km", 1e9))
        hospitals = [HospitalResponse(**h) for h in results[:limit]]
        result = HospitalSearchResponse(
            hospitals=hospitals,
            total_found=len(results),
            search_query=f"lat={lat_val},lng={lng_val},radius_km={radius_km}",
        )
        _cache_set(cache_key, result)
        return result

    # City branch
    if city:
        city_formatted = city.strip().title()
        hospitals_objs = db.query(Hospital).filter(Hospital.city == city_formatted).limit(limit).all()
        for h_obj in hospitals_objs:
            h = {k: v for k, v in h_obj.__dict__.items() if not k.startswith('_')}
            # If lat/lng supplied alongside city, compute distance
            if lat_val is not None and lng_val is not None and h.get("latitude") is not None and h.get("longitude") is not None:
                dist = calculate_distance(lat_val, lng_val, h["latitude"], h["longitude"])  # type: ignore[arg-type]
                h["distance_km"] = round(dist, 1)
                h["estimated_time_minutes"] = int(dist * 2)
            hospitals.append(HospitalResponse(**h))
        result = HospitalSearchResponse(
            hospitals=hospitals,
            total_found=len(hospitals),
            search_query=f"hospitals in {city}",
        )
        _cache_set(cache_key, result)
        return result

    # Default empty
    result = HospitalSearchResponse(hospitals=[], total_found=0, search_query="")
    _cache_set(cache_key, result)
    return result

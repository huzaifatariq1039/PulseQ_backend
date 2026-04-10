from fastapi import APIRouter, HTTPException, status, Query, Depends
from typing import List, Optional
import re
import uuid
from app.models import (
    HospitalCreate,
    HospitalResponse,
    HospitalSearchResponse,
    HospitalUnifiedSearchResponse,
    HospitalLite,
    SearchRequest,
    DoctorResponse,
    DoctorSearchResponse,
    DoctorWithQueue,
    QueueStatus,
)
from app.database import get_db
from sqlalchemy.orm import Session
from app.db_models import Hospital, Doctor, Queue, HospitalStatus
from app.security import get_current_active_user, require_roles
from app.utils.responses import ok
from datetime import datetime
import math
import httpx
from time import time

router = APIRouter(prefix="/hospitals", tags=["Hospitals"])

# Lightweight text normalizer for robust matching across app/backend
def _norm(text: Optional[str]) -> str:
    """Normalize text for comparison: collapse whitespace, trim, lowercase.

    This helps when the app sends values with extra spaces or different casing
    (e.g., "General  Medicine ", non-breaking spaces, etc.).
    """
    if not text:
        return ""
    # Replace any whitespace (including NBSP) with single spaces, then lowercase
    return re.sub(r"\s+", " ", str(text)).strip().lower()

# ==============================
# In-memory TTL cache (per-process, best-effort)
# ==============================
_CACHE_TTL_SECONDS = 60
_cache_store: dict[str, tuple[float, object]] = {}

def _cache_get(key: str):
    try:
        exp, val = _cache_store.get(key, (0.0, None))
        if exp >= time():
            return val
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

@router.post("/", response_model=HospitalResponse, dependencies=[Depends(require_roles("admin", "patient"))])
async def create_hospital(hospital: HospitalCreate, db: Session = Depends(get_db)):
    """Create a new hospital (Admin only)"""

    # Check if hospital with same name and address already exists
    existing = (
        db.query(Hospital)
        .filter(Hospital.name == hospital.name)
        .filter(Hospital.address == hospital.address)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hospital with this name and address already exists"
        )

    hospital_data = hospital.dict()
    # Normalize city name to title case for consistent searching
    hospital_data["city"] = hospital_data["city"].strip().title()
    hospital_id = str(uuid.uuid4())
    now = datetime.utcnow()

    h = Hospital(
        id=hospital_id,
        created_at=now,
        updated_at=now,
        **hospital_data,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    out = {k: v for k, v in h.__dict__.items() if not k.startswith('_')}
    return ok(data=HospitalResponse(**out), message="Hospital created successfully")

# ===============================
# NEW: Live Nearby via OpenStreetMap (Overpass API)
# ===============================
@router.get("/nearby-overpass")
async def get_nearby_hospitals_overpass(
    lat: float = Query(..., description="User latitude"),
    lng: float = Query(..., description="User longitude"),
    radius_m: int = Query(5000, ge=100, le=50000, description="Search radius in meters (default 5000m)"),
    limit: int = Query(20, ge=1, le=100, description="Max hospitals to return")
):
    """
    Fetch nearby hospitals using OpenStreetMap Overpass API.
    Does not depend on your Firestore dataset.
    """
    overpass_url = "https://overpass-api.de/api/interpreter"
    # Overpass QL query: search for hospital amenities around the coordinate
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="hospital"](around:{radius_m},{lat},{lng});
      way["amenity"="hospital"](around:{radius_m},{lat},{lng});
      relation["amenity"="hospital"](around:{radius_m},{lat},{lng});
    );
    out center;
    """

    try:
        async with httpx.AsyncClient(headers={"User-Agent": "SmartTokenApp/1.0"}) as client:
            resp = await client.get(overpass_url, params={"data": query})
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            data = resp.json()

        elements = data.get("elements", [])
        hospitals = []
        for el in elements:
            tags = el.get("tags", {})
            name = tags.get("name") or "Unknown Hospital"
            lat_val = el.get("lat") or el.get("center", {}).get("lat")
            lng_val = el.get("lon") or el.get("center", {}).get("lon")
            if lat_val is None or lng_val is None:
                continue
            hospitals.append({
                "id": el.get("id"),
                "name": name,
                "latitude": float(lat_val),
                "longitude": float(lng_val),
                "address": {
                    "street": tags.get("addr:street"),
                    "city": tags.get("addr:city"),
                    "state": tags.get("addr:state"),
                    "postcode": tags.get("addr:postcode"),
                    "country": tags.get("addr:country"),
                },
                "type": tags.get("amenity", "hospital"),
            })

        # Optional: limit results
        hospitals = hospitals[:limit]

        return {
            "hospitals": hospitals,
            "total_found": len(hospitals),
            "source": "OpenStreetMap-Overpass"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching from Overpass: {str(e)}")

@router.get("/")
async def list_hospitals(
    limit: int = Query(20, ge=1, le=100),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db)
):
    """List all hospitals with standardized response format"""
    total = db.query(Hospital).count()
    hospitals = db.query(Hospital).offset((page-1)*limit).limit(limit).all()
    
    results = []
    for h in hospitals:
        # Map DB model to response model
        h_dict = {k: v for k, v in h.__dict__.items() if not k.startswith('_')}
        # Ensure is_open is set based on status
        h_dict["is_open"] = h.status == HospitalStatus.OPEN
        results.append(h_dict)

    return {
        "success": True,
        "data": results,
        "meta": {
            "total": total,
            "page": page,
            "page_size": limit
        }
    }

# (Google Maps live-nearby endpoint removed as requested; using OpenStreetMap endpoints instead)

# ===============================
# NEW: Live Nearby via OpenStreetMap (Nominatim)
# ===============================
@router.get("/nearby-osm")
async def get_nearby_hospitals_osm(
    lat: float = Query(..., description="User latitude"),
    lng: float = Query(..., description="User longitude"),
    radius_m: int = Query(2000, ge=100, le=10000, description="Search radius in meters (default 2000m)"),
    limit: int = Query(10, ge=1, le=50, description="Max hospitals to return")
):
    """
    Fetch nearby hospitals using OpenStreetMap (Nominatim API).
    This does NOT require Google Maps API.
    """
    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": "hospital",
        "format": "json",
        "limit": limit,
        "lat": lat,
        "lon": lng,
        "addressdetails": 1,
        "extratags": 1,
        "amenity": "hospital",
        "radius": radius_m,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params, headers={"User-Agent": "SmartTokenApp/1.0"})
            data = response.json()

        hospitals = []
        for item in data:
            hospitals.append({
                "id": item.get("osm_id"),
                "name": item.get("display_name", "Unknown Hospital"),
                "latitude": float(item.get("lat")),
                "longitude": float(item.get("lon")),
                "address": item.get("address", {}),
                "type": item.get("type", "hospital"),
                "distance_km": None  # Nominatim does not return direct distance
            })

        return {
            "hospitals": hospitals,
            "total_found": len(hospitals),
            "source": "OpenStreetMap"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching data from OpenStreetMap: {str(e)}"
        )

@router.get("/nearby", response_model=HospitalSearchResponse)
async def get_nearby_hospitals(
    city: Optional[str] = Query(None, description="City to search for nearby hospitals (optional when lat/lng provided)"),
    limit: int = Query(20, ge=1, le=50, description="Number of hospitals to return"),
    # Accept multiple aliases from various clients
    user_lat: Optional[float] = Query(None, description="User's latitude (alias 1)"),
    user_lng: Optional[float] = Query(None, description="User's longitude (alias 1)"),
    lat: Optional[float] = Query(None, description="User's latitude (alias 2)"),
    lng: Optional[float] = Query(None, description="User's longitude (alias 2)"),
    latitude: Optional[float] = Query(None, description="User's latitude (alias 3)"),
    longitude: Optional[float] = Query(None, description="User's longitude (alias 3)"),
    radius_km: float = Query(25.0, gt=0, le=200, description="Search radius when using lat/lng"),
    include_open_db: bool = Query(True, description="Also include OPEN DB hospitals even if they lack coordinates"),
    db: Session = Depends(get_db),
):
    """Get nearby hospitals by city or by user coordinates.

    Behavior:
    - If `city` is provided, return hospitals in that city, with optional distance calc.
    - Else if `user_lat` and `user_lng` provided, return hospitals within `radius_km`, sorted by distance.
    - Else return an empty list.
    """
    # Coalesce coordinate aliases
    lat_val = user_lat if user_lat is not None else (lat if lat is not None else latitude)
    lng_val = user_lng if user_lng is not None else (lng if lng is not None else longitude)
    has_coords = (lat_val is not None) and (lng_val is not None)

    hospitals: List[HospitalResponse] = []

    # Cache by parameters (city or coords + radius + limit)
    cache_key = (
        f"hospitals:nearby:city={(city or '').strip().lower()}:lat={lat_val}:lng={lng_val}:r={radius_km}:l={limit}"
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    if city:
        # City-based query (case-insensitive storage by title-casing)
        city_formatted = city.strip().title()
        docs = db.query(Hospital).filter(Hospital.city == city_formatted).limit(limit).all()
        for h in docs:
            hospital_data = {k: v for k, v in h.__dict__.items() if not k.startswith('_')}
            if has_coords and hospital_data.get("latitude") is not None and hospital_data.get("longitude") is not None:
                distance = calculate_distance(lat_val, lng_val, hospital_data["latitude"], hospital_data["longitude"])  # type: ignore[arg-type]
                hospital_data["distance_km"] = round(distance, 1)
                hospital_data["estimated_time_minutes"] = int(distance * 2)
            hospitals.append(HospitalResponse(**hospital_data))
        result = HospitalSearchResponse(
            hospitals=hospitals,
            total_found=len(hospitals),
            search_query=f"hospitals in {city}"
        )
        _cache_set(cache_key, result)
        return result

    if has_coords:
        # Coordinate-based fallback: scan and filter within radius_km
        results: List[dict] = []
        docs = db.query(Hospital).limit(500).all()
        for doc in docs:
            h = {k: v for k, v in doc.__dict__.items() if not k.startswith('_')}
            h_lat = h.get("latitude")
            h_lng = h.get("longitude")
            if h_lat is not None and h_lng is not None:
                dist = calculate_distance(lat_val, lng_val, h_lat, h_lng)  # type: ignore[arg-type]
                if dist <= radius_km:
                    h["distance_km"] = round(dist, 1)
                    h["estimated_time_minutes"] = int(dist * 2)
                    results.append(h)
            elif include_open_db:
                # Include OPEN hospitals that lack coordinates so the UI still shows onboarded hospitals
                status_val = str(h.get("status") or "").lower()
                if status_val in ("open",):
                    results.append(h)
        results.sort(key=lambda x: x.get("distance_km", 1e9))
        hospitals = [HospitalResponse(**h) for h in results[:limit]]
        if hospitals:
            result = HospitalSearchResponse(
                hospitals=hospitals,
                total_found=len(results),
                search_query=f"lat={lat_val},lng={lng_val},radius_km={radius_km}"
            )
            _cache_set(cache_key, result)
            return result
        # Graceful fallback: return top hospitals (no distance) so UI isn't empty
        docs = db.query(Hospital).limit(limit).all()
        fallback = [HospitalResponse(**{k: v for k, v in d.__dict__.items() if not k.startswith('_')}) for d in docs]
        result = HospitalSearchResponse(
            hospitals=fallback,
            total_found=len(fallback),
            search_query="fallback_no_coords_on_hospitals"
        )
        _cache_set(cache_key, result)
        return result

    # Neither city nor coords provided
    result = HospitalSearchResponse(hospitals=[], total_found=0, search_query="")
    _cache_set(cache_key, result)
    return result

@router.get("/open", response_model=HospitalSearchResponse)
async def get_open_hospitals(
    city: Optional[str] = Query(None, description="Filter by city (optional)"),
    limit: int = Query(50, ge=1, le=200, description="Max hospitals to return"),
    db: Session = Depends(get_db),
):
    """Return OPEN hospitals from the SmartToken database (onboarded providers).

    This endpoint is designed for the Search page to show onboarded/open hospitals
    even when the user has not typed a search query or granted location.
    """

    q = db.query(Hospital)
    if city:
        q = q.filter(Hospital.city.ilike(city.strip()))
    q = q.filter(Hospital.status == HospitalStatus.OPEN)
    docs = q.limit(500).all()
    items = [{k: v for k, v in h.__dict__.items() if not k.startswith('_')} for h in docs]
    items.sort(key=lambda x: (x.get("name") or "").lower())
    hospitals = [HospitalResponse(**h) for h in items[:limit]]
    return HospitalSearchResponse(hospitals=hospitals, total_found=len(hospitals), search_query="open")

@router.get("/nearby-with-doctors")
async def get_nearby_hospitals_with_doctors(
    city: Optional[str] = Query(None, description="City to search for nearby hospitals (optional when lat/lng provided)"),
    # Accept multiple aliases from various clients
    user_lat: Optional[float] = Query(None, description="User's latitude for distance calc (alias 1)"),
    user_lng: Optional[float] = Query(None, description="User's longitude for distance calc (alias 1)"),
    lat: Optional[float] = Query(None, description="User's latitude for distance calc (alias 2)"),
    lng: Optional[float] = Query(None, description="User's longitude for distance calc (alias 2)"),
    latitude: Optional[float] = Query(None, description="User's latitude for distance calc (alias 3)"),
    longitude: Optional[float] = Query(None, description="User's longitude for distance calc (alias 3)"),
    main_category: Optional[str] = Query(None, description="General Medical | Specialist | Surgeon"),
    subcategory: Optional[str] = Query(None, description="Filter doctors by specific subcategory/specialization"),
    per_hospital_limit: int = Query(10, ge=1, le=50, description="Max doctors per hospital"),
    hospitals_limit: int = Query(20, ge=1, le=50, description="Max hospitals to return"),
    radius_km: float = Query(25.0, gt=0, le=200, description="Search radius when using lat/lng"),
    db: Session = Depends(get_db),
):
    """Return nearby hospitals along with their doctors filtered by category/subcategory.

    This is a convenience endpoint to render doctors inline on the Nearby Hospitals screen.
    """
    # Coalesce coordinate aliases similar to /hospitals/nearby
    lat_val = user_lat if user_lat is not None else (lat if lat is not None else latitude)
    lng_val = user_lng if user_lng is not None else (lng if lng is not None else longitude)
    has_coords = (lat_val is not None) and (lng_val is not None)

    if city:
        city_formatted = city.strip().title()
        docs = db.query(Hospital).filter(Hospital.city == city_formatted).limit(hospitals_limit).all()
    elif has_coords:
        docs = db.query(Hospital).limit(500).all()
    else:
        docs = []

    # Category mappings mirror those used in doctors and hospital category endpoints
    category_mappings = {
        "General Medical": [
            "General Medicine", "Family Medicine", "Internal Medicine", "Emergency Medicine"
        ],
        "Specialist": [
            "Cardiology", "Neurology", "Dermatology", "Pediatrics", "Psychiatry",
            "Radiology", "Pathology", "Anesthesiology", "Oncology", "Endocrinology",
            "Gastroenterology", "Pulmonology", "Nephrology", "Rheumatology",
            "Ophthalmology", "ENT", "Gynecology", "Urology"
        ],
        "Surgeon": [
            "General Surgery", "Cardiac Surgery", "Heart Surgeon", "Neuro Surgeon",
            "Ortho Surgeon", "Plastic Surgery", "Vascular Surgery", "Thoracic Surgery",
            "Pediatric Surgery", "Trauma Surgery", "Transplant Surgery",
            "Laparoscopic Surgery", "Reconstructive Surgery", "Surgeon"
        ],
    }

    def _matches_category(item: dict) -> bool:
        if not main_category and not subcategory:
            return True
        spec = (item.get("specialization") or "").strip()
        sub = (item.get("subcategory") or "").strip()
        if subcategory:
            s = subcategory.strip().lower()
            return sub.strip().lower() == s or spec.strip().lower() == s
        # main category filtering
        subs = category_mappings.get(main_category or "", [])
        subs_lower = {x.lower() for x in subs}
        if (sub and sub.lower() in subs_lower) or (spec and spec.lower() in subs_lower):
            return True
        if (main_category == "Surgeon") and ("surgeon" in sub.lower() or "surgeon" in spec.lower()):
            return True
        # Keep General Medical strict to its list to avoid over-mapping
        if main_category == "General Medical" and (
            (sub and sub in category_mappings["General Medical"]) or (spec and spec in category_mappings["General Medical"])
        ):
            return True
        if main_category == "Specialist" and (
            "surgeon" not in sub.lower() and "surgeon" not in spec.lower()
            and sub not in category_mappings["General Medical"] and spec not in category_mappings["General Medical"]
        ):
            return True
        return False

    results = []
    for doc in docs:
        h = {k: v for k, v in doc.__dict__.items() if not k.startswith('_')}
        # Distance calc if coords provided
        if has_coords and h.get("latitude") is not None and h.get("longitude") is not None:
            distance = calculate_distance(lat_val, lng_val, h["latitude"], h["longitude"])  # type: ignore[arg-type]
            h["distance_km"] = round(distance, 1)
            h["estimated_time_minutes"] = int(distance * 2)
            # If we're in coordinate-mode without city, filter by radius
            if not city and distance > radius_km:
                continue

        # Fetch doctors for this hospital and filter
        dref = db.query(Doctor).filter(Doctor.hospital_id == str(h.get("id"))).limit(500).all()
        doctors = []
        for d in dref:
            item = {k: v for k, v in d.__dict__.items() if not k.startswith('_')}
            if _matches_category(item):
                doctors.append(item)
                if len(doctors) >= per_hospital_limit:
                    break

        results.append({
            "hospital": HospitalResponse(**h),
            "doctors": doctors,
        })

    # Sort hospitals by distance if available
    results.sort(key=lambda x: getattr(x["hospital"], "distance_km", 1e9))

    # If no results in coordinate mode, graceful fallback to top hospitals
    if not results and has_coords:
        fb_docs = db.query(Hospital).limit(hospitals_limit).all()
        for d in fb_docs:
            h = {k: v for k, v in d.__dict__.items() if not k.startswith('_')}
            results.append({
                "hospital": HospitalResponse(**h),
                "doctors": []
            })

    return {
        "items": results,
        "total_found": len(results),
        "city": city,
        "main_category": main_category,
        "subcategory": subcategory,
    }

@router.get("/search", response_model=HospitalSearchResponse)
async def search_hospitals(
    query: str = Query(..., min_length=2, description="Search query for hospital name or specialization"),
    city: Optional[str] = Query(None, description="Filter by city"),
    limit: int = Query(10, ge=1, le=50, description="Number of results to return"),
    user_lat: Optional[float] = Query(None, description="User's latitude"),
    user_lng: Optional[float] = Query(None, description="User's longitude"),
    db: Session = Depends(get_db),
):
    """Search hospitals by name, specialization, or city"""
    results = []

    # Get all hospitals and filter in memory (simpler approach for small datasets)
    all_hospitals = db.query(Hospital).limit(100).all()  # Reasonable limit for filtering

    for h in all_hospitals:
        hospital_data = {k: v for k, v in h.__dict__.items() if not k.startswith('_')}

        # Apply city filter if specified
        if city and hospital_data.get("city", "").lower() != city.lower():
            continue

        # Check if query matches name, specializations, or city
        matches = False

        # Search in hospital name (case-insensitive)
        if query.lower() in hospital_data.get("name", "").lower():
            matches = True

        # Search in specializations (case-insensitive)
        specializations = hospital_data.get("specializations", [])
        if any(query.lower() in spec.lower() for spec in specializations):
            matches = True

        # Search in city if not already filtered
        if not city and query.lower() in hospital_data.get("city", "").lower():
            matches = True

        if matches:
            results.append(hospital_data)

        # Stop if we have enough results
        if len(results) >= limit:
            break

    # Calculate distances and prepare response
    hospitals = []
    for hospital_data in results[:limit]:
        # Calculate distance if user coordinates provided
        if user_lat and user_lng and hospital_data.get("latitude") and hospital_data.get("longitude"):
            distance = calculate_distance(
                user_lat, user_lng,
                hospital_data["latitude"], hospital_data["longitude"]
            )
            hospital_data["distance_km"] = round(distance, 1)
            hospital_data["estimated_time_minutes"] = int(distance * 2)

        hospitals.append(HospitalResponse(**hospital_data))

    return HospitalSearchResponse(
        hospitals=hospitals,
        total_found=len(hospitals),
        search_query=query
    )

# ===============================
# Unified Search: DB + Nearby (OSM)
# ===============================
@router.get("/search-unified", response_model=HospitalUnifiedSearchResponse)
async def search_hospitals_unified(
    query: Optional[str] = Query(None, description="Free text to match name/city"),
    city: Optional[str] = Query(None, description="City filter for DB hospitals"),
    limit: int = Query(30, ge=1, le=100, description="Max combined results"),
    user_lat: Optional[float] = Query(None, description="User latitude for nearby"),
    user_lng: Optional[float] = Query(None, description="User longitude for nearby"),
    radius_km: float = Query(25.0, gt=0, le=50, description="Nearby radius for OSM"),
    include_db: bool = Query(True, description="Include SmartToken database hospitals"),
    include_osm: bool = Query(True, description="Include external nearby hospitals from OSM"),
    db: Session = Depends(get_db),
):
    """Return a merged list of hospitals containing:
    - Database hospitals (never marked as nearby, is_database=True)
    - Nearby hospitals from OpenStreetMap (marked is_nearby=True, is_database=False)

    Items are de-duplicated by normalized name+city when possible.
    """
    qnorm = (query or "").strip().lower()

    # Cache by full parameter set
    cache_key = (
        f"hospitals:search_unified:q={qnorm}:city={(city or '').strip().lower()}:l={limit}:"
        f"lat={user_lat}:lng={user_lng}:r={radius_km}:db={include_db}:osm={include_osm}"
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    items: list[HospitalLite] = []

    # 1) Pull DB hospitals
    if include_db:
        docs = db.query(Hospital).limit(300).all()
        for d in docs:
            h = {k: v for k, v in d.__dict__.items() if not k.startswith('_')}
            # Optional city filter
            if city and h.get("city", "").lower() != city.lower():
                continue

            # Optional text filter
            if qnorm:
                hay = f"{h.get('name','')} {h.get('city','')}".lower()
                if qnorm not in hay:
                    continue
            # Distance only for display; DB entries are not flagged as nearby
            if user_lat is not None and user_lng is not None and h.get("latitude") and h.get("longitude"):
                dist = calculate_distance(user_lat, user_lng, h["latitude"], h["longitude"])  # type: ignore[arg-type]
                h["distance_km"] = round(dist, 1)
                h["estimated_time_minutes"] = int(dist * 2)

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
                is_nearby=False,
                is_database=True,
            ))

    # 2) Pull Nearby from OSM Overpass (if coords provided)
    if include_osm and user_lat is not None and user_lng is not None:
        overpass_url = "https://overpass-api.de/api/interpreter"
        radius_m = int(radius_km * 1000)
        query_overpass = f"""
        [out:json][timeout:25];
        (
          node["amenity"="hospital"](around:{radius_m},{user_lat},{user_lng});
          way["amenity"="hospital"](around:{radius_m},{user_lat},{user_lng});
          relation["amenity"="hospital"](around:{radius_m},{user_lat},{user_lng});
        );
        out center;
        """
        try:
            async with httpx.AsyncClient(headers={"User-Agent": "SmartTokenApp/1.0"}, timeout=20) as client:
                resp = await client.get(overpass_url, params={"data": query_overpass})
                data = resp.json()
            for el in data.get("elements", []):
                tags = el.get("tags", {})
                name = tags.get("name") or "Unknown Hospital"
                lat_val = el.get("lat") or el.get("center", {}).get("lat")
                lng_val = el.get("lon") or el.get("center", {}).get("lon")
                if lat_val is None or lng_val is None:
                    continue

                # Compute distance for ordering/badge
                dist_km = None
                eta = None
                try:
                    dist_km = round(calculate_distance(user_lat, user_lng, float(lat_val), float(lng_val)), 1)
                    eta = int(dist_km * 2)
                except Exception:
                    pass

                items.append(HospitalLite(
                    id=str(el.get("id")),
                    name=name,
                    address=tags.get("addr:street"),
                    city=tags.get("addr:city"),
                    state=tags.get("addr:state"),
                    latitude=float(lat_val),
                    longitude=float(lng_val),
                    distance_km=dist_km,
                    estimated_time_minutes=eta,
                    rating=None,
                    review_count=0,
                    status=None,
                    source="osm_overpass",
                    is_nearby=True,
                    is_database=False,
                ))
        except Exception as e:
            # Soft fail: continue with DB-only
            pass

    # 3) De-duplicate by normalized name + city preference: prefer DB record
    def _key(it: HospitalLite) -> str:
        nm = (it.name or "").strip().lower()
        ct = (it.city or "").strip().lower()
        return f"{nm}|{ct}"

    dedup: dict[str, HospitalLite] = {}
    # Insert DB first so they win on conflicts
    for it in items:
        k = _key(it)
        if k not in dedup:
            dedup[k] = it
        else:
            # If existing is OSM and new is DB, replace
            if dedup[k].is_database is False and it.is_database is True:
                dedup[k] = it

    merged = list(dedup.values())

    # Optional text filter after merge (covers OSM too)
    if qnorm:
        merged = [m for m in merged if qnorm in f"{m.name} {m.city}".lower()]

    # Sort: nearby first (by distance), then DB by name
    def _sort_key(m: HospitalLite):
        if m.is_nearby:
            return (0, m.distance_km or 1e9)
        return (1, (m.name or "").lower())

    merged.sort(key=_sort_key)
    merged = merged[:limit]

    result = HospitalUnifiedSearchResponse(
        hospitals=merged,
        total_found=len(merged),
        search_query=(query or "")
    )
    _cache_set(cache_key, result)
    return result

@router.get("/nearby-radius", response_model=HospitalSearchResponse)
async def get_hospitals_by_radius(
    lat: float = Query(..., description="User latitude"),
    lng: float = Query(..., description="User longitude"),
    radius_km: float = Query(25.0, gt=0, le=200, description="Search radius in kilometers"),
    limit: int = Query(20, ge=1, le=100, description="Max hospitals to return"),
    db: Session = Depends(get_db),
):
    """Return hospitals within a given radius of the provided coordinates."""
    # Load hospitals (bounded for safety); filter in-memory by distance
    results: List[dict] = []

    docs = db.query(Hospital).limit(500).all()
    for doc in docs:
        h = {k: v for k, v in doc.__dict__.items() if not k.startswith('_')}
        h_lat = h.get("latitude")
        h_lng = h.get("longitude")
        if h_lat is None or h_lng is None:
            continue
        dist = calculate_distance(lat, lng, h_lat, h_lng)
        if dist <= radius_km:
            h["distance_km"] = round(dist, 1)
            h["estimated_time_minutes"] = int(dist * 2)
            results.append(h)

    # Sort by distance asc and limit
    results.sort(key=lambda x: x.get("distance_km", 1e9))
    hospitals = [HospitalResponse(**h) for h in results[:limit]]

    return HospitalSearchResponse(
        hospitals=hospitals,
        total_found=len(results),
        search_query=f"lat={lat},lng={lng},radius_km={radius_km}"
    )

@router.get("/{hospital_id}", response_model=HospitalResponse)
async def get_hospital(hospital_id: str, db: Session = Depends(get_db)):
    """Get hospital by ID"""
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hospital not found"
        )
    return HospitalResponse(**{k: v for k, v in hospital.__dict__.items() if not k.startswith('_')})

@router.get("/{hospital_id}/doctors", response_model=DoctorSearchResponse)
async def get_hospital_doctors(
    hospital_id: str,
    category: Optional[str] = Query(None, description="Filter doctors by specialization category"),
    db: Session = Depends(get_db),
):
    """Get doctors for a specific hospital with optional category filter.

    Aligns the response shape with `/doctors/hospital/{hospital_id}` by returning
    `DoctorSearchResponse` including `doctors` with queue info and `subcategories`.
    """
    # Local helper to build a queue status for a doctor (mirrors logic in doctors.py)
    async def _get_queue_status(doctor_id: str) -> QueueStatus:
        q = db.query(Queue).filter(Queue.doctor_id == doctor_id).first()
        if q:
            return QueueStatus(
                doctor_id=doctor_id,
                current_token=int(getattr(q, "current_token", 0) or 0),
                waiting_patients=int(getattr(q, "waiting_patients", 0) or 0),
                estimated_wait_time_minutes=int(getattr(q, "estimated_wait_time_minutes", 0) or 0),
            )
        # Fallback synthetic queue
        import random
        waiting = random.randint(5, 25)

        return QueueStatus(
            doctor_id=doctor_id,
            current_token=random.randint(1, 10),
            waiting_patients=waiting,
            estimated_wait_time_minutes=waiting * 3,
        )

    category_mappings = {
        "General Medical": [
            "General Medicine", "Family Medicine", "Internal Medicine", "Emergency Medicine"
        ],
        "Specialist": [
            "Cardiology", "Neurology", "Dermatology", "Pediatrics", "Psychiatry",
            "Radiology", "Pathology", "Anesthesiology", "Oncology", "Endocrinology",
            "Gastroenterology", "Pulmonology", "Nephrology", "Rheumatology",
            "Ophthalmology", "ENT", "Gynecology", "Urology"
        ],
        "Surgeon": [
            "General Surgery", "Cardiac Surgery", "Heart Surgeon", "Neuro Surgeon",
            "Ortho Surgeon", "Plastic Surgery", "Vascular Surgery", "Thoracic Surgery",
            "Pediatric Surgery", "Trauma Surgery", "Transplant Surgery",
            "Laparoscopic Surgery", "Reconstructive Surgery", "Surgeon"
        ],
    }

    # If no category, return a reasonable set directly, wrapped as DoctorSearchResponse
    if not category:
        docs_stream = db.query(Doctor).filter(Doctor.hospital_id == hospital_id).limit(200).all()
        doctors_with_queue: list[DoctorWithQueue] = []
        for d in docs_stream:
            data = {k: v for k, v in d.__dict__.items() if not k.startswith('_')}
            doctor = DoctorResponse(**data)
            queue = await _get_queue_status(data["id"])
            doctors_with_queue.append(DoctorWithQueue(doctor=doctor, queue=queue))
        return {
            "doctors": doctors_with_queue,
            "total_found": len(doctors_with_queue),
            "hospital_id": hospital_id,
            "category": None,
            "subcategories": [],
        }

    cat = (category or "").strip()
    cat_lower = cat.lower()

    is_main_category = any(cat_lower == k.lower() for k in category_mappings.keys())

    # Stream a bounded set and filter in-memory for case-insensitivity and contains-matching
    docs_stream = db.query(Doctor).filter(Doctor.hospital_id == hospital_id).limit(500).all()
    results: list[dict] = []
    resolved_subcategories: list[str] = []

    if is_main_category:
        # Build subcategory set for the selected main category
        selected_key = next(k for k in category_mappings.keys() if cat_lower == k.lower())
        subcats = category_mappings[selected_key]
        sub_set_lower = {s.lower() for s in subcats}
        general_set = {s.lower() for s in category_mappings["General Medical"]}

        # Also accumulate dynamic subcategories present in data
        dyn_set = set(subcats)

        for d in docs_stream:
            item = {k: v for k, v in d.__dict__.items() if not k.startswith('_')}
            spec = (item.get("specialization") or "").strip()
            sub = (item.get("subcategory") or "").strip()
            spec_l = spec.lower()
            sub_l = sub.lower()

            ok = False
            if selected_key == "Surgeon":
                # Any surgeon-like doctor or explicitly in the mapped list
                ok = ("surgeon" in spec_l) or ("surgeon" in sub_l) or (spec_l in sub_set_lower) or (sub_l in sub_set_lower)
                if "surgeon" in spec_l or "surgeon" in sub_l:
                    if spec:
                        dyn_set.add(spec)
                    if sub:
                        dyn_set.add(sub)
            elif selected_key == "General Medical":
                ok = (spec_l in general_set) or (sub_l in general_set)
                if spec in category_mappings["General Medical"]:
                    dyn_set.add(spec)
                if sub in category_mappings["General Medical"]:
                    dyn_set.add(sub)
            else:  # Specialist
                # Specialist = not General Medical and not Surgeon, or explicitly in sub list
                if (
                    ("surgeon" not in spec_l and "surgeon" not in sub_l)
                    and (spec_l not in general_set and sub_l not in general_set)
                ):
                    ok = True
                # If we registered explicit subcategories, include those too
                if (spec_l in sub_set_lower) or (sub_l in sub_set_lower):
                    ok = True
                if spec and ("surgeon" not in spec_l) and (spec not in category_mappings["General Medical"]):
                    dyn_set.add(spec)
                if sub and ("surgeon" not in sub_l) and (sub not in category_mappings["General Medical"]):
                    dyn_set.add(sub)

            if ok:
                results.append(item)

        resolved_subcategories = sorted({s for s in dyn_set if s})

    else:
        # Otherwise: treat it as a concrete specialization/subcategory term
        for d in docs_stream:
            item = {k: v for k, v in d.__dict__.items() if not k.startswith('_')}
            spec = (item.get("specialization") or "").strip().lower()
            sub = (item.get("subcategory") or "").strip().lower()
            if cat_lower == spec or cat_lower == sub or cat_lower in spec or cat_lower in sub:
                results.append(item)

    # Wrap into DoctorWithQueue with queue info
    doctors_with_queue: list[DoctorWithQueue] = []
    for data in results:
        doctor = DoctorResponse(**data)
        queue = await _get_queue_status(data["id"])
        doctors_with_queue.append(DoctorWithQueue(doctor=doctor, queue=queue))

    # Filter out any subcategory tokens that equal main category labels, and remove empties
    main_labels_norm = { _norm(k) for k in category_mappings.keys() }
    resolved_subcategories = sorted({
        s for s in (resolved_subcategories or [])
        if s and s.strip().lower() not in main_labels_norm
    }, key=lambda x: x.lower())

    return {
        "doctors": doctors_with_queue,
        "total_found": len(doctors_with_queue),
        "hospital_id": hospital_id,
        "category": category,
        "subcategories": resolved_subcategories,
    }

@router.get("/{hospital_id}/doctors/by-category")
async def get_hospital_doctors_by_main_category(
    hospital_id: str,
    main_category: str = Query(..., description="One of: General Medical, Specialist, Surgeon"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Return doctors for a hospital filtered by a main category using the same mappings
    as `/{hospital_id}/categories`.

    Example: main_category=Surgeon will include ["General Surgery", "Cardiac Surgery", ...].
    """
    # Category mappings must match get_hospital_categories()
    category_mappings = {
        "General Medical": [
            "General Medical",
            "General Medicine",
            "Family Medicine",
            "Internal Medicine",
            "Emergency Medicine",
        ],
        "Specialist": [
            "Specialist",
            "Cardiology",
            "Neurology",
            "Dermatology",
            "Pediatrics",
            "Psychiatry",
            "Radiology",
            "Pathology",
            "Anesthesiology",
            "Oncology",
            "Endocrinology",
            "Gastroenterology",
            "Pulmonology",
            "Nephrology",
            "Rheumatology",
            "Ophthalmology",
            "ENT",
            "Gynecology",
            "Urology",
        ],
        "Surgeon": [
            "General Surgery",
            "Cardiac Surgery",
            "Heart Surgeon",
            "Neuro Surgeon",
            "Ortho Surgeon",
            "Plastic Surgery",
            "Vascular Surgery",
            "Thoracic Surgery",
            "Pediatric Surgery",
            "Trauma Surgery",
            "Transplant Surgery",
            "Laparoscopic Surgery",
            "Reconstructive Surgery",
            "Surgeon",
        ],
    }

    if main_category not in category_mappings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid main_category. Must be one of: {list(category_mappings.keys())}",
        )

    subcats = category_mappings[main_category]
    subcats_lower = [_norm(s) for s in subcats]

    # Fetch and filter in-memory for case-insensitive/contains matches
    docs = db.query(Doctor).filter(Doctor.hospital_id == hospital_id).limit(500).all()
    results: list[dict] = []
    for d in docs:
        item = {k: v for k, v in d.__dict__.items() if not k.startswith('_')}
        spec = _norm(item.get("specialization") or "")
        if any(spec == sc or spec in sc or sc in spec for sc in subcats_lower):
            results.append(item)
            if len(results) >= limit:
                break

    # Clean subcategories to avoid returning main labels and duplicates
    main_labels_norm = { _norm(k) for k in category_mappings.keys() }
    cleaned_subcats = sorted({ s for s in subcats if _norm(s) and _norm(s) not in main_labels_norm }, key=lambda x: x.lower())

    return {
        "doctors": results,
        "total_found": len(results),
        "hospital_id": hospital_id,
        "main_category": main_category,
        "subcategories": cleaned_subcats,
    }

@router.get("/{hospital_id}/doctors/by-subcategory")
async def get_hospital_doctors_by_subcategory(
    hospital_id: str,
    subcategory: str = Query(..., description="Exact subcategory/specialization name to filter"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Return doctors for a hospital filtered by a specific subcategory/specialization.
    Uses case-insensitive contains matching to be tolerant to data entry variations.
    """
    target = _norm(subcategory)

    # Map subcategory -> main category to also include doctors stored with main labels only
    category_mappings = {
        "General Medical": [
            "General Medical",
            "General Medicine",
            "Family Medicine",
            "Internal Medicine",
            "Emergency Medicine",
        ],
        "Specialist": [
            "Specialist",
            "Cardiology",
            "Neurology",
            "Dermatology",
            "Pediatrics",
            "Psychiatry",
            "Radiology",
            "Pathology",
            "Anesthesiology",
            "Oncology",
            "Endocrinology",
            "Gastroenterology",
            "Pulmonology",
            "Nephrology",
            "Rheumatology",
            "Ophthalmology",
            "ENT",
            "Gynecology",
            "Urology",
        ],
        "Surgeon": [
            "General Surgery",
            "Cardiac Surgery",
            "Heart Surgeon",
            "Neuro Surgeon",
            "Ortho Surgeon",
            "Plastic Surgery",
            "Vascular Surgery",
            "Thoracic Surgery",
            "Pediatric Surgery",
            "Trauma Surgery",
            "Transplant Surgery",
            "Laparoscopic Surgery",
            "Reconstructive Surgery",
            "Surgeon",
        ],
    }

    # Figure out which main category this subcategory belongs to (if any)
    target_main_norm: str = ""
    for main, subs in category_mappings.items():
        subs_norm = [_norm(s) for s in subs]
        if target in subs_norm:
            target_main_norm = _norm(main)
            break

    docs = db.query(Doctor).filter(Doctor.hospital_id == hospital_id).limit(500).all()
    results: list[dict] = []
    for d in docs:
        item = {k: v for k, v in d.__dict__.items() if not k.startswith('_')}
        spec = _norm(item.get("specialization") or "")
        # Match direct subcategory OR the resolved main category (doctor saved as main only)
        if target and (target == spec or target in spec or spec in target or (target_main_norm and spec == target_main_norm)):
            results.append(item)
            if len(results) >= limit:
                break

    return {
        "doctors": results,
        "total_found": len(results),
        "hospital_id": hospital_id,
        "subcategory": subcategory,
    }


@router.get("/{hospital_id}/categories")
async def get_hospital_categories(hospital_id: str, db: Session = Depends(get_db)):
    """Return enabled categories and subcategories for a hospital based on its doctors.

    Response example:
    {
      "categories": {
        "General Medical": ["General Medicine", "Family Medicine"],
        "Specialist": ["Cardiology"],
        "Surgeon": ["General Surgery", "Ortho Surgeon"]
      },
      "counts": {"General Medical": 2, "Specialist": 1, "Surgeon": 2},
      "subcategories_counts": {"General Medicine": 3, "Cardiology": 5, ...}
    }
    """
    # Fetch all specializations for this hospital
    docs = db.query(Doctor).filter(Doctor.hospital_id == hospital_id).all()
    present_specs: dict[str, int] = {}
    for d in docs:
        spec = getattr(d, "specialization", None)
        if not spec:
            continue
        present_specs[str(spec)] = present_specs.get(str(spec), 0) + 1

    # Category mappings (kept in sync with app/routes/doctors.py)
    category_mappings = {
        "General Medical": [
            "General Medicine",
            "Family Medicine",
            "Internal Medicine",
            "Emergency Medicine",
        ],
        "Specialist": [
            "Cardiology",
            "Neurology",
            "Dermatology",
            "Pediatrics",
            "Psychiatry",
            "Radiology",
            "Pathology",
            "Anesthesiology",
            "Oncology",
            "Endocrinology",
            "Gastroenterology",
            "Pulmonology",
            "Nephrology",
            "Rheumatology",
            "Ophthalmology",
            "ENT",
            "Gynecology",
            "Urology",
        ],
        "Surgeon": [
            "General Surgery",
            "Cardiac Surgery",
            "Heart Surgeon",
            "Neuro Surgeon",
            "Ortho Surgeon",
            "Plastic Surgery",
            "Vascular Surgery",
            "Thoracic Surgery",
            "Pediatric Surgery",
            "Trauma Surgery",
            "Transplant Surgery",
            "Laparoscopic Surgery",
            "Reconstructive Surgery",
        ],
    }

    # If no doctor specializations are present for this hospital, fall back to predefined mappings
    # so the UI can still show subcategories for selection. Counts remain zero in this case.
    if not present_specs:
        fallback_categories = {k: sorted(v, key=lambda x: x.lower()) for k, v in category_mappings.items()}
        fallback_counts = {k: 0 for k in category_mappings.keys()}
        return {
            "categories": fallback_categories,
            "counts": fallback_counts,
            "subcategories_counts": {},
            "hospital_id": hospital_id,
        }

    # Group present specializations into main categories
    categories: dict[str, list[str]] = {k: [] for k in category_mappings.keys()}
    counts: dict[str, int] = {k: 0 for k in category_mappings.keys()}

    def match_category(spec: str) -> Optional[str]:
        s = spec.lower()
        for main, subs in category_mappings.items():
            for sc in subs:
                if s == sc.lower() or s in sc.lower() or sc.lower() in s:
                    return main
        return None

    for spec, c in present_specs.items():
        main_cat = match_category(spec)
        if not main_cat:
            # If unmapped, treat as Specialist by default
            main_cat = "Specialist"
            if spec not in category_mappings[main_cat]:
                category_mappings[main_cat].append(spec)
        if spec not in categories[main_cat]:
            categories[main_cat].append(spec)
        counts[main_cat] += c

    # Sort subcategories alphabetically for stable UI
    for k in categories:
        categories[k].sort(key=lambda x: x.lower())

    return {
        "categories": categories,
        "counts": counts,
        "subcategories_counts": present_specs,
        "hospital_id": hospital_id,
    }


@router.put("/{hospital_id}")
async def update_hospital(
    hospital_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Update hospital details (Admin only)"""
    # Verify role
    from app.db_models import UserRole
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found")

    allowed = {
        "name", "address", "city", "state", "phone", "email",
        "latitude", "longitude", "status", "specializations"
    }

    for k, v in payload.items():
        if k in allowed:
            if k == "status" and v:
                from app.db_models import HospitalStatus
                try:
                    v = HospitalStatus(v.lower())
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid status: {v}")
            setattr(hospital, k, v)

    hospital.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(hospital)

    return {
        "success": True,
        "data": {k: v for k, v in hospital.__dict__.items() if not k.startswith('_')},
        "message": "Hospital updated"
    }


@router.delete("/{hospital_id}")
async def delete_hospital(
    hospital_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Delete hospital (Admin only)"""
    from app.db_models import UserRole
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hospital not found")

    db.delete(hospital)
    db.commit()

    return {"success": True, "message": "Hospital deleted"}


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points using Haversine formula"""
    R = 6371  # Earth's radius in kilometers
    
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c 
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.security import require_roles, get_current_active_user
from app.models import TokenData
from app.config import COLLECTIONS
from app.database import get_db
from app.utils.responses import ok
from datetime import datetime, timedelta, timezone
from app.services.token_service import SmartTokenService
from app.routes.pharmacy import router as pharmacy_router
from app.utils.mrn import get_or_create_patient_mrn

router = APIRouter(prefix="/portal", tags=["Portal (Role-Protected)"])

# Include Pharmacy portal endpoints under the centralized portal router
router.include_router(pharmacy_router)


def _parse_positive_int(value: Optional[int], default: int, maximum: int = 100) -> int:
    try:
        v = int(value or default)
        if v <= 0:
            return default
        return min(v, maximum)
    except Exception:
        return default


# -------------------- Shared datetime helpers --------------------
# Some endpoints need clinic-local day boundaries; ensure helpers exist at module scope
# (other endpoints previously referenced these names without defining them locally).
def _tz_offset_minutes(hospital_doc: Optional[Dict[str, Any]]) -> int:
    try:
        if isinstance(hospital_doc, dict):
            for k in ("tz_offset_minutes", "timezone_offset_minutes", "timezoneOffsetMinutes", "tzMinutes"):
                v = hospital_doc.get(k)
                if v is None:
                    continue
                try:
                    return int(v)
                except Exception:
                    continue
    except Exception:
        pass
    # Default to PKT-ish offset (UTC+5) as a safe fallback
    return 300


def _as_utc(dt: datetime) -> datetime:
    try:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return dt


def _to_local(dt: datetime, tz_minutes: int) -> datetime:
    try:
        tz = timezone(timedelta(minutes=int(tz_minutes or 0)))
        return _as_utc(dt).astimezone(tz)
    except Exception:
        return dt


@router.get("/notifications")
async def list_portal_notifications(
    current: TokenData = Depends(get_current_active_user),
    unread_only: bool = Query(True),
    limit: Optional[int] = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    db = get_db()
    notif_ref = db.collection("notifications").where("user_id", "==", current.user_id)
    if unread_only:
        notif_ref = notif_ref.where("is_read", "==", False)

    docs = list(notif_ref.stream())
    items = []
    for d in docs:
        n = d.to_dict() or {}
        if not n.get("id"):
            n["id"] = d.id
        # Backward compatibility: missing fields treated as unread
        if n.get("is_read") is None:
            n["is_read"] = False
        items.append(n)

    def _sort_key(x: Dict[str, Any]):
        v = x.get("sent_at") or x.get("created_at") or x.get("updated_at")
        return v or ""

    items.sort(key=_sort_key, reverse=True)
    items = items[: _parse_positive_int(limit, 50, 200)]
    return {"success": True, "data": items, "meta": {"unread_only": unread_only, "count": len(items)}}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    db = get_db()
    ref = db.collection("notifications").document(str(notification_id))
    snap = ref.get()
    if not getattr(snap, "exists", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    doc = snap.to_dict() or {}
    if str(doc.get("user_id") or "") != str(current.user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    ref.set({"is_read": True, "read_at": datetime.utcnow()}, merge=True)
    return {"success": True}


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    db = get_db()
    q = db.collection("notifications").where("user_id", "==", current.user_id).where("is_read", "==", False)
    docs = list(q.stream())
    if not docs:
        return {"success": True, "updated": 0}

    batch = db.batch()
    now = datetime.utcnow()
    updated = 0
    for d in docs:
        batch.set(d.reference, {"is_read": True, "read_at": now}, merge=True)
        updated += 1
        if updated % 400 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()
    return {"success": True, "updated": updated}


@router.get("/doctor/tokens", dependencies=[Depends(require_roles("doctor"))])
async def get_doctor_tokens(
    current: TokenData = Depends(get_current_active_user),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: Optional[int] = Query(1, ge=1),
    page_size: Optional[int] = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    db = get_db()
    tokens_ref = db.collection(COLLECTIONS["TOKENS"]).where("doctor_id", "==", current.user_id)
    if status_filter:
        tokens_ref = tokens_ref.where("status", "==", status_filter)
    # Firestore pagination requires cursors; we provide simple offset for now
    size = _parse_positive_int(page_size, 20)
    skip = max(0, (int(page or 1) - 1) * size)

    docs = list(tokens_ref.stream())
    items = [d.to_dict() for d in docs[skip: skip + size]]
    return {"success": True, "data": items, "meta": {"page": page, "page_size": size, "total": len(docs)}}


@router.get("/doctor/dashboard", dependencies=[Depends(require_roles("doctor"))])
async def doctor_dashboard(
    current: TokenData = Depends(get_current_active_user),
    upcoming_limit: int = Query(5, ge=0, le=50),
    skipped_limit: int = Query(5, ge=0, le=50),
) -> Dict[str, Any]:
    db = get_db()

    def _to_dt(v: Any) -> Optional[datetime]:
        try:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            to_dt = getattr(v, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except Exception:
            return None

    def _tz_offset_minutes(hospital_doc: Optional[Dict[str, Any]]) -> int:
        try:
            if isinstance(hospital_doc, dict):
                for k in ("tz_offset_minutes", "timezone_offset_minutes", "timezoneOffsetMinutes", "tzMinutes"):
                    v = hospital_doc.get(k)
                    if v is None:
                        continue
                    try:
                        return int(v)
                    except Exception:
                        continue
        except Exception:
            pass
        return 300

    def _as_utc(dt: datetime) -> datetime:
        try:
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return dt

    def _to_local(dt: datetime, tz_minutes: int) -> datetime:
        try:
            tz = timezone(timedelta(minutes=int(tz_minutes or 0)))
            return _as_utc(dt).astimezone(tz)
        except Exception:
            return dt

    def _status(t: Dict[str, Any]) -> str:
        raw = t.get("status")
        return str(getattr(raw, "value", raw) or "").lower()

    def _token_day(t: Dict[str, Any]) -> Optional[datetime.date]:
        # Queue-mode tokens may not have appointment_date; we store queue_day (YYYY-MM-DD)
        try:
            qd = t.get("queue_day")
            if qd:
                return datetime.fromisoformat(str(qd)).date()
        except Exception:
            pass
        appt = _to_dt(t.get("appointment_date"))
        if appt:
            return appt.date()
        try:
            created = _to_dt(t.get("created_at"))
            return created.date() if created else None
        except Exception:
            return None

    def _visible_token(t: Dict[str, Any]) -> Optional[str]:
        if not t:
            return None
        for k in ("display_code", "displayCode"):
            if t.get(k):
                return str(t.get(k))
        try:
            return SmartTokenService.format_token(int(t.get("token_number") or 0))
        except Exception:
            return None

    def _payment_label(tok: Dict[str, Any]) -> str:
        raw = tok.get("payment_status")
        val = str(getattr(raw, "value", raw) or "").lower()
        if val in ("paid", "unpaid"):
            return "Paid" if val == "paid" else "Unpaid"
        if val in ("completed", "processing", "success", "succeeded"):
            return "Paid"
        return "Unpaid"

    # Doctor profile header
    doctor_doc = {}
    try:
        snap = db.collection(COLLECTIONS["DOCTORS"]).document(current.user_id).get()
        if getattr(snap, "exists", False):
            doctor_doc = snap.to_dict() or {}
        else:
            # fallback if doctors collection stores separate user_id
            q = db.collection(COLLECTIONS["DOCTORS"]).where("user_id", "==", current.user_id).limit(1)
            docs = list(q.stream())
            if docs:
                doctor_doc = docs[0].to_dict() or {}
    except Exception:
        doctor_doc = {}

    doctor_header = {
        "id": doctor_doc.get("id") or current.user_id,
        "name": doctor_doc.get("name") or getattr(current, "name", None),
        "department": doctor_doc.get("specialization") or doctor_doc.get("department"),
        "room": doctor_doc.get("room") or doctor_doc.get("room_number"),
        "status": str(doctor_doc.get("status") or "").lower() or None,
    }

    # Pull today's tokens for this doctor (online + walk-in)
    today = datetime.utcnow().date()
    ref = db.collection(COLLECTIONS["TOKENS"]).where("doctor_id", "==", current.user_id)
    all_tokens = [d.to_dict() for d in ref.limit(5000).stream()]
    todays: List[Dict[str, Any]] = []
    for t in all_tokens:
        tday = _token_day(t)
        if tday and tday == today:
            todays.append(t)

    # Enrich patient info from users for online bookings
    _user_cache: Dict[str, Dict[str, Any]] = {}

    def _get_user(uid: Optional[str]) -> Dict[str, Any]:
        if not uid:
            return {}
        if uid in _user_cache:
            return _user_cache[uid]
        try:
            usnap = db.collection(COLLECTIONS["USERS"]).document(uid).get()
            data = usnap.to_dict() if getattr(usnap, "exists", False) else {}
        except Exception:
            data = {}
        _user_cache[uid] = data or {}
        return _user_cache[uid]

    for t in todays:
        u = _get_user(t.get("patient_id"))
        if not t.get("patient_name") and u.get("name"):
            t["patient_name"] = u.get("name")
        if not t.get("patient_phone") and u.get("phone"):
            t["patient_phone"] = u.get("phone")
        if not t.get("mrn") and t.get("patient_id"):
            hid = str(t.get("hospital_id") or doctor_doc.get("hospital_id") or "").strip()
            if hid:
                try:
                    t["mrn"] = get_or_create_patient_mrn(db, hospital_id=hid, patient_id=str(t.get("patient_id")))
                except Exception:
                    pass

    # Sort by token number
    todays.sort(key=lambda x: int(x.get("token_number") or 0))

    completed_tokens = [t for t in todays if _status(t) == "completed"]
    skipped_tokens = [t for t in todays if _status(t) == "skipped"]

    # Current consultation is strictly the token in consultation
    active_tokens = [t for t in todays if _status(t) in ("in_consultation", "pending", "confirmed", "waiting")]
    active_tokens.sort(key=lambda x: int(x.get("token_number") or 0))
    current_consult = None
    for t in active_tokens:
        if _status(t) == "in_consultation":
            current_consult = t
            break

    curr_num = 0
    try:
        if current_consult:
            curr_num = int(current_consult.get("token_number") or 0)
    except Exception:
        curr_num = 0

    # Waiting = patients still in line (pending/confirmed/waiting), excluding already served and excluding current
    waiting_candidates = [t for t in todays if _status(t) in ("pending", "confirmed", "waiting")]
    if current_consult and curr_num > 0:
        waiting_tokens = [t for t in waiting_candidates if int(t.get("token_number") or 0) > curr_num]
    else:
        waiting_tokens = waiting_candidates

    def _patient_row(t: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "token_id": t.get("id"),
            "token_number": _visible_token(t),
            "mrn": t.get("mrn") or t.get("patient_mrn"),
            "patient_name": t.get("patient_name"),
            "phone": t.get("patient_phone"),
            "age": t.get("patient_age"),
            "gender": t.get("patient_gender"),
            "reason": t.get("reason_for_visit"),
            "status": _status(t),
            "payment": _payment_label(t),
            "source": "walk_in" if bool(t.get("is_walk_in")) else "online",
        }

    current_obj = _patient_row(current_consult) if current_consult else None

    waiting_tokens.sort(key=lambda x: int(x.get("token_number") or 0))

    upcoming: List[Dict[str, Any]] = []
    for t in waiting_tokens:
        upcoming.append(_patient_row(t))
        if len(upcoming) >= int(upcoming_limit or 0):
            break

    skipped: List[Dict[str, Any]] = []
    for t in skipped_tokens:
        skipped.append(_patient_row(t))
        if len(skipped) >= int(skipped_limit or 0):
            break

    return ok(
        data={
            "doctor": doctor_header,
            "active_session": bool(current_consult),
            "cards": {
                "waiting_in_queue": len(waiting_tokens),
                "patients_served": len(completed_tokens),
            },
            "current_consultation": current_obj,
            "upcoming_patients": upcoming,
            "skipped_patients": skipped,
        }
    )


@router.get("/doctor/ratings/summary", dependencies=[Depends(require_roles("doctor"))])
async def doctor_ratings_summary(
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    db = get_db()

    def _to_dt(v: Any) -> Optional[datetime]:
        try:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            to_dt = getattr(v, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(v))
        except Exception:
            return None

    ref = db.collection(COLLECTIONS["TOKENS"]).where("doctor_id", "==", current.user_id)
    docs = [d.to_dict() for d in ref.limit(5000).stream()]

    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    total = 0
    total_sum = 0
    for t in docs:
        r = t.get("rating")
        if r is None:
            continue
        try:
            rv = int(r)
        except Exception:
            continue
        if rv < 1 or rv > 5:
            continue
        # Only count ratings that have a timestamp (best-effort); if missing, still count
        _ = _to_dt(t.get("rated_at"))
        dist[rv] = int(dist.get(rv, 0)) + 1
        total += 1
        total_sum += rv

    avg = round((total_sum / total), 2) if total > 0 else 0.0
    return ok(
        data={
            "average": avg,
            "total_reviews": total,
            "distribution": {
                "5": dist[5],
                "4": dist[4],
                "3": dist[3],
                "2": dist[2],
                "1": dist[1],
            },
        }
    )


@router.get("/doctor/ratings/reviews", dependencies=[Depends(require_roles("doctor"))])
async def doctor_ratings_reviews(
    current: TokenData = Depends(get_current_active_user),
    search: Optional[str] = Query(None, description="Search by patient name or review text"),
    rating: Optional[int] = Query(None, ge=1, le=5, description="Filter by star rating"),
    sort: Optional[str] = Query("recent", description="recent|oldest|highest|lowest"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    db = get_db()

    def _to_dt(v: Any) -> Optional[datetime]:
        try:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            to_dt = getattr(v, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(v))
        except Exception:
            return None

    def _visible_token(t: Dict[str, Any]) -> Optional[str]:
        for k in ("display_code", "displayCode"):
            if t.get(k):
                return str(t.get(k))
        try:
            return SmartTokenService.format_token(int(t.get("token_number") or 0))
        except Exception:
            return None

    # Load tokens for this doctor and filter in-memory (avoids composite index requirements)
    ref = db.collection(COLLECTIONS["TOKENS"]).where("doctor_id", "==", current.user_id)
    docs = [d.to_dict() for d in ref.limit(5000).stream()]

    # Enrich patient info from users for online bookings
    _user_cache: Dict[str, Dict[str, Any]] = {}

    def _get_user(uid: Optional[str]) -> Dict[str, Any]:
        if not uid:
            return {}
        if uid in _user_cache:
            return _user_cache[uid]
        try:
            usnap = db.collection(COLLECTIONS["USERS"]).document(uid).get()
            data = usnap.to_dict() if getattr(usnap, "exists", False) else {}
        except Exception:
            data = {}
        _user_cache[uid] = data or {}
        return _user_cache[uid]

    items: List[Dict[str, Any]] = []
    for t in docs:
        r = t.get("rating")
        if r is None:
            continue
        try:
            rv = int(r)
        except Exception:
            continue
        if rv < 1 or rv > 5:
            continue
        if rating is not None and int(rating) != rv:
            continue

        u = _get_user(t.get("patient_id"))
        pname = t.get("patient_name") or u.get("name")
        review_text = t.get("review_text") or t.get("feedback") or t.get("comment")
        rated_at = _to_dt(t.get("rated_at"))

        items.append({
            "token_id": t.get("id"),
            "token_number": _visible_token(t),
            "patient_id": t.get("patient_id"),
            "patient_name": pname,
            "rating": rv,
            "review_text": review_text,
            "rated_at": rated_at,
            "source": "walk_in" if bool(t.get("is_walk_in")) else "online",
        })

    if search:
        s = str(search).strip().lower()
        if s:
            def _hay(it: Dict[str, Any]) -> str:
                return f"{it.get('patient_name') or ''} {it.get('review_text') or ''} {it.get('token_number') or ''}".lower()
            items = [it for it in items if s in _hay(it)]

    sort_norm = str(sort or "recent").strip().lower()
    if sort_norm == "oldest":
        items.sort(key=lambda x: (x.get("rated_at") or datetime.min))
    elif sort_norm == "highest":
        items.sort(key=lambda x: (int(x.get("rating") or 0), x.get("rated_at") or datetime.min), reverse=True)
    elif sort_norm == "lowest":
        items.sort(key=lambda x: (int(x.get("rating") or 0), x.get("rated_at") or datetime.min))
    else:
        items.sort(key=lambda x: (x.get("rated_at") or datetime.min), reverse=True)

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    # Serialize rated_at consistently (ISO string)
    out: List[Dict[str, Any]] = []
    for it in page_items:
        dtv = it.get("rated_at")
        if isinstance(dtv, datetime):
            it = dict(it)
            it["rated_at"] = dtv.isoformat() + "Z"
        out.append(it)

    return ok(data=out, meta={"page": page, "page_size": page_size, "total": total})


@router.get("/doctor/history/patients", dependencies=[Depends(require_roles("doctor"))])
async def doctor_patient_history_list(
    current: TokenData = Depends(get_current_active_user),
    search: Optional[str] = Query(None, description="Search by patient name or phone"),
    sort: Optional[str] = Query("recent", description="recent|oldest|most_visits"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    db = get_db()

    def _to_dt(v: Any) -> Optional[datetime]:
        try:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            to_dt = getattr(v, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(v))
        except Exception:
            return None

    # Load completed consultations for this doctor and group by patient
    ref = db.collection(COLLECTIONS["TOKENS"]).where("doctor_id", "==", current.user_id)
    docs = [d.to_dict() for d in ref.limit(8000).stream()]

    # Cache users
    _user_cache: Dict[str, Dict[str, Any]] = {}

    def _get_user(uid: Optional[str]) -> Dict[str, Any]:
        if not uid:
            return {}
        if uid in _user_cache:
            return _user_cache[uid]
        try:
            usnap = db.collection(COLLECTIONS["USERS"]).document(uid).get()
            data = usnap.to_dict() if getattr(usnap, "exists", False) else {}
        except Exception:
            data = {}
        _user_cache[uid] = data or {}
        return _user_cache[uid]

    grouped: Dict[str, Dict[str, Any]] = {}
    for t in docs:
        st = str(getattr(t.get("status"), "value", t.get("status")) or "").lower()
        if st != "completed":
            continue
        pid = t.get("patient_id")
        if not pid:
            continue
        when = _to_dt(t.get("end_time") or t.get("completed_at") or t.get("appointment_date"))
        if pid not in grouped:
            u = _get_user(pid)
            grouped[pid] = {
                "patient_id": pid,
                "patient_name": (t.get("patient_name") or u.get("name")),
                "patient_phone": (t.get("patient_phone") or u.get("phone")),
                "mrn": (
                    t.get("mrn")
                    or (get_or_create_patient_mrn(db, hospital_id=str(t.get("hospital_id")), patient_id=str(pid)) if t.get("hospital_id") and pid else None)
                ),
                "visits": 0,
                "last_visit": when,
                "first_visit": when,
            }
        g = grouped[pid]
        g["visits"] = int(g.get("visits") or 0) + 1
        lv = g.get("last_visit")
        fv = g.get("first_visit")
        if when:
            if lv is None or when > lv:
                g["last_visit"] = when
            if fv is None or when < fv:
                g["first_visit"] = when

    items: List[Dict[str, Any]] = list(grouped.values())

    if search:
        s = str(search).strip().lower()
        if s:
            def _hay(it: Dict[str, Any]) -> str:
                return f"{it.get('patient_name') or ''} {it.get('patient_phone') or ''} {it.get('mrn') or ''}".lower()
            items = [it for it in items if s in _hay(it)]

    sort_norm = str(sort or "recent").strip().lower()
    if sort_norm == "oldest":
        items.sort(key=lambda x: (x.get("first_visit") or datetime.max))
    elif sort_norm == "most_visits":
        items.sort(key=lambda x: int(x.get("visits") or 0), reverse=True)
    else:
        items.sort(key=lambda x: (x.get("last_visit") or datetime.min), reverse=True)

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    out: List[Dict[str, Any]] = []
    for it in page_items:
        lv = it.get("last_visit")
        fv = it.get("first_visit")
        row = dict(it)
        if isinstance(lv, datetime):
            row["last_visit"] = lv.isoformat() + "Z"
        if isinstance(fv, datetime):
            row["first_visit"] = fv.isoformat() + "Z"
        out.append(row)

    return ok(data=out, meta={"page": page, "page_size": page_size, "total": total})


@router.get("/doctor/history/patients/{patient_id}", dependencies=[Depends(require_roles("doctor"))])
async def doctor_patient_history_detail(
    patient_id: str,
    current: TokenData = Depends(get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    db = get_db()

    def _to_dt(v: Any) -> Optional[datetime]:
        try:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            to_dt = getattr(v, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(v))
        except Exception:
            return None

    # Patient info
    patient_doc: Dict[str, Any] = {}
    try:
        psnap = db.collection(COLLECTIONS["USERS"]).document(patient_id).get()
        if getattr(psnap, "exists", False):
            patient_doc = psnap.to_dict() or {}
    except Exception:
        patient_doc = {}

    # Completed consultations between this doctor and patient
    ref = db.collection(COLLECTIONS["TOKENS"]).where("doctor_id", "==", current.user_id).where("patient_id", "==", patient_id)
    docs = [d.to_dict() for d in ref.limit(8000).stream()]
    completed: List[Dict[str, Any]] = []
    for t in docs:
        st = str(getattr(t.get("status"), "value", t.get("status")) or "").lower()
        if st != "completed":
            continue
        completed.append(t)

    completed.sort(key=lambda x: _to_dt(x.get("end_time") or x.get("completed_at") or x.get("appointment_date")) or datetime.min, reverse=True)

    total = len(completed)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = completed[start:end]

    def _visible_token(t: Dict[str, Any]) -> Optional[str]:
        for k in ("display_code", "displayCode"):
            if t.get(k):
                return str(t.get(k))
        try:
            return SmartTokenService.format_token(int(t.get("token_number") or 0))
        except Exception:
            return None

    out_items: List[Dict[str, Any]] = []
    for t in page_items:
        appt = _to_dt(t.get("appointment_date"))
        st = _to_dt(t.get("start_time"))
        et = _to_dt(t.get("end_time") or t.get("completed_at"))
        out_items.append({
            "token_id": t.get("id"),
            "token_number": _visible_token(t),
            "appointment_date": appt.isoformat() + "Z" if appt else None,
            "start_time": st.isoformat() + "Z" if st else None,
            "end_time": et.isoformat() + "Z" if et else None,
            "duration_minutes": t.get("duration_minutes"),
            "reason": t.get("reason_for_visit"),
            "notes": t.get("special_notes"),
            "rating": t.get("rating"),
            "review_text": t.get("review_text"),
        })

    patient_obj = {
        "id": patient_id,
        "name": patient_doc.get("name"),
        "phone": patient_doc.get("phone"),
        "mrn": None,
        "age": patient_doc.get("age"),
        "gender": patient_doc.get("gender"),
    }

    try:
        hid = None
        for t in completed:
            if t.get("hospital_id"):
                hid = str(t.get("hospital_id"))
                break
        if hid:
            patient_obj["mrn"] = get_or_create_patient_mrn(db, hospital_id=hid, patient_id=patient_id)
        else:
            by_h = patient_doc.get("mrn_by_hospital")
            if isinstance(by_h, dict) and by_h:
                # Arbitrary stable pick when hospital is unknown
                patient_obj["mrn"] = next(iter(by_h.values()))
    except Exception:
        try:
            by_h = patient_doc.get("mrn_by_hospital")
            if isinstance(by_h, dict) and by_h:
                patient_obj["mrn"] = next(iter(by_h.values()))
        except Exception:
            patient_obj["mrn"] = None

    return ok(data={"patient": patient_obj, "consultations": out_items}, meta={"page": page, "page_size": page_size, "total": total})


@router.get("/receptionist/tokens", dependencies=[Depends(require_roles("receptionist"))])
async def get_receptionist_tokens(
    current: TokenData = Depends(get_current_active_user),
    hospital_id: str = Query(..., description="Hospital managed by receptionist"),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: Optional[int] = Query(1, ge=1),
    page_size: Optional[int] = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    db = get_db()
    tokens_ref = db.collection(COLLECTIONS["TOKENS"]).where("hospital_id", "==", hospital_id)
    if status_filter:
        tokens_ref = tokens_ref.where("status", "==", status_filter)

    size = _parse_positive_int(page_size, 20)
    skip = max(0, (int(page or 1) - 1) * size)

    docs = list(tokens_ref.stream())
    items = [d.to_dict() for d in docs[skip: skip + size]]
    return {"success": True, "data": items, "meta": {"page": page, "page_size": size, "total": len(docs)}}


@router.get("/admin/users", dependencies=[Depends(require_roles("admin"))])
async def admin_list_users(
    current: TokenData = Depends(get_current_active_user),
    role: Optional[str] = Query(None, description="Filter by role"),
    page: Optional[int] = Query(1, ge=1),
    page_size: Optional[int] = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    db = get_db()
    users_ref = db.collection(COLLECTIONS["USERS"]).order_by("created_at") if hasattr(db.collection(COLLECTIONS["USERS"]), 'order_by') else db.collection(COLLECTIONS["USERS"])  # type: ignore
    if role:
        users_ref = users_ref.where("role", "==", role)

    size = _parse_positive_int(page_size, 20)
    skip = max(0, (int(page or 1) - 1) * size)

    docs = list(users_ref.stream())
    items = [d.to_dict() for d in docs[skip: skip + size]]
    # Avoid returning password hashes if present
    for it in items:
        it.pop("password", None)
    return {"success": True, "data": items, "meta": {"page": page, "page_size": size, "total": len(docs)}}


@router.get("/admin/dashboard", dependencies=[Depends(require_roles("admin"))])
async def admin_dashboard(
    current: TokenData = Depends(get_current_active_user),
    hospital_id: Optional[str] = Query(None, description="Optional hospital scope"),
    logs_limit: int = Query(10, ge=1, le=50),
    flow_start_hour: int = Query(8, ge=0, le=23),
    flow_end_hour: int = Query(15, ge=0, le=23),
) -> Dict[str, Any]:
    db = get_db()

    def _to_dt(v: Any) -> Optional[datetime]:
        try:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            to_dt = getattr(v, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(v))
        except Exception:
            return None

    def _safe_int(v: Any, default: int = 0) -> int:
        try:
            return int(v)
        except Exception:
            return default

    def _time_ago(ts: Optional[datetime]) -> str:
        if not ts:
            return ""
        now = datetime.utcnow()
        delta = now - ts
        secs = int(delta.total_seconds())
        if secs < 60:
            return "just now"
        mins = secs // 60
        if mins < 60:
            return f"{mins} min ago" if mins == 1 else f"{mins} mins ago"
        hrs = mins // 60
        if hrs < 24:
            return f"{hrs} hr ago" if hrs == 1 else f"{hrs} hrs ago"
        days = hrs // 24
        return f"{days} day ago" if days == 1 else f"{days} days ago"

    doctors_ref = db.collection(COLLECTIONS["DOCTORS"])
    if hospital_id:
        doctors_ref = doctors_ref.where("hospital_id", "==", hospital_id)
    doctors = [d.to_dict() for d in doctors_ref.limit(1000).stream()]

    active_doctors = 0
    departments_set = set()
    for d in doctors:
        spec = (d.get("specialization") or "").strip()
        if spec:
            departments_set.add(spec.lower())
        status_val = str(d.get("status") or "").lower()
        if status_val in ("available", "active") or status_val == "":
            active_doctors += 1

    # Resolve local-day boundaries for the scoped hospital (default to PKT offset when unknown)
    hospital_doc = None
    if hospital_id:
        try:
            hsnap = db.collection(COLLECTIONS["HOSPITALS"]).document(str(hospital_id)).get()
            hospital_doc = hsnap.to_dict() if getattr(hsnap, "exists", False) else None
        except Exception:
            hospital_doc = None
    tz_minutes = _tz_offset_minutes(hospital_doc)

    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    now_local = _to_local(now_utc, tz_minutes)
    local_day = now_local.date()
    start_local = datetime(local_day.year, local_day.month, local_day.day, 0, 0, 0, tzinfo=timezone(timedelta(minutes=tz_minutes)))
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    tokens_ref = db.collection(COLLECTIONS["TOKENS"])
    if hospital_id:
        tokens_ref = tokens_ref.where("hospital_id", "==", hospital_id)

    # Real-time today tokens: use created_at within local-day boundaries (includes queue-mode + walk-ins)
    tokens_today: List[Dict[str, Any]] = []
    try:
        q = tokens_ref.where("created_at", ">=", start_utc).where("created_at", "<", end_utc)
        tokens_today = [t.to_dict() for t in q.stream()]
    except Exception:
        # Fallback: avoid index requirements by streaming a larger sample and filtering in memory
        try:
            docs = [t.to_dict() for t in tokens_ref.limit(5000).stream()]
        except Exception:
            docs = []
        for t in docs:
            created = _to_dt(t.get("created_at") or t.get("updated_at"))
            if not created:
                continue
            if start_utc <= _as_utc(created) < end_utc:
                tokens_today.append(t)

    total_patients_today = len(tokens_today)

    wait_samples = []
    doctor_ids = {str(d.get("id") or "").strip() for d in doctors if d.get("id")}
    for did in doctor_ids:
        try:
            qs = SmartTokenService.get_queue_status(did) or {}
            q_total = _safe_int(qs.get("total_queue"), 0)
            if q_total > 0:
                wait_samples.append(max(q_total - 1, 0) * 9)
        except Exception:
            continue
    avg_wait = int(round(sum(wait_samples) / len(wait_samples))) if wait_samples else 0

    start_h = min(flow_start_hour, flow_end_hour)
    end_h = max(flow_start_hour, flow_end_hour)
    flow_hours = list(range(start_h, end_h + 1))
    buckets = {h: 0 for h in flow_hours}
    for t in tokens_today:
        created_dt = _to_dt(t.get("created_at") or t.get("updated_at"))
        if not created_dt:
            continue
        h = _to_local(created_dt, tz_minutes).hour
        if h in buckets:
            buckets[h] += 1

    flow = []
    for h in flow_hours:
        label = f"{h % 12 or 12}{'am' if h < 12 else 'pm'}"
        flow.append({"hour": h, "label": label, "count": buckets.get(h, 0)})

    logs = []
    try:
        docs = sorted(tokens_today, key=lambda x: _to_dt(x.get("created_at") or x.get("updated_at")) or datetime.min, reverse=True)
        for t in docs[:logs_limit]:
            created = _to_dt(t.get("created_at") or t.get("updated_at"))
            code = t.get("display_code") or t.get("displayCode") or t.get("hex_code") or t.get("hexCode") or t.get("token_number")
            dept = t.get("doctor_specialization") or t.get("department") or t.get("specialization")
            msg = f"Token {code} generated" + (f" for {dept}" if dept else "")
            logs.append({"message": msg, "time_ago": _time_ago(created), "created_at": created.isoformat() + "Z" if created else None})
    except Exception:
        logs = []

    # Monthly patient flow: last 12 months, based on created_at in hospital local time
    month_flow = []
    try:
        month0_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_12_local = (month0_local - timedelta(days=365)).replace(day=1)
        start_12_utc = start_12_local.astimezone(timezone.utc)

        month_docs: List[Dict[str, Any]] = []
        try:
            q2 = tokens_ref.where("created_at", ">=", start_12_utc)
            month_docs = [d.to_dict() for d in q2.stream()]
        except Exception:
            try:
                month_docs = [d.to_dict() for d in tokens_ref.limit(8000).stream()]
            except Exception:
                month_docs = []

        buckets_m: Dict[str, int] = {}
        for t in month_docs:
            created = _to_dt(t.get("created_at") or t.get("updated_at"))
            if not created:
                continue
            loc = _to_local(created, tz_minutes)
            # Filter to last 12 months window
            if loc < start_12_local:
                continue
            key = f"{loc.year:04d}-{loc.month:02d}"
            buckets_m[key] = buckets_m.get(key, 0) + 1

        # Emit last 12 months in order
        months = []
        cur = month0_local
        for _ in range(12):
            months.append(cur)
            # step back 1 month
            y = cur.year
            m = cur.month - 1
            if m <= 0:
                y -= 1
                m = 12
            cur = cur.replace(year=y, month=m, day=1)
        months.reverse()

        for mdt in months:
            k = f"{mdt.year:04d}-{mdt.month:02d}"
            try:
                label = mdt.strftime("%b")
            except Exception:
                label = k
            month_flow.append({"month": k, "label": label, "count": buckets_m.get(k, 0)})
    except Exception:
        month_flow = []

    return ok(
        data={
            "cards": {
                "total_patients_today": total_patients_today,
                "active_doctors": active_doctors,
                "avg_wait_time_minutes": avg_wait,
                "departments": len(departments_set),
            },
            "patient_flow_today": flow,
            "patient_flow_monthly": month_flow,
            "live_system_logs": logs,
        }
    )


@router.get("/admin/completed-consultations", dependencies=[Depends(require_roles("admin"))])
async def admin_completed_consultations(
    current: TokenData = Depends(get_current_active_user),
    hospital_id: Optional[str] = Query(None, description="Optional hospital scope"),
    doctor_id: Optional[str] = Query(None),
    department: Optional[str] = Query(None, description="Doctor specialization/department"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    db = get_db()

    def _to_dt(v: Any) -> Optional[datetime]:
        try:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            to_dt = getattr(v, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(v))
        except Exception:
            return None

    def _to_date(v: Any):
        dt = _to_dt(v)
        return dt.date() if dt else None

    def _duration_minutes(tok: Dict[str, Any]) -> int:
        try:
            d = tok.get("duration_minutes")
            if d is not None:
                return max(0, int(d))
        except Exception:
            pass
        st = _to_dt(tok.get("start_time"))
        et = _to_dt(tok.get("end_time"))
        try:
            if st and et:
                return max(0, int((et - st).total_seconds() // 60))
        except Exception:
            return 0
        return 0

    tokens_ref = db.collection(COLLECTIONS["TOKENS"])
    query = tokens_ref.where("status", "==", "completed")
    if hospital_id:
        query = query.where("hospital_id", "==", hospital_id)
    if doctor_id:
        query = query.where("doctor_id", "==", doctor_id)

    docs = []
    try:
        # Prefer Firestore-side ordering when available
        if hasattr(query, "order_by"):
            try:
                ordered = query.order_by("end_time", direction="DESCENDING")
                docs = [d.to_dict() for d in ordered.stream()]
            except Exception:
                docs = [d.to_dict() for d in query.stream()]
        else:
            docs = [d.to_dict() for d in query.stream()]
    except Exception:
        docs = []

    if department:
        dep = str(department).strip().lower()
        docs = [t for t in docs if str(t.get("doctor_specialization") or t.get("department") or t.get("specialization") or "").strip().lower() == dep]

    # In-memory ordering fallback (mock + safety)
    docs.sort(key=lambda x: _to_dt(x.get("end_time")) or datetime.min, reverse=True)

    today = datetime.utcnow().date()
    first_month = today.replace(day=1)

    completed_today = 0
    completed_this_month = 0
    durations = []
    for t in docs:
        end_d = _to_date(t.get("end_time") or t.get("completed_at"))
        if end_d == today:
            completed_today += 1
        if end_d and end_d >= first_month:
            completed_this_month += 1
        durations.append(_duration_minutes(t))

    avg_minutes = int(round(sum(durations) / len(durations))) if durations else 0

    total = len(docs)
    start = (page - 1) * page_size
    end = start + page_size
    page_docs = docs[start:end]

    records = []
    for t in page_docs:
        st = _to_dt(t.get("start_time"))
        et = _to_dt(t.get("end_time"))
        records.append({
            "token_id": t.get("id") or t.get("token_id"),
            "token_number": t.get("display_code") or t.get("displayCode") or t.get("hex_code") or t.get("hexCode") or t.get("token_number"),
            "mrn": t.get("mrn") or t.get("patient_mrn"),
            "patient_name": t.get("patient_name") or t.get("patient") or t.get("patient_full_name"),
            "doctor_name": t.get("doctor_name"),
            "department": t.get("doctor_specialization") or t.get("department") or t.get("specialization"),
            "start_time": st.isoformat() + "Z" if st else None,
            "end_time": et.isoformat() + "Z" if et else None,
            "duration_minutes": _duration_minutes(t),
            "status": t.get("status"),
        })

    return ok(
        data={
            "summary": {
                "completed_today": completed_today,
                "average_consultation_time_minutes": avg_minutes,
                "completed_this_month": completed_this_month,
            },
            "records": records,
        },
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get("/admin/doctors", dependencies=[Depends(require_roles("admin"))])
async def admin_list_doctors(
    current: TokenData = Depends(get_current_active_user),
    search: Optional[str] = Query(None, description="Search by doctor name"),
    department: Optional[str] = Query(None, description="Filter by specialization"),
    status_filter: Optional[str] = Query(None, alias="status"),
    hospital_id: Optional[str] = Query(None, description="Optional hospital scope"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> Dict[str, Any]:
    db = get_db()
    ref = db.collection(COLLECTIONS["DOCTORS"])
    if hospital_id:
        ref = ref.where("hospital_id", "==", hospital_id)
    if status_filter:
        ref = ref.where("status", "==", str(status_filter).strip().lower())

    docs = list(ref.limit(2000).stream())
    items: List[Dict[str, Any]] = []
    for d in docs:
        data = d.to_dict() or {}
        if not data.get("id"):
            data["id"] = getattr(d, "id", None)
        items.append(data)

    if department:
        dep = str(department).strip().lower()
        items = [it for it in items if str(it.get("specialization") or "").strip().lower() == dep]

    if search:
        s = str(search).strip().lower()
        if s:
            items = [it for it in items if s in str(it.get("name") or "").strip().lower()]

    def _sort_key(x: Dict[str, Any]):
        val = x.get("updated_at") or x.get("created_at")
        try:
            if isinstance(val, datetime):
                return val
            to_dt = getattr(val, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(val))
        except Exception:
            return datetime.min

    items.sort(key=_sort_key, reverse=True)

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    records = []
    for it in page_items:
        def _fmt_time_12h(v: Any) -> Optional[str]:
            """Format 'HH:MM' or 'H:MM AM/PM' into 'HH:MM AM/PM'."""
            try:
                s = str(v or "").strip()
                if not s:
                    return None
                low = s.lower()
                # Already AM/PM -> normalize spacing/case + leading hour
                if low.endswith("am") or low.endswith("pm"):
                    import re
                    m = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*$", low)
                    if not m:
                        return None
                    h = int(m.group(1))
                    mm = int(m.group(2) or 0)
                    mer = m.group(3).upper()
                    if h < 1 or h > 12 or mm < 0 or mm > 59:
                        return None
                    return f"{h:02d}:{mm:02d} {mer}"

                # Assume 24-hour HH:MM
                parts = s.split(":")
                if len(parts) != 2:
                    return None
                h = int(parts[0])
                mm = int(parts[1])
                if h < 0 or h > 23 or mm < 0 or mm > 59:
                    return None
                mer = "AM" if h < 12 else "PM"
                h12 = h % 12
                h12 = 12 if h12 == 0 else h12
                return f"{h12:02d}:{mm:02d} {mer}"
            except Exception:
                return None

        start_fmt = _fmt_time_12h(it.get("start_time"))
        end_fmt = _fmt_time_12h(it.get("end_time"))
        timings = f"{start_fmt} - {end_fmt}" if start_fmt and end_fmt else None
        dept = it.get("department") or it.get("specialization")
        records.append({
            "id": it.get("id"),
            "name": it.get("name"),
            "department": dept,
            "room": it.get("room") or it.get("room_number"),
            "status": str(it.get("status") or "available").lower(),
            "hospital_id": it.get("hospital_id"),
            "phone": it.get("phone"),
            "email": it.get("email"),
            "experience_years": it.get("experience_years"),
            "consultation_fee": it.get("consultation_fee"),
            "has_session": bool(it.get("has_session")),
            "pricing_type": it.get("pricing_type") or ("session_based" if bool(it.get("has_session")) else "standard"),
            "session_fee": it.get("session_fee"),
            "available_days": it.get("available_days") or [],
            "start_time": it.get("start_time"),
            "end_time": it.get("end_time"),
            "timings": timings,
        })

    return ok(data=records, meta={"page": page, "page_size": page_size, "total": total})


@router.post("/admin/doctors", dependencies=[Depends(require_roles("admin"))])
async def admin_create_doctor(
    payload: Dict[str, Any],
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    db = get_db()
    ref = db.collection(COLLECTIONS["DOCTORS"]).document()

    now = datetime.utcnow()
    data = dict(payload or {})
    data["id"] = getattr(ref, "id", None)
    data["created_at"] = now
    data["updated_at"] = now
    if not data.get("status"):
        data["status"] = "available"

    # If Firestore uses `department` field name, map it for internal consistency.
    if data.get("specialization") is None and data.get("department") is not None:
        data["specialization"] = data.get("department")
    if data.get("department") is None and data.get("specialization") is not None:
        data["department"] = data.get("specialization")

    # ---------------- Session-based pricing rules ----------------
    # If specialization/subcategory implies psychology/psychiatry/physiotherapy => has_session=true
    dept_text = (
        f"{data.get('specialization') or ''} "
        f"{data.get('subcategory') or ''} "
        f"{data.get('department') or ''}"
    ).lower().strip()
    inferred_has_session = any(
        kw in dept_text
        for kw in ("psychology", "psychiatry", "physiotherapist", "physiotherapy", "physio")
    )

    if not data.get("consultation_fee"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="consultation_fee is required")

    if inferred_has_session:
        session_fee_val = data.get("session_fee")
        try:
            session_fee_val = float(session_fee_val)
        except Exception:
            session_fee_val = None
        if session_fee_val is None or session_fee_val <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="session_fee is required and must be > 0 for session-based departments",
            )
        data["has_session"] = True
        data["pricing_type"] = "session_based"
        data["session_fee"] = session_fee_val
    else:
        data["has_session"] = False
        data["pricing_type"] = "standard"
        data["session_fee"] = None

    ref.set(data)
    return ok(data=data, message="Doctor created")


@router.put("/admin/doctors/{doctor_id}", dependencies=[Depends(require_roles("admin"))])
async def admin_update_doctor(
    doctor_id: str,
    payload: Dict[str, Any],
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    db = get_db()
    ref = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id)
    snap = ref.get()
    if not getattr(snap, "exists", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    allowed = {
        "name", "specialization", "subcategory", "hospital_id", "phone", "email",
        "experience_years", "rating", "review_count", "consultation_fee", "status",
        "session_fee",
        "department",
        "available_days", "start_time", "end_time", "avatar_initials", "patients_per_day",
        "has_session",
        "pricing_type",
        "room", "room_number",
    }
    update: Dict[str, Any] = {}
    for k, v in (payload or {}).items():
        if k in allowed:
            update[k] = v

    # Keep `department` and `specialization` in sync
    if "department" in update and "specialization" not in update:
        update["specialization"] = update.get("department")
    if "specialization" in update and "department" not in update:
        update["department"] = update.get("specialization")

    if "status" in update and update["status"] is not None:
        update["status"] = str(update["status"]).strip().lower()

    update["updated_at"] = datetime.utcnow()
    ref.update(update)

    merged = (snap.to_dict() or {})
    merged.update(update)
    if not merged.get("id"):
        merged["id"] = doctor_id

    # Re-apply session-based pricing rules to guarantee consistency
    dept_text = (
        f"{merged.get('specialization') or ''} "
        f"{merged.get('subcategory') or ''} "
        f"{merged.get('department') or ''}"
    ).lower().strip()
    inferred_has_session = any(
        kw in dept_text
        for kw in ("psychology", "psychiatry", "physiotherapist", "physiotherapy", "physio")
    )

    if not merged.get("consultation_fee"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="consultation_fee is required")

    if inferred_has_session:
        session_fee_val = merged.get("session_fee")
        try:
            session_fee_val = float(session_fee_val)
        except Exception:
            session_fee_val = None
        if session_fee_val is None or session_fee_val <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="session_fee is required and must be > 0 for session-based departments",
            )
        merged["has_session"] = True
        merged["pricing_type"] = "session_based"
        merged["session_fee"] = session_fee_val
    else:
        merged["has_session"] = False
        merged["session_fee"] = None
        merged["pricing_type"] = "standard"

    # Persist computed fields
    try:
        ref.update(
            {
                "has_session": merged["has_session"],
                "session_fee": merged["session_fee"],
                "pricing_type": merged.get("pricing_type") or ("session_based" if merged.get("has_session") else "standard"),
                "specialization": merged.get("specialization"),
                "department": merged.get("department") or merged.get("specialization"),
                "updated_at": datetime.utcnow(),
            }
        )
    except Exception:
        pass
    return ok(data=merged, message="Doctor updated")


@router.delete("/admin/doctors/{doctor_id}", dependencies=[Depends(require_roles("admin"))])
async def admin_delete_doctor(
    doctor_id: str,
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    db = get_db()
    ref = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id)
    snap = ref.get()
    if not getattr(snap, "exists", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    try:
        ref.delete()
    except Exception:
        ref.set({"deleted": True, "updated_at": datetime.utcnow()}, merge=True)
    return ok(message="Doctor deleted")


@router.get("/admin/departments", dependencies=[Depends(require_roles("admin"))])
async def admin_list_departments(
    current: TokenData = Depends(get_current_active_user),
    hospital_id: Optional[str] = Query(None, description="Optional hospital scope"),
    search: Optional[str] = Query(None, description="Search by department name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    db = get_db()
    ref = db.collection("departments")
    if hospital_id:
        ref = ref.where("hospital_id", "==", hospital_id)

    docs = list(ref.limit(2000).stream())
    items: List[Dict[str, Any]] = []
    for d in docs:
        data = d.to_dict() or {}
        if not data.get("id"):
            data["id"] = getattr(d, "id", None)
        items.append(data)

    if search:
        s = str(search).strip().lower()
        if s:
            items = [it for it in items if s in str(it.get("name") or "").strip().lower()]

    def _sort_key(x: Dict[str, Any]):
        val = x.get("updated_at") or x.get("created_at")
        try:
            if isinstance(val, datetime):
                return val
            to_dt = getattr(val, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(val))
        except Exception:
            return datetime.min

    items.sort(key=_sort_key, reverse=True)

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    out = []
    for it in page_items:
        out.append({
            "id": it.get("id"),
            "name": it.get("name"),
            "hospital_id": it.get("hospital_id"),
            "created_at": it.get("created_at"),
            "updated_at": it.get("updated_at"),
        })

    return ok(data=out, meta={"page": page, "page_size": page_size, "total": total})


@router.post("/admin/departments", dependencies=[Depends(require_roles("admin"))])
async def admin_create_department(
    payload: Dict[str, Any],
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    db = get_db()
    name = str((payload or {}).get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name is required")

    hospital_id = (payload or {}).get("hospital_id")
    # Prevent duplicates (best-effort)
    try:
        q = db.collection("departments")
        if hospital_id:
            q = q.where("hospital_id", "==", hospital_id)
        docs = list(q.limit(2000).stream())
        for d in docs:
            dd = d.to_dict() or {}
            if str(dd.get("name") or "").strip().lower() == name.lower():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Department already exists")
    except HTTPException:
        raise
    except Exception:
        pass

    ref = db.collection("departments").document()
    now = datetime.utcnow()
    data = {
        "id": getattr(ref, "id", None),
        "name": name,
        "hospital_id": hospital_id,
        "created_at": now,
        "updated_at": now,
    }
    ref.set(data)
    return ok(data=data, message="Department created")


@router.put("/admin/departments/{department_id}", dependencies=[Depends(require_roles("admin"))])
async def admin_update_department(
    department_id: str,
    payload: Dict[str, Any],
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    db = get_db()
    ref = db.collection("departments").document(department_id)
    snap = ref.get()
    if not getattr(snap, "exists", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    update: Dict[str, Any] = {}
    if "name" in (payload or {}):
        name = str((payload or {}).get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name is required")
        update["name"] = name
    if "hospital_id" in (payload or {}):
        update["hospital_id"] = (payload or {}).get("hospital_id")
    update["updated_at"] = datetime.utcnow()

    ref.update(update)
    merged = (snap.to_dict() or {})
    merged.update(update)
    if not merged.get("id"):
        merged["id"] = department_id
    return ok(data=merged, message="Department updated")


@router.delete("/admin/departments/{department_id}", dependencies=[Depends(require_roles("admin"))])
async def admin_delete_department(
    department_id: str,
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    db = get_db()
    ref = db.collection("departments").document(department_id)
    snap = ref.get()
    if not getattr(snap, "exists", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    try:
        ref.delete()
    except Exception:
        ref.set({"deleted": True, "updated_at": datetime.utcnow()}, merge=True)
    return ok(message="Department deleted")


@router.get("/receptionist/dashboard", dependencies=[Depends(require_roles("receptionist"))])
async def receptionist_dashboard(
    current: TokenData = Depends(get_current_active_user),
    hospital_id: str = Query(...),
    doctor_id: Optional[str] = Query(None),
    upcoming_limit: int = Query(5, ge=0, le=50),
) -> Dict[str, Any]:
    db = get_db()

    _doctor_cache: Dict[str, Dict[str, Any]] = {}

    def _get_doctor_meta(did: Optional[str]) -> Dict[str, Any]:
        if not did:
            return {}
        key = str(did)
        if key in _doctor_cache:
            return _doctor_cache[key]
        try:
            snap = db.collection(COLLECTIONS["DOCTORS"]).document(key).get()
            data = snap.to_dict() if getattr(snap, "exists", False) else {}
        except Exception:
            data = {}
        _doctor_cache[key] = data or {}
        return _doctor_cache[key]

    def _to_dt(v: Any) -> Optional[datetime]:
        try:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            to_dt = getattr(v, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(v))
        except Exception:
            return None

    today = datetime.utcnow().date()
    tokens_ref = db.collection(COLLECTIONS["TOKENS"]).where("hospital_id", "==", hospital_id)
    if doctor_id:
        tokens_ref = tokens_ref.where("doctor_id", "==", doctor_id)
    tokens = [t.to_dict() for t in tokens_ref.limit(3000).stream()]

    todays = []
    for t in tokens:
        appt = _to_dt(t.get("appointment_date"))
        if appt and appt.date() == today:
            todays.append(t)

    def _status(t: Dict[str, Any]) -> str:
        raw = t.get("status")
        return str(getattr(raw, "value", raw) or "").lower()

    waiting = [t for t in todays if _status(t) in ("pending", "confirmed")]
    completed = [t for t in todays if _status(t) == "completed"]
    skipped = [t for t in todays if _status(t) == "skipped"]

    # Now serving: prefer in_consultation, else first waiting
    active = [t for t in todays if _status(t) in ("in_consultation", "pending", "confirmed")]
    active.sort(key=lambda x: int(x.get("token_number") or 0))
    now_serving = None
    in_cons = [t for t in active if _status(t) == "in_consultation"]
    if in_cons:
        now_serving = in_cons[0]
    elif active:
        now_serving = active[0]

    def _visible_token(t: Dict[str, Any]) -> Optional[str]:
        if not t:
            return None
        for k in ("display_code", "displayCode"):
            if t.get(k):
                return str(t.get(k))
        try:
            return SmartTokenService.format_token(int(t.get("token_number") or 0))
        except Exception:
            return None

    now_obj = None
    if now_serving:
        dmeta = _get_doctor_meta(now_serving.get("doctor_id"))
        doc_name = now_serving.get("doctor_name") or dmeta.get("name")
        room = (
            now_serving.get("doctor_room")
            or now_serving.get("doctor_room_number")
            or dmeta.get("room")
            or dmeta.get("room_number")
        )
        now_obj = {
            "token_id": now_serving.get("id"),
            "token_number": _visible_token(now_serving),
            "patient_name": now_serving.get("patient_name"),
            "age": now_serving.get("patient_age"),
            "gender": now_serving.get("patient_gender"),
            "reason": now_serving.get("reason_for_visit"),
            "status": _status(now_serving),
            "doctor_name": doc_name,
            "doctor_room": room,
        }

    upcoming = []
    for t in active:
        if now_serving and t.get("id") == now_serving.get("id"):
            continue
        if _status(t) == "in_consultation":
            continue
        dmeta = _get_doctor_meta(t.get("doctor_id"))
        doc_name = t.get("doctor_name") or dmeta.get("name")
        room = (
            t.get("doctor_room")
            or t.get("doctor_room_number")
            or dmeta.get("room")
            or dmeta.get("room_number")
        )
        upcoming.append({
            "token_id": t.get("id"),
            "token_number": _visible_token(t),
            "patient_name": t.get("patient_name"),
            "age": t.get("patient_age"),
            "gender": t.get("patient_gender"),
            "reason": t.get("reason_for_visit"),
            "status": _status(t),
            "doctor_name": doc_name,
            "doctor_room": room,
        })
        if len(upcoming) >= upcoming_limit:
            break

    # Avg wait (minutes): approximate from queue size
    avg_wait = 0
    try:
        qsize = len(waiting)
        avg_wait = max(qsize - 1, 0) * 9
    except Exception:
        avg_wait = 0

    doctors_ref = db.collection(COLLECTIONS["DOCTORS"]).where("hospital_id", "==", hospital_id)
    doctors = [d.to_dict() for d in doctors_ref.limit(1000).stream()]
    active_doctors = []
    for d in doctors:
        st = str(d.get("status") or "").lower()
        if st in ("available", "active"):
            active_doctors.append({
                "id": d.get("id"),
                "name": d.get("name"),
                "department": d.get("specialization"),
                "room": d.get("room") or d.get("room_number"),
                "status": st,
            })

    return ok(
        data={
            "now_serving": now_obj,
            "upcoming_queue": upcoming,
            "cards": {
                "waiting": len(waiting),
                "completed": len(completed),
                "skipped": len(skipped),
                "avg_wait_minutes": avg_wait,
            },
            "active_doctors": active_doctors,
        }
    )


@router.get("/receptionist/queue", dependencies=[Depends(require_roles("receptionist"))])
async def receptionist_queue_list(
    current: TokenData = Depends(get_current_active_user),
    hospital_id: str = Query(...),
    doctor_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    payment: Optional[str] = Query(None, description="paid|unpaid|all"),
    search: Optional[str] = Query(None, description="Search by patient name or token number"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    db = get_db()

    _doctor_cache: Dict[str, Dict[str, Any]] = {}

    def _get_doctor_meta(did: Optional[str]) -> Dict[str, Any]:
        if not did:
            return {}
        key = str(did)
        if key in _doctor_cache:
            return _doctor_cache[key]
        try:
            snap = db.collection(COLLECTIONS["DOCTORS"]).document(key).get()
            data = snap.to_dict() if getattr(snap, "exists", False) else {}
        except Exception:
            data = {}
        _doctor_cache[key] = data or {}
        return _doctor_cache[key]

    def _to_dt(v: Any) -> Optional[datetime]:
        try:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            to_dt = getattr(v, "to_datetime", None)
            if callable(to_dt):
                return to_dt()
            return datetime.fromisoformat(str(v))
        except Exception:
            return None

    today = datetime.utcnow().date()
    ref = db.collection(COLLECTIONS["TOKENS"]).where("hospital_id", "==", hospital_id)
    if doctor_id:
        ref = ref.where("doctor_id", "==", doctor_id)
    docs = [d.to_dict() for d in ref.limit(5000).stream()]

    # Cache user lookups to avoid repeated reads
    _user_cache: Dict[str, Dict[str, Any]] = {}

    def _get_user(uid: Optional[str]) -> Dict[str, Any]:
        if not uid:
            return {}
        if uid in _user_cache:
            return _user_cache[uid]
        try:
            snap = db.collection(COLLECTIONS["USERS"]).document(uid).get()
            data = snap.to_dict() if getattr(snap, "exists", False) else {}
        except Exception:
            data = {}
        _user_cache[uid] = data or {}
        return _user_cache[uid]

    def _payment_label(tok: Dict[str, Any]) -> str:
        raw = tok.get("payment_status")
        val = str(getattr(raw, "value", raw) or "").lower()
        # Backward compatibility: some flows store paid/unpaid directly
        if val in ("paid", "unpaid"):
            return "Paid" if val == "paid" else "Unpaid"
        # Payment module uses completed/processing/pending
        if val in ("completed", "processing", "success", "succeeded"):
            return "Paid"
        return "Unpaid"

    items = []
    for t in docs:
        appt = _to_dt(t.get("appointment_date"))
        if not appt or appt.date() != today:
            continue
        raw = t.get("status")
        st = str(getattr(raw, "value", raw) or "").lower()
        if status_filter and st != str(status_filter).strip().lower():
            continue

        # Payment filter
        if payment and str(payment).strip().lower() != "all":
            want = str(payment).strip().lower()
            paid_flag = _payment_label(t).lower() == "paid"
            if want == "paid" and not paid_flag:
                continue
            if want in ("unpaid", "pending") and paid_flag:
                continue

        # Enrich from users collection if online-booked token doesn't include walk-in fields
        u = _get_user(t.get("patient_id"))
        if not t.get("patient_name") and u.get("name"):
            t["patient_name"] = u.get("name")
        if not t.get("patient_phone") and u.get("phone"):
            t["patient_phone"] = u.get("phone")
        if not t.get("mrn") and t.get("patient_id") and t.get("hospital_id"):
            try:
                t["mrn"] = get_or_create_patient_mrn(db, hospital_id=str(t.get("hospital_id")), patient_id=str(t.get("patient_id")))
            except Exception:
                pass

        # Ensure doctor_name/room is present for commercial-grade correctness
        try:
            dmeta = _get_doctor_meta(t.get("doctor_id"))
            if not t.get("doctor_name"):
                t["doctor_name"] = dmeta.get("name")
            if not t.get("doctor_room") and not t.get("doctor_room_number"):
                t["doctor_room"] = dmeta.get("room") or dmeta.get("room_number")
                t["doctor_room_number"] = dmeta.get("room_number") or dmeta.get("room")

            # Fee breakdown for receptionist view (doctor pricing rules)
            try:
                consultation_fee = t.get("consultation_fee")
                if consultation_fee is None:
                    consultation_fee = dmeta.get("consultation_fee")

                consultation_fee = float(consultation_fee) if consultation_fee is not None else None

                dept_text = (
                    f"{dmeta.get('specialization') or ''} "
                    f"{dmeta.get('subcategory') or ''} "
                    f"{dmeta.get('department') or ''}"
                ).lower().strip()
                inferred_has_session = any(
                    kw in dept_text
                    for kw in ("psychology", "psychiatry", "physiotherapist", "physiotherapy", "physio")
                )

                if inferred_has_session:
                    session_fee = t.get("session_fee")
                    if session_fee is None:
                        session_fee = dmeta.get("session_fee")
                    session_fee = float(session_fee) if session_fee is not None else None
                else:
                    session_fee = None

                if consultation_fee is not None and consultation_fee > 0:
                    total_fee = consultation_fee + (session_fee or 0) if session_fee else consultation_fee
                else:
                    total_fee = None

                t["consultation_fee"] = consultation_fee
                t["session_fee"] = session_fee
                t["total_fee"] = total_fee
            except Exception:
                pass
        except Exception:
            pass

        # Search filter (by token or patient)
        if search:
            s = str(search).strip().lower()
            if s:
                tok_label = str(t.get("display_code") or t.get("displayCode") or t.get("token_number") or "").strip().lower()
                pname = str(t.get("patient_name") or "").strip().lower()
                if s not in tok_label and s not in pname:
                    continue

        items.append(t)

    items.sort(key=lambda x: int(x.get("token_number") or 0))
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    def _visible_token(t: Dict[str, Any]) -> Optional[str]:
        for k in ("display_code", "displayCode"):
            if t.get(k):
                return str(t.get(k))
        try:
            return SmartTokenService.format_token(int(t.get("token_number") or 0))
        except Exception:
            return None

    out = []
    for t in page_items:
        raw = t.get("status")
        st = str(getattr(raw, "value", raw) or "").lower()
        pay_label = _payment_label(t)
        out.append({
            "token_id": t.get("id"),
            "token_number": _visible_token(t),
            "mrn": t.get("mrn") or t.get("patient_mrn"),
            "patient_name": t.get("patient_name"),
            "age": t.get("patient_age"),
            "gender": t.get("patient_gender"),
            "reason": t.get("reason_for_visit"),
            "doctor_id": t.get("doctor_id"),
            "doctor_name": t.get("doctor_name"),
            "doctor_room": t.get("doctor_room") or t.get("doctor_room_number"),
            "department": t.get("doctor_specialization") or t.get("department") or t.get("specialization"),
            "consultation_fee": t.get("consultation_fee"),
            "session_fee": t.get("session_fee"),
            "total_fee": t.get("total_fee"),
            "status": st,
            "payment": pay_label,
            "source": "walk_in" if bool(t.get("is_walk_in")) else "online",
        })

    return ok(data=out, meta={"page": page, "page_size": page_size, "total": total})


@router.get("/receptionist/walkin-form-data", dependencies=[Depends(require_roles("receptionist"))])
async def receptionist_walkin_form_data(
    current: TokenData = Depends(get_current_active_user),
    hospital_id: str = Query(...),
) -> Dict[str, Any]:
    db = get_db()
    # Departments
    dep_docs = list(db.collection("departments").where("hospital_id", "==", hospital_id).limit(2000).stream())
    departments = [d.to_dict() for d in dep_docs]
    if not departments:
        # fallback global departments (no hospital scope)
        departments = [d.to_dict() for d in db.collection("departments").limit(2000).stream()]
    departments = [{"id": x.get("id"), "name": x.get("name"), "hospital_id": x.get("hospital_id")} for x in departments if x.get("name")]

    # Doctors
    docs_ref = db.collection(COLLECTIONS["DOCTORS"]).where("hospital_id", "==", hospital_id)
    docs = [d.to_dict() for d in docs_ref.limit(2000).stream()]
    doctors = []
    for d in docs:
        doctors.append({
            "id": d.get("id"),
            "name": d.get("name"),
            "department": d.get("specialization"),
            "status": str(d.get("status") or "").lower(),
        })

    return ok(data={"departments": departments, "doctors": doctors})


@router.post("/receptionist/walkin-token", dependencies=[Depends(require_roles("receptionist"))])
async def receptionist_create_walkin_token(
    payload: Dict[str, Any],
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    db = get_db()
    hospital_id = str((payload or {}).get("hospital_id") or "").strip()
    if not hospital_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="hospital_id is required")

    department = str((payload or {}).get("department") or "").strip()
    doctor_id = (payload or {}).get("doctor_id")
    assign_any = bool((payload or {}).get("assign_any_available_doctor"))

    patient_name = str((payload or {}).get("patient_name") or "").strip()
    phone = str((payload or {}).get("phone") or "").strip()
    age = (payload or {}).get("age")
    gender = str((payload or {}).get("gender") or "").strip()
    reason = str((payload or {}).get("reason_for_visit") or "").strip()
    payment_status = str((payload or {}).get("payment_status") or "unpaid").strip().lower()
    special_notes = str((payload or {}).get("special_notes") or "").strip()
    include_consultation_fee = (payload or {}).get("include_consultation_fee")
    include_session_fee = (payload or {}).get("include_session_fee")

    if not department:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="department is required")
    if not patient_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="patient_name is required")
    if not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="phone is required")
    if not gender:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="gender is required")
    if not reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason_for_visit is required")

    # Choose doctor
    chosen_doc = None
    if doctor_id and not assign_any:
        snap = db.collection(COLLECTIONS["DOCTORS"]).document(str(doctor_id)).get()
        if not getattr(snap, "exists", False):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
        chosen_doc = snap.to_dict() or {}
    else:
        # pick first available doctor in hospital + department
        docs_ref = db.collection(COLLECTIONS["DOCTORS"]).where("hospital_id", "==", hospital_id).limit(2000)
        docs = [d.to_dict() for d in docs_ref.stream()]
        dep_norm = department.strip().lower()
        avail = []
        for d in docs:
            doc_dept = str(d.get("specialization") or d.get("department") or "").strip().lower()
            if doc_dept != dep_norm:
                continue
            st = str(d.get("status") or "").lower()
            if st in ("available", "active"):
                avail.append(d)
        if avail:
            chosen_doc = avail[0]

    if not chosen_doc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No available doctor found for selected department")

    # Emergency/unavailability: block walk-in token creation to avoid queue confusion
    chosen_status = str(chosen_doc.get("status") or "").lower()
    if chosen_status in {"offline", "on_leave"} or bool(chosen_doc.get("queue_paused")) or bool(chosen_doc.get("paused")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor unavailable")

    # ---------------- Session-based pricing rules ----------------
    consultation_fee_val = chosen_doc.get("consultation_fee")
    try:
        consultation_fee_val = float(consultation_fee_val)
    except Exception:
        consultation_fee_val = None
    if consultation_fee_val is None or consultation_fee_val <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor consultation_fee is required")

    dept_text = (
        f"{chosen_doc.get('specialization') or ''} "
        f"{chosen_doc.get('subcategory') or ''} "
        f"{chosen_doc.get('department') or ''}"
    ).lower().strip()
    inferred_has_session = any(
        kw in dept_text for kw in ("psychology", "psychiatry", "physiotherapist", "physiotherapy", "physio")
    )
    # Fee calculation (token fee + selected doctor fees)
    from app.services.fee_calculator import compute_total_amount
    if inferred_has_session and (include_session_fee is None or include_session_fee is True) and not chosen_doc.get("session_fee"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session fee required")
    pricing = compute_total_amount(
        consultation_fee=consultation_fee_val,
        session_fee=chosen_doc.get("session_fee"),
        include_consultation_fee=include_consultation_fee if isinstance(include_consultation_fee, bool) else None,
        include_session_fee=include_session_fee if isinstance(include_session_fee, bool) else None,
    )

    # Create or reuse user (walk-in patient)
    user_id = None
    try:
        users_ref = db.collection(COLLECTIONS["USERS"]).where("phone", "==", phone).limit(1)
        existing = list(users_ref.stream())
        if existing:
            u = existing[0].to_dict() or {}
            user_id = u.get("id") or getattr(existing[0], "id", None)
    except Exception:
        user_id = None
    if not user_id:
        uref = db.collection(COLLECTIONS["USERS"]).document()
        now = datetime.utcnow()
        udata = {
            "id": getattr(uref, "id", None),
            "name": patient_name,
            "phone": phone,
            "role": "patient",
            "is_walk_in": True,
            "created_at": now,
            "updated_at": now,
        }
        uref.set(udata)
        user_id = udata["id"]

    appt = datetime.utcnow()
    token_number, hex_code, formatted = SmartTokenService.create_smart_token(user_id, chosen_doc.get("id"), hospital_id, appt)

    token_data = {
        "patient_id": user_id,
        "patient_name": patient_name,
        "patient_phone": phone,
        "patient_age": age,
        "patient_gender": gender,
        "reason_for_visit": reason,
        "special_notes": special_notes,
        "payment_status": "completed" if payment_status == "paid" else "pending",
        "payment_method": "cash" if payment_status == "paid" else None,
        "doctor_id": chosen_doc.get("id"),
        "doctor_name": chosen_doc.get("name"),
        "doctor_specialization": chosen_doc.get("specialization") or chosen_doc.get("department"),
        "hospital_id": hospital_id,
        "token_number": token_number,
        "hex_code": hex_code,
        "display_code": formatted,
        "appointment_date": appt,
        # Fee breakdown (token fee + selected doctor fees)
        "token_fee": pricing.get("token_fee"),
        "consultation_fee": pricing.get("consultation_fee"),
        "session_fee": pricing.get("session_fee"),
        "total_fee": pricing.get("total_fee"),
        "total_amount": pricing.get("total_amount"),
        "include_consultation_fee": pricing.get("include_consultation_fee"),
        "include_session_fee": pricing.get("include_session_fee"),
        "status": "pending",
        "is_walk_in": True,
        "created_by": current.user_id,
        "created_via": "receptionist",
    }

    token_id = SmartTokenService.save_smart_token(token_data)
    token_data["id"] = token_id
    return ok(data={"token_id": token_id, "token": token_data}, message="Walk-in token created")


@router.post("/receptionist/tokens/{token_id}/skip", dependencies=[Depends(require_roles("receptionist"))])
async def receptionist_skip_token(
    token_id: str,
    current: TokenData = Depends(get_current_active_user),
) -> Dict[str, Any]:
    db = get_db()
    ref = db.collection(COLLECTIONS["TOKENS"]).document(token_id)
    snap = ref.get()
    if not getattr(snap, "exists", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    ref.update({"status": "skipped", "skipped_at": datetime.utcnow(), "updated_at": datetime.utcnow()})
    return ok(message="Token skipped")

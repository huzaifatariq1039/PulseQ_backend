import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import os

from fastapi import HTTPException, status

from app.database import get_db
from app.config import COLLECTIONS
from app.services.notification_service import NotificationService
from app.services.whatsapp_service import send_template_message
from app.templates import TEMPLATES
from app.routes.realtime import manager
from app.config_env import WEB_BASE_URL, MOBILE_BASE_URL


class DoctorLeaveService:
    """Emergency doctor leave handling.

    Responsibilities:
    - Pause doctor queue (advanced queue docs + doctor doc)
    - Update affected active tokens (waiting/pending/confirmed)
    - Send WhatsApp to affected patients
    - Broadcast real-time WebSocket updates
    """

    @staticmethod
    def _normalize_status(val: Any) -> str:
        try:
            return str(getattr(val, "value", val) or "").lower()
        except Exception:
            return ""

    @staticmethod
    def _active_token_statuses() -> List[str]:
        # "waiting OR confirmed" requirement, but existing code uses both
        # "waiting" (legacy) and "pending" (current) to mean waiting.
        return ["waiting", "pending", "confirmed"]

    @staticmethod
    def _normalize_leave_action(action: Optional[str]) -> str:
        a = str(action or "").strip().lower()
        if a in {"cancel", "c", "cancellation"}:
            return "cancel"
        if a in {"rescheduled", "reschedule", "a"}:
            return "rescheduled"
        if a in {"suggest_alternate", "suggest-alternate", "alternate", "b"}:
            return "suggest_alternate"
        # Default for safety: cancel so patient doesn't wait indefinitely
        return "cancel"

    @staticmethod
    def _queue_pause_payload(reason: str) -> Dict[str, Any]:
        now = datetime.utcnow()
        return {
            "status": "on_leave",
            # Support both naming conventions to keep frontend integrations stable.
            "paused": True,
            "queue_paused": True,
            "queue_pause_reason": reason,
            "updated_at": now,
        }

    @staticmethod
    def _pick_alternate_doctor(
        *,
        hospital_id: str,
        current_doctor_id: str,
        current_dept_norm: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Best-effort alternate doctor suggestion in same hospital + department match."""
        db = get_db()
        if not hospital_id:
            return None, None

        docs = list(
            db.collection(COLLECTIONS["DOCTORS"]).where("hospital_id", "==", hospital_id).limit(2000).stream()
        )
        for d in docs:
            data = d.to_dict() or {}
            did = str(data.get("id") or "").strip() or getattr(d, "id", None)
            if not did or str(did) == str(current_doctor_id):
                continue

            status_val = DoctorLeaveService._normalize_status(data.get("status")).lower()
            if status_val not in {"available", "active", ""}:
                continue

            dep_norm = str(data.get("specialization") or data.get("department") or "").strip().lower()
            sub_norm = str(data.get("subcategory") or "").strip().lower()
            merged = " ".join([dep_norm, sub_norm]).strip()

            if not merged:
                continue

            # Simple match: exact department or shared keyword
            if merged == current_dept_norm or current_dept_norm in merged or merged in current_dept_norm:
                return str(did), str(data.get("name") or "").strip() or None

            # Token overlap fallback
            cur_words = {w for w in current_dept_norm.replace(",", " ").split() if w}
            dep_words = {w for w in merged.replace(",", " ").split() if w}
            if cur_words and (cur_words & dep_words):
                return str(did), str(data.get("name") or "").strip() or None

        return None, None

    @staticmethod
    async def handle_doctor_on_leave(
        *,
        doctor_id: str,
        leave_action: Optional[str] = None,
        alternate_doctor_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        db = get_db()
        now = datetime.utcnow()

        doctor_id = str(doctor_id).strip()
        if not doctor_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="doctor_id is required")

        leave_action_norm = DoctorLeaveService._normalize_leave_action(leave_action)
        pause_reason = reason or "doctor_on_leave"

        dref = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id)
        dsnap = dref.get()
        if not getattr(dsnap, "exists", False):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
        doctor_data = dsnap.to_dict() or {}
        doctor_name = doctor_data.get("name") or "Doctor"
        hospital_id = str(doctor_data.get("hospital_id") or "").strip()

        dept_text = " ".join(
            [
                str(doctor_data.get("specialization") or ""),
                str(doctor_data.get("subcategory") or ""),
                str(doctor_data.get("department") or ""),
            ]
        ).strip().lower()

        # 1) Pause queue state
        dref.set(DoctorLeaveService._queue_pause_payload(pause_reason), merge=True)

        # 2) Pause advanced queue docs (queues collection) for null estimated_wait_time
        try:
            qref = db.collection(COLLECTIONS["QUEUES"]).where("doctor_id", "==", doctor_id)
            for qdoc in qref.stream():
                qdoc_ref = qdoc.reference if hasattr(qdoc, "reference") else None
                q_updates = {
                    "paused": True,
                    "queue_paused": True,
                    "queue_pause_reason": pause_reason,
                    "estimated_wait_time": None,
                    "updated_at": now,
                }
                if qdoc_ref:
                    qdoc_ref.set(q_updates, merge=True)
                else:
                    # Fallback for mocks
                    db.collection(COLLECTIONS["QUEUES"]).document(getattr(qdoc, "id", "")).set(q_updates, merge=True)
        except Exception:
            # Best-effort: never block status update for queue doc issues
            pass

        # 3) Fetch active tokens waiting/confirmed
        tokens_ref = db.collection(COLLECTIONS["TOKENS"]).where("doctor_id", "==", doctor_id)
        token_docs = list(tokens_ref.limit(5000).stream())

        affected_tokens: List[Dict[str, Any]] = []
        for tdoc in token_docs:
            t = tdoc.to_dict() or {}
            status_val = DoctorLeaveService._normalize_status(t.get("status"))
            if status_val in DoctorLeaveService._active_token_statuses():
                t["id"] = t.get("id") or getattr(tdoc, "id", None)
                affected_tokens.append(t)

        affected_token_ids = [str(t.get("id") or "").strip() for t in affected_tokens if t.get("id")]

        # 4) Update tokens (cancel/rescheduled/suggest alternate)
        if leave_action_norm in {"suggest_alternate", "rescheduled"}:
            chosen_alt_id = str(alternate_doctor_id or "").strip() if alternate_doctor_id else None
            chosen_alt_name = None
            if chosen_alt_id:
                try:
                    asnap = db.collection(COLLECTIONS["DOCTORS"]).document(chosen_alt_id).get()
                    if getattr(asnap, "exists", False):
                        ad = asnap.to_dict() or {}
                        chosen_alt_name = ad.get("name")
                except Exception:
                    chosen_alt_id = None

            if not chosen_alt_id:
                chosen_alt_id, chosen_alt_name = DoctorLeaveService._pick_alternate_doctor(
                    hospital_id=hospital_id,
                    current_doctor_id=doctor_id,
                    current_dept_norm=dept_text,
                )
        else:
            chosen_alt_id = None
            chosen_alt_name = None

        async_notifications: List[asyncio.Task] = []

        for t in affected_tokens:
            tid = str(t.get("id") or "").strip()
            if not tid:
                continue

            current_status = DoctorLeaveService._normalize_status(t.get("status"))
            token_update: Dict[str, Any] = {
                "doctor_unavailable": True,
                "doctor_unavailable_reason": pause_reason,
                "queue_position": 0,
                "estimated_wait_time": None,
                "updated_at": now,
            }

            # Use required options A/B/C
            if leave_action_norm == "cancel":
                token_update.update(
                    {
                        "status": "cancelled",
                        "cancellation_reason": "medical_emergency",
                        "cancelled_at": now,
                        "leave_action": "cancelled_due_to_doctor_on_leave",
                    }
                )
            elif leave_action_norm in {"rescheduled", "suggest_alternate"}:
                token_update.update(
                    {
                        "status": "rescheduled",
                        "leave_action": "rescheduled_due_to_doctor_on_leave",
                        "rescheduled_at": now,
                    }
                )
                if chosen_alt_id:
                    token_update["suggested_doctor_id"] = chosen_alt_id
                if chosen_alt_name:
                    token_update["suggested_doctor_name"] = chosen_alt_name

            # Persist token updates
            try:
                db.collection(COLLECTIONS["TOKENS"]).document(tid).set(token_update, merge=True)
            except Exception:
                continue

            # 5) Send WhatsApp to affected patients (best-effort)
            try:
                phone = (t.get("patient_phone") or "").strip()
                patient_name = str(t.get("patient_name") or "").strip()
                if not phone and t.get("patient_id"):
                    pu_ref = db.collection(COLLECTIONS["USERS"]).document(str(t.get("patient_id")))
                    pu_snap = pu_ref.get()
                    pu = pu_snap.to_dict() if getattr(pu_snap, "exists", False) else {}
                    phone = (pu.get("phone") or pu.get("mobile") or "").strip()
                    if not patient_name:
                        patient_name = str(pu.get("name") or pu.get("full_name") or "").strip()

                if not phone:
                    continue

                token_number = t.get("display_code") or t.get("hex_code") or t.get("token_number") or ""
                token_number_str = str(token_number)

                if leave_action_norm == "cancel":
                    action_msg = "cancelled"
                else:
                    action_msg = "rescheduled"

                base = (WEB_BASE_URL or MOBILE_BASE_URL or "").strip().rstrip("/")
                rebook_link = f"{base}/rebook/{tid}" if base else ""

                alt_line = ""
                try:
                    if chosen_alt_name:
                        alt_line = f"New assigned doctor: Dr. {chosen_alt_name}.\n"
                    elif chosen_alt_id:
                        alt_line = f"New assigned doctor ID: {chosen_alt_id}.\n"
                except Exception:
                    alt_line = ""

                msg = (
                    f"Emergency update: Dr. {doctor_name} is unavailable due to leave.\n"
                    f"Your token {token_number_str} has been {action_msg}.\n"
                    f"{alt_line}"
                    + (f"Rebook here: {rebook_link}\n" if rebook_link else "")
                    + "Please contact reception if you need help."
                )

                new_doc_name = chosen_alt_name or ""
                if not new_doc_name and chosen_alt_id:
                    new_doc_name = str(chosen_alt_id)

                send_task = None
                try:
                    template_name = str(TEMPLATES.get("DOCTOR_CHANGED_or_cancel") or "").strip()
                except Exception:
                    template_name = ""

                if template_name:
                    # Expected body variables:
                    # 1) patient name, 2) old doctor name, 3) new doctor name, 4) link
                    params = [
                        patient_name or "Patient",
                        f"Dr. {doctor_name}",
                        f"Dr. {new_doc_name}" if new_doc_name and not str(new_doc_name).lower().startswith("dr") else (new_doc_name or ""),
                        rebook_link or "",
                    ]
                    try:
                        send_task = asyncio.create_task(send_template_message(phone, template_name, params))
                    except Exception:
                        send_task = None

                if send_task is None:
                    send_task = asyncio.create_task(NotificationService.send_whatsapp_message(phone, msg))

                # Persist notification record for patient portal inbox (best-effort)
                try:
                    pid = t.get("patient_id")
                    if pid:
                        nref = db.collection("notifications").document()
                        nref.set(
                            {
                                "id": nref.id,
                                "token_id": tid,
                                "user_id": str(pid),
                                "phone_number": phone,
                                "message": msg,
                                "notification_types": ["whatsapp"],
                                "sent_at": now,
                                "status": "sent",
                                "is_read": False,
                                "read_at": None,
                            }
                        )
                except Exception:
                    pass

                async_notifications.append(send_task)
            except Exception:
                continue

        if async_notifications:
            # Best-effort: do not fail the API due to notification issues
            await asyncio.gather(*async_notifications, return_exceptions=True)

        # 6) Real-time WebSocket broadcasts
        try:
            rooms = [f"doctor_{doctor_id}"]
            if hospital_id:
                rooms.append(f"hospital_{hospital_id}")
                rooms.append(f"reception_{hospital_id}")

            payload = {
                "event": "doctor_on_leave",
                "doctor_id": doctor_id,
                "hospital_id": hospital_id,
                "leave_action": leave_action_norm,
                "reason": pause_reason,
                "affected_token_ids": affected_token_ids,
                "queue_paused": True,
                "estimated_wait_time": None,
            }
            msg = {"type": "queue_updated", "data": payload}
            for room in set(rooms):
                asyncio.create_task(manager.broadcast(room, msg))
        except Exception:
            pass

        return {
            "success": True,
            "doctor_id": doctor_id,
            "hospital_id": hospital_id,
            "doctor_name": doctor_name,
            "leave_action": leave_action_norm,
            "affected_tokens_count": len(affected_tokens),
            "affected_token_ids": affected_token_ids,
        }


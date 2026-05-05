import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.config import (
    AVG_CONSULTATION_TIME_MINUTES,
    COLLECTIONS,
    QUEUE_GRACE_TIME_MINUTES,
    QUEUE_SMART_NOTIFY_POSITION_THRESHOLD,
    QUEUE_SMART_NOTIFY_WAIT_THRESHOLD_MINUTES,
)
from app.database import get_db
from app.services.notification_service import NotificationService
from app.services.whatsapp_service import send_template_message
from app.templates import TEMPLATES


ACTIVE_QUEUE_STATUSES = {"waiting", "called", "in_consultation"}


@dataclass(frozen=True)
class QueueEvent:
    event_type: str
    doctor_id: str
    hospital_id: Optional[str]
    payload: Dict[str, Any]


class QueueManagementService:
    """Advanced queue management using Firestore `queues` collection.

    This is implemented alongside existing token-based queue logic so you can adopt it
    gradually without breaking current flows.
    """

    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
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

    @staticmethod
    def _is_doc_exists(snap: Any) -> bool:
        try:
            ex = getattr(snap, "exists", None)
            if isinstance(ex, bool):
                return ex
            if callable(ex):
                return bool(ex())
        except Exception:
            pass

        return False

    @staticmethod
    async def _send_queue_update_alerts_for_doctor(*, doctor_id: str, hospital_id: Optional[str]) -> None:
        """Send queue_update_alert based on time-to-appointment buckets and anti-spam.

        Rules:
        - do NOT send when patients_ahead <= 1 (final alert handles that)
        - anti-spam: minimum 120s between sends per token
        - thresholds:
          * time_diff > 60: send if wait changed by >= 10
          * 30 < time_diff <= 60: send if wait changed by >= 5
          * time_diff <= 30: send if position changed

        `time_diff` is derived from token appointment_date when present; otherwise falls back to new_wait.
        """

        try:
            tpl = str(TEMPLATES.get("QUEUE_UPDATE") or "").strip()
        except Exception:
            tpl = ""
        if not tpl:
            return

        db = get_db()
        qcol = db.collection(COLLECTIONS["QUEUES"])
        docs = list(qcol.where("doctor_id", "==", doctor_id).stream())

        waiting: List[Dict[str, Any]] = []
        for d in docs:
            dd = d.to_dict() or {}
            if str(dd.get("status") or "").lower() == "waiting":
                waiting.append(dd)

        if not waiting:
            return

        def _pos(dd: Dict[str, Any]) -> int:
            try:
                return int(dd.get("queue_position") or 10**9)
            except Exception:
                return 10**9

        waiting.sort(key=_pos)
        now = QueueManagementService._now()

        # Best-effort department mapping
        dept_label = ""
        try:
            dsnap = db.collection(COLLECTIONS["DOCTORS"]).document(str(doctor_id)).get()
            d = dsnap.to_dict() if QueueManagementService._is_doc_exists(dsnap) else {}
            room = str(d.get("room_number") or d.get("room") or "").strip()
            dept = str(d.get("specialization") or d.get("department") or d.get("subcategory") or "").strip()
            if room and dept:
                dept_label = f"Room {room} – {dept}"
            else:
                dept_label = dept or (f"Room {room}" if room else "")
        except Exception:
            dept_label = ""

        for qd in waiting:
            new_position = _pos(qd)
            patients_ahead = max(0, int(new_position) - 1)

            # IMPORTANT RULE: no queue update when patient is next/current
            if patients_ahead <= 1:
                continue

            pid = str(qd.get("patient_id") or "").strip()
            if not pid:
                continue

            token_id, token = QueueManagementService._find_active_token_for_patient(
                db=db,
                doctor_id=doctor_id,
                hospital_id=hospital_id,
                patient_id=pid,
            )
            if not token_id:
                continue

            # Respect opt-in if field exists
            if "queue_opt_in" in token and not bool(token.get("queue_opt_in")):
                continue

            # Anti-spam 120 seconds
            last_sent_dt = QueueManagementService._to_dt(token.get("last_queue_update"))
            if last_sent_dt and (now - last_sent_dt).total_seconds() < 120:
                continue

            try:
                new_wait = int(qd.get("estimated_wait_time") or 0)
            except Exception:
                new_wait = 0

            # Compute time_diff (minutes left)
            appt_dt = QueueManagementService._to_dt(token.get("appointment_date"))
            if appt_dt:
                try:
                    time_diff = int(max(0, (appt_dt - now).total_seconds() // 60))
                except Exception:
                    time_diff = new_wait
            else:
                time_diff = new_wait

            try:
                last_wait = int(token.get("last_wait") or token.get("last_queue_wait") or 0)
            except Exception:
                last_wait = 0
            try:
                last_position = int(token.get("last_position") or token.get("last_queue_position") or 0)
            except Exception:
                last_position = 0

            send = False

            if time_diff > 60:
                if abs(last_wait - new_wait) >= 10:
                    send = True
            elif 30 < time_diff <= 60:
                if abs(last_wait - new_wait) >= 5:
                    send = True
            else:
                if last_position != new_position:
                    send = True

            if not send:
                # Still update last_position/last_wait so next comparison is meaningful
                try:
                    db.collection(COLLECTIONS["TOKENS"]).document(token_id).set(
                        {"last_position": int(new_position), "last_wait": int(new_wait), "updated_at": now},
                        merge=True,
                    )
                except Exception:
                    pass
                continue

            # Phone + patient name
            usnap = db.collection(COLLECTIONS["USERS"]).document(pid).get()
            if not QueueManagementService._is_doc_exists(usnap):
                continue
            u = usnap.to_dict() or {}
            phone = str(u.get("phone") or token.get("patient_phone") or "").strip()
            if not phone:
                continue

            patient_name = str(u.get("name") or token.get("patient_name") or "Patient")
            token_number = str(token.get("formatted_token") or token.get("token_number") or "")

            try:
                await send_template_message(
                    phone,
                    tpl,
                    [
                        patient_name,
                        str(patients_ahead),
                        str(new_wait),
                        str(dept_label or token.get("department") or ""),
                        token_number,
                    ],
                )
            except Exception:
                pass

            try:
                db.collection(COLLECTIONS["TOKENS"]).document(token_id).set(
                    {
                        "last_queue_update": now,
                        "last_position": int(new_position),
                        "last_wait": int(new_wait),
                        "updated_at": now,
                    },
                    merge=True,
                )
            except Exception:
                pass


    @staticmethod
    def _estimated_wait_minutes(queue_position: int, consult_minutes: Optional[int] = None) -> int:
        cm = consult_minutes if consult_minutes is not None else int(AVG_CONSULTATION_TIME_MINUTES)
        try:
            cm = int(cm)
        except Exception:
            cm = int(AVG_CONSULTATION_TIME_MINUTES)
        if cm <= 0:
            cm = int(AVG_CONSULTATION_TIME_MINUTES)
        return max(0, int(queue_position - 1) * int(cm))

    @staticmethod
    def _doctor_consult_minutes(db: Any, doctor_id: str) -> Optional[int]:
        try:
            dsnap = db.collection(COLLECTIONS["DOCTORS"]).document(str(doctor_id)).get()
            if not QueueManagementService._is_doc_exists(dsnap):
                return None
            d = dsnap.to_dict() or {}
            for k in (
                "avg_consultation_time_minutes",
                "consultation_time_minutes",
                "avg_consult_time_minutes",
                "avg_consult_time",
                "avg_consultation_time",
            ):
                v = d.get(k)
                if v is None:
                    continue
                try:
                    iv = int(v)
                    if iv > 0:
                        return iv
                except Exception:
                    continue
        except Exception:
            return None
        return None

    @staticmethod
    def _queue_doc_to_dict(doc: Any) -> Dict[str, Any]:
        d = doc.to_dict() or {}
        d["queue_id"] = getattr(doc, "id", None) or getattr(doc, "doc_id", None)
        return d

    @staticmethod
    def _doc_id(doc: Any) -> Optional[str]:
        return getattr(doc, "id", None) or getattr(doc, "doc_id", None)

    @staticmethod
    def _broadcast_best_effort(event: QueueEvent) -> None:
        """Fire-and-forget websocket broadcast. Safe if realtime module isn't used."""
        try:
            from app.routes.realtime import manager  # local import to avoid hard dependency / cycles

            rooms = [f"doctor_{event.doctor_id}"]
            if event.hospital_id:
                rooms.append(f"hospital_{event.hospital_id}")
            msg = {"type": "queue_updated", "data": {"event": event.event_type, **event.payload}}
            for room in rooms:
                asyncio.create_task(manager.broadcast(room, msg))
        except Exception:
            # Realtime is optional; never break core queue ops.
            return

    @staticmethod
    def _doctor_queue_paused(doctor_id: str) -> Tuple[bool, Optional[str]]:
        db = get_db()
        dref = db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id)
        snap = dref.get()
        if not QueueManagementService._is_doc_exists(snap):
            return False, None

        data = snap.to_dict() or {}
        if bool(data.get("queue_paused")) or bool(data.get("paused")):
            return True, str(data.get("queue_pause_reason") or "paused")
        # If doctor is offline, treat as paused for updates.
        status = str(data.get("status") or "").lower()
        if status in {"offline", "on_leave"}:
            return True, "doctor_off_leave" if status == "on_leave" else "doctor_offline"
        return False, None

    @staticmethod
    def _find_active_token_for_patient(
        *,
        db: Any,
        doctor_id: str,
        hospital_id: Optional[str],
        patient_id: str,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """Best-effort token lookup without requiring composite indexes."""
        try:
            docs = list(
                db.collection(COLLECTIONS["TOKENS"]).where("patient_id", "==", str(patient_id)).limit(50).stream()
            )
        except Exception:
            docs = []

        best_id: Optional[str] = None
        best: Dict[str, Any] = {}
        best_created: Optional[datetime] = None

        for d in docs:
            td = d.to_dict() or {}
            if str(td.get("doctor_id") or "") != str(doctor_id or ""):
                continue
            if hospital_id and str(td.get("hospital_id") or "") != str(hospital_id):
                continue

            st_raw = td.get("status")
            st = str(getattr(st_raw, "value", st_raw) or "").lower()
            if st in {"cancelled", "completed"}:
                continue

            created = td.get("created_at")
            created_dt = QueueManagementService._to_dt(created)
            if best_id is None:
                best_id = str(td.get("id") or getattr(d, "id", None) or "") or None
                best = td
                best_created = created_dt
            else:
                if created_dt and (best_created is None or created_dt > best_created):
                    best_id = str(td.get("id") or getattr(d, "id", None) or "") or None
                    best = td
                    best_created = created_dt

        return best_id, best

    @staticmethod
    async def _send_turn_now_alert(*, doctor_id: str, hospital_id: Optional[str], qdata: Dict[str, Any]) -> None:
        """Send patient_call_alert when patient becomes current (called)."""
        try:
            tpl = str(TEMPLATES.get("TURN_NOW") or "").strip()
        except Exception:
            tpl = ""
        if not tpl:
            return

        pid = str(qdata.get("patient_id") or "").strip()
        if not pid:
            return

        db = get_db()
        token_id, token = QueueManagementService._find_active_token_for_patient(
            db=db,
            doctor_id=doctor_id,
            hospital_id=hospital_id,
            patient_id=pid,
        )
        if not token_id:
            return

        if bool(token.get("turn_alert_sent")):
            return

        # Phone/name from user doc (authoritative for queue)
        usnap = db.collection(COLLECTIONS["USERS"]).document(pid).get()
        if not QueueManagementService._is_doc_exists(usnap):
            return
        u = usnap.to_dict() or {}
        phone = str(u.get("phone") or "").strip()
        if not phone:
            return

        patient_name = str(u.get("name") or token.get("patient_name") or "Patient")
        token_number = str(token.get("formatted_token") or token.get("token_number") or "")

        try:
            await send_template_message(phone, tpl, [patient_name])
        except Exception:
            pass

        try:
            db.collection(COLLECTIONS["TOKENS"]).document(token_id).set(
                {"turn_alert_sent": True, "turn_alert_sent_at": QueueManagementService._now()},
                merge=True,
            )
        except Exception:
            pass

    @staticmethod
    async def _send_final_alert_for_doctor(*, doctor_id: str, hospital_id: Optional[str]) -> None:
        """Send final_alert when queue_position==3 (1 patient ahead), once per token."""
        try:
            tpl = str(TEMPLATES.get("FINAL_CALL") or "").strip()
        except Exception:
            tpl = ""
        if not tpl:
            return

        db = get_db()
        qcol = db.collection(COLLECTIONS["QUEUES"])
        docs = list(qcol.where("doctor_id", "==", doctor_id).stream())
        waiting = []
        for d in docs:
            dd = d.to_dict() or {}
            if str(dd.get("status") or "").lower() == "waiting":
                waiting.append(dd)

        # IMPORTANT CONDITION: total_tokens > 1
        if len(waiting) <= 1:
           return

        def _pos(dd: Dict[str, Any]) -> int:
            try:
                return int(dd.get("queue_position") or 10**9)
            except Exception:
                return 10**9

        waiting.sort(key=_pos)

# Send final_alert when patient has 3 or 4 patients ahead (position 4 or 5)
        target = None
        for entry in waiting:
           if _pos(entry) in {4, 5}:
               target = entry
               break

        if not target:
            return

        next_token = target

        pid = str(next_token.get("patient_id") or "").strip()
        if not pid:
            return

        token_id, token = QueueManagementService._find_active_token_for_patient(
            db=db,
            doctor_id=doctor_id,
            hospital_id=hospital_id,
            patient_id=pid,
        )
        if not token_id:
            return
        if bool(token.get("final_alert_sent")):
            return

        usnap = db.collection(COLLECTIONS["USERS"]).document(pid).get()
        if not QueueManagementService._is_doc_exists(usnap):
            return
        u = usnap.to_dict() or {}
        phone = str(u.get("phone") or "").strip()
        if not phone:
            return

        patient_name = str(u.get("name") or token.get("patient_name") or "Patient")
        token_number = str(token.get("formatted_token") or token.get("token_number") or "")

        try:
            await send_template_message(phone, tpl, [patient_name, token_number])
        except Exception:
            pass

        try:
            db.collection(COLLECTIONS["TOKENS"]).document(token_id).set(
                {"final_alert_sent": True, "final_alert_sent_at": QueueManagementService._now()},
                merge=True,
            )
        except Exception:
            pass

    # -------------------- Core operations --------------------
    @staticmethod
    async def add_patient_to_queue(hospital_id: str, doctor_id: str, patient_id: str) -> Dict[str, Any]:
        db = get_db()

        paused, reason = QueueManagementService._doctor_queue_paused(doctor_id)
        if paused:
            raise ValueError(f"Queue is paused: {reason}")

        # Determine next position by scanning active queue entries for doctor.
        qref = db.collection(COLLECTIONS["QUEUES"])
        docs = list(qref.where("doctor_id", "==", doctor_id).stream())
        active = [
            QueueManagementService._queue_doc_to_dict(d)
            for d in docs
            if str((d.to_dict() or {}).get("status") or "").lower() in ACTIVE_QUEUE_STATUSES
        ]
        next_pos = (max([int(x.get("queue_position") or 0) for x in active], default=0) or 0) + 1
        est = QueueManagementService._estimated_wait_minutes(next_pos)

        now = QueueManagementService._now()
        entry = {
            "hospital_id": hospital_id,
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "queue_position": int(next_pos),
            "status": "waiting",
            "estimated_wait_time": int(est),
            "created_at": now,
            "called_at": None,
            "updated_at": now,
            # Prevent duplicate “approaching” notifications
            "approaching_notified_at": None,
        }

        new_doc = qref.document()
        new_doc.set(entry)
        entry["queue_id"] = getattr(new_doc, "id", None) or getattr(new_doc, "doc_id", None)

        # Recompute positions/wait times to keep everything consistent and trigger smart notifications.
        await QueueManagementService.recalculate_for_doctor(doctor_id=doctor_id, hospital_id=hospital_id, reason="patient_added")

        QueueManagementService._broadcast_best_effort(
            QueueEvent(
                event_type="patient_added",
                doctor_id=doctor_id,
                hospital_id=hospital_id,
                payload={"queue_id": entry.get("queue_id"), "patient_id": patient_id},
            )
        )
        return entry

    @staticmethod
    async def call_next_patient(doctor_id: str) -> Optional[Dict[str, Any]]:
        paused, reason = QueueManagementService._doctor_queue_paused(doctor_id)
        if paused:
            raise ValueError(f"Queue is paused: {reason}")

        db = get_db()
        qref = db.collection(COLLECTIONS["QUEUES"])
        docs = list(qref.where("doctor_id", "==", doctor_id).stream())
        waiting = [
            (QueueManagementService._doc_id(d), d.to_dict() or {})
            for d in docs
            if str((d.to_dict() or {}).get("status") or "").lower() == "waiting"
        ]
        waiting = [(qid, dd) for (qid, dd) in waiting if qid]
        if not waiting:
            return None

        waiting.sort(key=lambda x: int((x[1].get("queue_position") or 10**9)))
        queue_id, data = waiting[0]  # type: ignore[misc]
        now = QueueManagementService._now()

        qref.document(queue_id).set(
            {"status": "called", "called_at": now, "updated_at": now},
            merge=True,
        )

        hospital_id = data.get("hospital_id")
        await QueueManagementService.recalculate_for_doctor(doctor_id=doctor_id, hospital_id=hospital_id, reason="patient_called")

        # TURN NOW alert (patient called)
        try:
            await QueueManagementService._send_turn_now_alert(doctor_id=doctor_id, hospital_id=hospital_id, qdata=data)
        except Exception:
            pass

        QueueManagementService._broadcast_best_effort(
            QueueEvent(
                event_type="patient_called",
                doctor_id=doctor_id,
                hospital_id=hospital_id,
                payload={"queue_id": queue_id, "patient_id": data.get("patient_id")},
            )
        )

        data = dict(data)
        data.update({"queue_id": queue_id, "status": "called", "called_at": now})
        return data

    @staticmethod
    async def complete_consultation(queue_id: str) -> Dict[str, Any]:
        db = get_db()
        qref = db.collection(COLLECTIONS["QUEUES"]).document(queue_id)
        snap = qref.get()
        if not QueueManagementService._is_doc_exists(snap):
            raise KeyError("Queue entry not found")
        data = snap.to_dict() or {}
        doctor_id = str(data.get("doctor_id") or "")
        hospital_id = data.get("hospital_id")

        now = QueueManagementService._now()
        qref.set({"status": "completed", "updated_at": now, "completed_at": now}, merge=True)

        # THANKYOU message (best-effort)
        try:
            tpl = str(TEMPLATES.get("THANKYOU") or "").strip()
        except Exception:
            tpl = ""
        if tpl:
            try:
                pid = str(data.get("patient_id") or "").strip()
                phone = ""
                patient_name = ""
                if pid:
                    usnap = db.collection(COLLECTIONS["USERS"]).document(pid).get()
                    if QueueManagementService._is_doc_exists(usnap):
                        u = usnap.to_dict() or {}
                        phone = str(u.get("phone") or u.get("mobile") or "").strip()
                        patient_name = str(u.get("name") or "").strip()

                if not phone and pid:
                    token_id, token = QueueManagementService._find_active_token_for_patient(
                        db=db,
                        doctor_id=doctor_id,
                        hospital_id=hospital_id,
                        patient_id=pid,
                    )
                    phone = str(token.get("patient_phone") or "").strip() if token_id else phone
                    if not patient_name:
                        patient_name = str(token.get("patient_name") or "").strip() if token_id else patient_name

                if phone:
                    await send_template_message(phone, tpl, [])
            except Exception as e:
                print(f"[ERROR] Failed to send thankyou message in queue service: {e}")

        await QueueManagementService.recalculate_for_doctor(doctor_id=doctor_id, hospital_id=hospital_id, reason="completed")
        # Auto-call next
        try:
            await QueueManagementService.call_next_patient(doctor_id=doctor_id)
        except Exception:
            pass

        QueueManagementService._broadcast_best_effort(
            QueueEvent(
                event_type="completed",
                doctor_id=doctor_id,
                hospital_id=hospital_id,
                payload={"queue_id": queue_id, "patient_id": data.get("patient_id")},
            )
        )
        return {"queue_id": queue_id, "status": "completed"}

    @staticmethod
    async def rejoin_queue(hospital_id: str, doctor_id: str, patient_id: str, from_queue_id: Optional[str] = None) -> Dict[str, Any]:
        # Rejoin is “add to end” by design.
        entry = await QueueManagementService.add_patient_to_queue(hospital_id=hospital_id, doctor_id=doctor_id, patient_id=patient_id)
        if from_queue_id:
            try:
                db = get_db()
                db.collection(COLLECTIONS["QUEUES"]).document(entry["queue_id"]).set({"rejoined_from_queue_id": from_queue_id}, merge=True)
            except Exception:
                pass
        return entry

    @staticmethod
    async def pause_queue(doctor_id: str, reason: str = "paused") -> None:
        db = get_db()
        db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id).set(
            {"queue_paused": True, "queue_pause_reason": reason, "queue_paused_at": QueueManagementService._now()},
            merge=True,
        )

    @staticmethod
    async def resume_queue(doctor_id: str) -> None:
        db = get_db()
        db.collection(COLLECTIONS["DOCTORS"]).document(doctor_id).set(
            {"queue_paused": False, "queue_pause_reason": None, "queue_resumed_at": QueueManagementService._now()},
            merge=True,
        )

    # -------------------- Maintenance: reorder / recalc / notify / autoskip --------------------
    @staticmethod
    async def recalculate_for_doctor(doctor_id: str, hospital_id: Optional[str], reason: str) -> None:
        db = get_db()
        qcol = db.collection(COLLECTIONS["QUEUES"])
        docs = list(qcol.where("doctor_id", "==", doctor_id).stream())

        active_docs: List[Tuple[str, Dict[str, Any]]] = []
        for d in docs:
            dd = d.to_dict() or {}
            if str(dd.get("status") or "").lower() in ACTIVE_QUEUE_STATUSES:
                did = QueueManagementService._doc_id(d)
                if did:
                    active_docs.append((did, dd))

        # Stable ordering by (queue_position, created_at)
        def _created_key(v: Any) -> float:
            dt = QueueManagementService._to_dt(v)
            return dt.timestamp() if dt else 0.0

        active_docs.sort(
            key=lambda x: (
                int(x[1].get("queue_position") or 10**9),
                _created_key(x[1].get("created_at")),
            )
        )

        now = QueueManagementService._now()
        consult_minutes = QueueManagementService._doctor_consult_minutes(db, doctor_id)
        # Batch update positions + wait times
        for idx, (doc_id, dd) in enumerate(active_docs, start=1):
            new_pos = idx
            new_wait = QueueManagementService._estimated_wait_minutes(new_pos, consult_minutes)
            updates: Dict[str, Any] = {
                "queue_position": int(new_pos),
                "estimated_wait_time": int(new_wait),
                "updated_at": now,
            }
            qcol.document(doc_id).set(updates, merge=True)

        # FINAL ALERT (position 2) after positions are updated (also covers skipped patients)
        try:
            await QueueManagementService._send_final_alert_for_doctor(doctor_id=doctor_id, hospital_id=hospital_id)
        except Exception:
            pass

        # QUEUE UPDATE alerts (LONG/MEDIUM/SHORT rules)
        try:
            await QueueManagementService._send_queue_update_alerts_for_doctor(doctor_id=doctor_id, hospital_id=hospital_id)
        except Exception:
            pass

        await QueueManagementService._smart_notify_for_doctor(doctor_id=doctor_id, hospital_id=hospital_id)

        QueueManagementService._broadcast_best_effort(
            QueueEvent(
                event_type="queue_recalculated",
                doctor_id=doctor_id,
                hospital_id=hospital_id,
                payload={"reason": reason, "active_count": len(active_docs)},
            )
        )

    @staticmethod
    async def _smart_notify_for_doctor(doctor_id: str, hospital_id: Optional[str]) -> None:
        db = get_db()
        qcol = db.collection(COLLECTIONS["QUEUES"])
        docs = list(qcol.where("doctor_id", "==", doctor_id).stream())

        # Notify waiting patients only, once.
        waiting: List[Tuple[str, Dict[str, Any]]] = []
        for d in docs:
            dd = d.to_dict() or {}
            if str(dd.get("status") or "").lower() == "waiting":
                did = QueueManagementService._doc_id(d)
                if did:
                    waiting.append((did, dd))

        if not waiting:
            return

        def _pos(dd: Dict[str, Any]) -> int:
            try:
                return int(dd.get("queue_position") or 10**9)
            except Exception:
                return 10**9

        waiting.sort(key=lambda x: _pos(x[1]))

        for qid, dd in waiting:
            pos = _pos(dd)
            est = int(dd.get("estimated_wait_time") or 0)
            already = QueueManagementService._to_dt(dd.get("approaching_notified_at")) is not None
            if already:
                continue

            if pos <= int(QUEUE_SMART_NOTIFY_POSITION_THRESHOLD) or est <= int(QUEUE_SMART_NOTIFY_WAIT_THRESHOLD_MINUTES):
                # Look up phone number
                pid = dd.get("patient_id")
                if not pid:
                    continue
                usnap = db.collection(COLLECTIONS["USERS"]).document(str(pid)).get()
                if not QueueManagementService._is_doc_exists(usnap):
                    continue
                u = usnap.to_dict() or {}
                phone = u.get("phone")
                if not phone:
                    continue

                message = "Your turn is approaching. Please reach the hospital."
                # Send on both channels by default; can be refined later per-user settings.
                await NotificationService.send_whatsapp_message(phone, message)
                await NotificationService.send_sms_message(phone, message)

                qcol.document(qid).set({"approaching_notified_at": QueueManagementService._now()}, merge=True)
                QueueManagementService._broadcast_best_effort(
                    QueueEvent(
                        event_type="smart_notification",
                        doctor_id=doctor_id,
                        hospital_id=hospital_id,
                        payload={"queue_id": qid, "patient_id": pid, "queue_position": pos, "estimated_wait_time": est},
                    )
                )

    @staticmethod
    async def autoskip_cycle() -> Dict[str, Any]:
        """Run one autoskip pass across all doctors (called entries past grace)."""
        paused_doctors: set[str] = set()
        db = get_db()
        qcol = db.collection(COLLECTIONS["QUEUES"])
        docs = list(qcol.stream())
        now = QueueManagementService._now()
        grace = timedelta(minutes=int(QUEUE_GRACE_TIME_MINUTES or 3))

        # Group candidates per doctor
        to_skip: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
        for d in docs:
            dd = d.to_dict() or {}
            if str(dd.get("status") or "").lower() != "called":
                continue

            doctor_id = str(dd.get("doctor_id") or "")
            if not doctor_id:
                continue
            if doctor_id in paused_doctors:
                continue

            paused, _ = QueueManagementService._doctor_queue_paused(doctor_id)
            if paused:
                paused_doctors.add(doctor_id)
                continue

            called_at = QueueManagementService._to_dt(dd.get("called_at"))
            if not called_at:
                continue
            if now - called_at > grace:
                did = QueueManagementService._doc_id(d)
                if did:
                    to_skip.setdefault(doctor_id, []).append((did, dd))

        skipped_count = 0
        touched_doctors: List[Tuple[str, Optional[str]]] = []
        for doctor_id, items in to_skip.items():
            for qid, dd in items:
                qcol.document(qid).set({"status": "skipped", "skipped_at": now, "updated_at": now}, merge=True)
                skipped_count += 1
                touched_doctors.append((doctor_id, dd.get("hospital_id")))

                # Send skipped template + update token status best-effort
                try:
                    hospital_id = dd.get("hospital_id")
                    pid = str(dd.get("patient_id") or "").strip()
                    if pid:
                        token_id, token = QueueManagementService._find_active_token_for_patient(
                            db=db,
                            doctor_id=doctor_id,
                            hospital_id=hospital_id,
                            patient_id=pid,
                        )
                    else:
                        token_id, token = None, {}

                    if token_id and not bool(token.get("skip_message_sent")):
                        try:
                            tpl = str(TEMPLATES.get("RESCHEDULED") or "").strip()
                        except Exception:
                            tpl = ""

                        # Get phone + patient name
                        usnap = db.collection(COLLECTIONS["USERS"]).document(pid).get() if pid else None
                        u = usnap.to_dict() if usnap and QueueManagementService._is_doc_exists(usnap) else {}
                        phone = str(u.get("phone") or token.get("patient_phone") or "").strip()
                        patient_name = str(u.get("name") or token.get("patient_name") or "Patient")
                        token_number = str(token.get("formatted_token") or token.get("token_number") or "")

                        if phone and tpl:
                            try:
                                await send_template_message(phone, tpl, [patient_name, token_number])
                            except Exception:
                                pass

                        try:
                            skip_count = int(token.get("skip_count") or 0) + 1
                        except Exception:
                            skip_count = 1

                        try:
                            db.collection(COLLECTIONS["TOKENS"]).document(token_id).set(
                                {
                                    "status": "skipped",
                                    "skipped_at": now,
                                    "skip_count": skip_count,
                                    "skip_message_sent": True,
                                    "skip_message_sent_at": now,
                                    "updated_at": now,
                                },
                                merge=True,
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

                QueueManagementService._broadcast_best_effort(
                    QueueEvent(
                        event_type="auto_skipped",
                        doctor_id=doctor_id,
                        hospital_id=dd.get("hospital_id"),
                        payload={"queue_id": qid, "patient_id": dd.get("patient_id")},
                    )
                )

            # Reorder/recalc after skips for this doctor
            hospital_id = items[0][1].get("hospital_id") if items and isinstance(items[0][1], dict) else None
            await QueueManagementService.recalculate_for_doctor(doctor_id=doctor_id, hospital_id=hospital_id, reason="auto_skip")

            # Move queue forward: call next waiting patient
            try:
                await QueueManagementService.call_next_patient(doctor_id=doctor_id)
            except Exception:
                pass

        return {"skipped": skipped_count, "doctors_touched": len(set([d for d, _ in touched_doctors]))}


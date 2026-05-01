import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, List

from app.services.whatsapp_service import send_template_message
from app.database import get_db
from app.config import COLLECTIONS


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


async def schedule_at(run_at: datetime, template_name: str, token_context: Dict[str, Any], params: List[str]) -> None:
    now = datetime.now(timezone.utc)
    run_at_utc = run_at
    try:
        if run_at_utc.tzinfo is None:
            run_at_utc = run_at_utc.replace(tzinfo=timezone.utc)
        else:
            run_at_utc = run_at_utc.astimezone(timezone.utc)
    except Exception:
        run_at_utc = now

    delay = max(0.0, (run_at_utc - now).total_seconds())

    async def _runner():
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            to = str(token_context.get("patient_phone") or "").strip()
            if not to:
                return
            await send_template_message(to, template_name, params)
        except Exception:
            return

    try:
        asyncio.create_task(_runner())
    except Exception:
        await _runner()


async def _build_token_context(token: Dict[str, Any]) -> Dict[str, Any]:
    db = next(get_db())
    ctx: Dict[str, Any] = dict(token or {})

    try:
        patient_id = ctx.get("patient_id")
        if patient_id and not ctx.get("patient_phone"):
            try:
                usnap = db.collection(COLLECTIONS["USERS"]).document(str(patient_id)).get()
                if getattr(usnap, "exists", False):
                    u = usnap.to_dict() or {}
                    ctx["patient_phone"] = u.get("phone") or u.get("mobile")
                    ctx["patient_name"] = ctx.get("patient_name") or u.get("name")
            except Exception:
                pass

        doctor_id = ctx.get("doctor_id")
        if doctor_id and not ctx.get("doctor_name"):
            try:
                dsnap = db.collection(COLLECTIONS["DOCTORS"]).document(str(doctor_id)).get()
                if getattr(dsnap, "exists", False):
                    d = dsnap.to_dict() or {}
                    ctx["doctor_name"] = d.get("name")
                    ctx["department"] = ctx.get("department") or d.get("specialization") or d.get("subcategory") or d.get("department")
            except Exception:
                pass

        hospital_id = ctx.get("hospital_id")
        if hospital_id and not ctx.get("hospital_name"):
            try:
                hsnap = db.collection(COLLECTIONS["HOSPITALS"]).document(str(hospital_id)).get()
                if getattr(hsnap, "exists", False):
                    h = hsnap.to_dict() or {}
                    ctx["hospital_name"] = h.get("name")
            except Exception:
                pass
    finally:
        db.close()

    return ctx


# ✅ FIX: is_webhook_trigger flag and true dynamic wait minutes
async def schedule_messages(token: Dict[str, Any], is_webhook_trigger: bool = False) -> None:
    ctx = await _build_token_context(token)

    appt = _to_dt(ctx.get("appointment_time")) or _to_dt(ctx.get("appointment_date"))
    if appt is None:
        return

    try:
        if appt.tzinfo is None:
            appt = appt.replace(tzinfo=timezone.utc)
        else:
            appt = appt.astimezone(timezone.utc)
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    
    # Extract estimated wait time safely
    try:
        est_wait_time = float(ctx.get("estimated_wait_time") or 0)
    except (ValueError, TypeError):
        est_wait_time = 0.0

    # Calculate TRUE expected appointment time
    expected_appt = appt + timedelta(minutes=est_wait_time)
    true_wait_minutes = (expected_appt - now).total_seconds() / 60.0

    phone = str(ctx.get("patient_phone") or "").strip()
    if not phone:
        return

    # Only send initial confirmation if it's NOT coming from the Webhook YES reply (Stops Duplicate Bug)
    if not is_webhook_trigger:
        confirm_params = [
            str(ctx.get("doctor_name") or "Doctor"),
            str(ctx.get("patient_name") or "Patient"),
            str(ctx.get("hospital_name") or "Hospital"),
            str(ctx.get("department") or "General"),
            str(int(true_wait_minutes) if true_wait_minutes > 0 else "0"),
        ]
        await send_template_message(phone, "token_number", confirm_params)

    # Walk-In Protection
    if true_wait_minutes < 5:
        return

    # CASE 1: LONG
    if true_wait_minutes > 60:
        await schedule_at(
            expected_appt - timedelta(minutes=60),
            "queue_update_alert",
            ctx,
            [str(ctx.get("patient_name") or "Patient"), "1", str(int(true_wait_minutes - 60)), str(ctx.get("hospital_name") or "Clinic"), str(ctx.get("token_number") or "")]
        )
        await schedule_at(
            expected_appt - timedelta(minutes=30),
            "final_alert",
            ctx,
            [str(ctx.get("patient_name") or "Patient"), str(ctx.get("token_number") or "")]
        )
        await schedule_at(
            expected_appt - timedelta(minutes=10),
            "patient_call_alert",
            ctx,
            [str(ctx.get("patient_name") or "Patient")]
        )

    # CASE 2: MEDIUM
    elif 30 < true_wait_minutes <= 60:
        await schedule_at(
            expected_appt - timedelta(minutes=30),
            "final_alert",
            ctx,
            [str(ctx.get("patient_name") or "Patient"), str(ctx.get("token_number") or "")]
        )
        await schedule_at(
            expected_appt - timedelta(minutes=10),
            "patient_call_alert",
            ctx,
            [str(ctx.get("patient_name") or "Patient")]
        )

    # CASE 3: SHORT
    else:
        await schedule_at(
            now + timedelta(minutes=2),
            "final_alert",
            ctx,
            [str(ctx.get("patient_name") or "Patient"), str(ctx.get("token_number") or "")]
        )
        await schedule_at(
            expected_appt - timedelta(minutes=2),
            "patient_call_alert",
            ctx,
            [str(ctx.get("patient_name") or "Patient")]
        )


async def schedule_confirmation_checks(token_id: str, first_delay_minutes: int = 15, second_delay_minutes: int = 15) -> None:
    async def _check_and_remind():
        await asyncio.sleep(first_delay_minutes * 60)

        try:
            db = next(get_db())
            from app.models import Token

            token = db.query(Token).filter(Token.id == token_id).first()
            if not token:
                return

            if token.status == "pending":
                phone = token.patient_phone
                patient_name = token.patient_name or "Patient"

                if phone:
                    await send_template_message(phone, "reminder_for_confirmation", [])

                await asyncio.sleep(second_delay_minutes * 60)

                db.refresh(token)

                if token.status == "pending":
                    token.status = "cancelled"
                    token.cancelled_at = datetime.utcnow()
                    token.updated_at = datetime.utcnow()
                    db.commit()

                    if phone:
                        await send_template_message(phone, "cancelled", [patient_name])

                    try:
                        from app.services.queue_management_service import QueueManagementService
                        await QueueManagementService.recalculate_positions(
                            token.doctor_id, token.hospital_id, token.appointment_date
                        )
                    except Exception:
                        pass

                    await asyncio.sleep(2 * 60)

                    if phone:
                        await send_template_message(phone, "template", [])

        except Exception as e:
            return
        finally:
            try:
                db.close()
            except Exception:
                pass

    try:
        asyncio.create_task(_check_and_remind())
    except Exception:
        await _check_and_remind()


async def schedule_skip_messages(token_id: str) -> None:
    async def _runner():
        await asyncio.sleep(10 * 60) 

        try:
            db = next(get_db())
            from app.db_models import Token

            token = db.query(Token).filter(Token.id == token_id).first()
            if not token:
                return

            current_status = str(token.status.value if hasattr(token.status, 'value') else token.status).lower()

            if current_status == "skipped":
                phone = token.patient_phone
                patient_name = token.patient_name or "Patient"
                token_number = str(token.display_code or token.token_number or "")

                if phone:
                    await send_template_message(phone, "skipped", [patient_name, token_number])
                    await asyncio.sleep(2 * 60)
                    await send_template_message(phone, "template", [])

        except Exception as e:
            return
        finally:
            try:
                db.close()
            except Exception:
                pass

    try:
        asyncio.create_task(_runner())
    except Exception:
        await _runner()
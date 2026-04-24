import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.db_models import PharmacyMedicine, Hospital
from app.services.go_pos_service import go_pos_service

logger = logging.getLogger(__name__)


async def sync_pos_to_postgres():
    """
    Background task to sync Go POS inventory into PostgreSQL every 5 minutes.
    Architecture: Go POS API -> Background Sync -> PostgreSQL
    """
    while True:
        logger.info("Starting background sync from Go POS...")
        db: Session = SessionLocal()
        try:
            # ✅ Fix: Fetch real hospital IDs from database instead of placeholder
            hospital_ids = [str(h.id) for h in db.query(Hospital.id).all()]

            if not hospital_ids:
                logger.warning("[SYNC] No hospitals found in database — skipping sync.")
                await asyncio.sleep(300)
                continue

            for hid in hospital_ids:
                # ✅ Guard: skip invalid hospital IDs
                if not hid or hid.strip().lower() in ("", "default", "none", "null"):
                    logger.warning(f"[SYNC] Skipping invalid hospital_id: '{hid}'")
                    continue

                try:
                    inventory = await go_pos_service.get_inventory(hid)
                    if not inventory:
                        logger.info(f"[SYNC] No inventory returned for hospital {hid} — skipping.")
                        continue

                    # Batch update/insert logic
                    updated = 0
                    inserted = 0
                    for item in inventory:
                        # ✅ Guard: skip malformed items
                        if not item.get("product_id"):
                            logger.warning(f"[SYNC] Skipping item with no product_id: {item}")
                            continue

                        existing = db.query(PharmacyMedicine).filter(
                            PharmacyMedicine.product_id == item["product_id"],
                            PharmacyMedicine.hospital_id == hid,
                        ).first()

                        if existing:
                            existing.quantity = item.get("quantity", existing.quantity)
                            existing.selling_price = item.get("price", existing.selling_price)
                            existing.updated_at = datetime.now(timezone.utc)
                            updated += 1
                        else:
                            new_med = PharmacyMedicine(
                                product_id=item["product_id"],
                                name=item.get("name", "Unknown"),
                                quantity=item.get("quantity", 0),
                                selling_price=item.get("price", 0.0),
                                hospital_id=hid,
                                created_at=datetime.now(timezone.utc),
                            )
                            db.add(new_med)
                            inserted += 1

                    db.commit()
                    logger.info(f"[SYNC] Hospital {hid}: {updated} updated, {inserted} inserted.")

                except Exception as e:
                    logger.error(f"[SYNC] Failed to sync hospital {hid}: {e}")
                    db.rollback()

        except Exception as e:
            logger.error(f"[SYNC] Unexpected error during background sync: {e}")
            db.rollback()
        finally:
            db.close()

        # Wait 5 minutes before next sync
        await asyncio.sleep(300)
import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.db_models import PharmacyMedicine
from app.services.go_pos_service import go_pos_service
from sqlalchemy import select, update

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
            # For this example, we'd iterate over all hospitals or a specific list
            # hospital_ids = db.query(Hospital.id).all()
            hospital_ids = ["default"] # Placeholder
            
            for hid in hospital_ids:
                inventory = await go_pos_service.get_inventory(hid)
                if not inventory:
                    continue
                
                # Batch update/insert logic
                for item in inventory:
                    # Optimized: Check and update existing or insert new
                    existing = db.query(PharmacyMedicine).filter(
                        PharmacyMedicine.product_id == item["product_id"],
                        PharmacyMedicine.hospital_id == hid
                    ).first()
                    
                    if existing:
                        existing.quantity = item["quantity"]
                        existing.selling_price = item["price"]
                        existing.updated_at = datetime.now(timezone.utc)
                    else:
                        new_med = PharmacyMedicine(
                            product_id=item["product_id"],
                            name=item["name"],
                            quantity=item["quantity"],
                            selling_price=item["price"],
                            hospital_id=hid,
                            created_at=datetime.now(timezone.utc)
                        )
                        db.add(new_med)
                
                db.commit()
                logger.info(f"Synced {len(inventory)} items for hospital {hid}")
                
        except Exception as e:
            logger.error(f"Error during background sync: {e}")
            db.rollback()
        finally:
            db.close()
            
        # Wait for 5 minutes
        await asyncio.sleep(300)

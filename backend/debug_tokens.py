
import os
import sys
from datetime import datetime
from sqlalchemy import func

# Add project root to path
sys.path.append(os.getcwd())

from app.database import get_db_session
from app.db_models import Token

def check_tokens():
    db = get_db_session()
    try:
        doctor_id = "5b110146-e002-404f-9111-546d3ad71fb5"
        today = datetime.utcnow().date()
        
        print(f"Checking tokens for doctor: {doctor_id}")
        print(f"Date: {today}")
        
        # 1. Check all tokens for this doctor today
        all_tokens = db.query(Token).filter(
            Token.doctor_id == doctor_id,
            func.date(Token.appointment_date) == today
        ).all()
        
        print(f"\nTotal tokens found for today: {len(all_tokens)}")
        for i, t in enumerate(all_tokens):
            print(f"Token {i+1}: ID={t.id}, Number={t.token_number}, Status={t.status}, Date={t.appointment_date}")
            
        # 2. Check the specific query used in the route
        patients_ahead = db.query(Token).filter(
            Token.doctor_id == doctor_id,
            Token.status.in_(["waiting", "confirmed", "pending", "called", "in_consultation"]),
            func.date(Token.appointment_date) == today
        ).count()
        
        print(f"\nPatients ahead count (using route logic): {patients_ahead}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_tokens()

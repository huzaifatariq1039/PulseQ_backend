"""
Migration script to add doctor leave management fields to queues and tokens tables.

Run this script to update your database schema:
    python migrate_add_doctor_leave_fields.py
"""

from sqlalchemy import create_engine, text
from app.config import DATABASE_URL
import os

def run_migration():
    """Add new columns for doctor leave management"""
    
    # Get database URL from environment or config
    db_url = os.getenv("DATABASE_URL") or DATABASE_URL
    
    if not db_url:
        print("ERROR: DATABASE_URL not configured")
        return
    
    print(f"Connecting to database...")
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        print("Adding fields to 'queues' table...")
        
        # Add fields to queues table
        queue_columns = [
            ("paused", "BOOLEAN DEFAULT FALSE"),
            ("queue_paused", "BOOLEAN DEFAULT FALSE"),
            ("queue_pause_reason", "VARCHAR(255)"),
        ]
        
        for col_name, col_type in queue_columns:
            try:
                sql = text(f"ALTER TABLE queues ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                conn.execute(sql)
                conn.commit()
                print(f"  ✓ Added '{col_name}' to queues table")
            except Exception as e:
                print(f"  ✗ Error adding '{col_name}' to queues: {e}")
        
        print("\nAdding fields to 'tokens' table...")
        
        # Add fields to tokens table
        token_columns = [
            ("doctor_unavailable", "BOOLEAN DEFAULT FALSE"),
            ("doctor_unavailable_reason", "VARCHAR(255)"),
            ("leave_action", "VARCHAR(100)"),
            ("suggested_doctor_id", "VARCHAR"),
            ("suggested_doctor_name", "VARCHAR(100)"),
            ("rescheduled_at", "TIMESTAMP WITH TIME ZONE"),
        ]
        
        for col_name, col_type in token_columns:
            try:
                sql = text(f"ALTER TABLE tokens ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                conn.execute(sql)
                conn.commit()
                print(f"  ✓ Added '{col_name}' to tokens table")
            except Exception as e:
                print(f"  ✗ Error adding '{col_name}' to tokens: {e}")
    
    print("\n✅ Migration completed successfully!")

if __name__ == "__main__":
    run_migration()

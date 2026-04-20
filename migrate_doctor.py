
import os
import sys

# Add the project root to sys.path to allow importing from app
sys.path.append(os.getcwd())

from sqlalchemy import text
from app.database import engine

def run_migration():
    print("Connecting to DigitalOcean database...")
    try:
        with engine.connect() as connection:
            print("Running migration queries...")
            
            # SQL commands to modify the schema
            sql = """
            -- 1. Remove the phone column from doctors table
            ALTER TABLE doctors DROP COLUMN IF EXISTS phone;

            -- 2. Ensure available_days exists as JSONB (PostgreSQL handles JSON as JSONB mostly)
            -- This is a safety check in case it was missing
            DO $$ 
            BEGIN 
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name='doctors' AND column_name='available_days') THEN
                    ALTER TABLE doctors ADD COLUMN available_days JSONB DEFAULT '[]';
                END IF;
            END $$;
            """
            
            connection.execute(text(sql))
            connection.commit()
            print("✅ Migration successful: 'phone' removed, 'available_days' verified.")
            
            # Verify the current columns
            result = connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='doctors'"))
            columns = [row[0] for row in result.fetchall()]
            print(f"Current columns in 'doctors' table: {columns}")
            
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")

if __name__ == "__main__":
    run_migration()

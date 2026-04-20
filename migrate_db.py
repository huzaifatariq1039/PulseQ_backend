import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add current directory to path so we can import app
sys.path.append(os.getcwd())

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL not found in environment variables.")
    sys.exit(1)

# Handle potential 'postgres://' vs 'postgresql://' issue
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def migrate():
    print(f"Connecting to database: {DATABASE_URL.split('@')[-1]}") # Log host only for safety
    
    with engine.connect() as conn:
        # 1. Add hospital_id to users table
        print("Checking for users.hospital_id column...")
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN hospital_id VARCHAR;"))
            print("Successfully added hospital_id to users table.")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("Column users.hospital_id already exists.")
            else:
                print(f"Error adding hospital_id to users: {e}")
        
        # 2. Add user_id to doctors table
        print("Checking for doctors.user_id column...")
        try:
            conn.execute(text("ALTER TABLE doctors ADD COLUMN user_id VARCHAR;"))
            print("Successfully added user_id to doctors table.")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("Column doctors.user_id already exists.")
            else:
                print(f"Error adding user_id to doctors: {e}")
        
        # 3. Add foreign key constraints (optional but recommended)
        print("Adding foreign key constraints...")
        try:
            conn.execute(text("ALTER TABLE users ADD CONSTRAINT fk_users_hospital FOREIGN KEY (hospital_id) REFERENCES hospitals (id);"))
            print("Added foreign key for users.hospital_id.")
        except Exception:
            print("Foreign key for users.hospital_id already exists or hospitals table missing.")
            
        try:
            conn.execute(text("ALTER TABLE doctors ADD CONSTRAINT fk_doctors_user FOREIGN KEY (user_id) REFERENCES users (id);"))
            print("Added foreign key for doctors.user_id.")
        except Exception:
            print("Foreign key for doctors.user_id already exists.")

        conn.commit()
        print("\nMigration completed successfully!")

if __name__ == "__main__":
    migrate()

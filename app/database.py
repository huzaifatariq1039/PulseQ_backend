from sqlalchemy import create_engine, text, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from app.config import DATABASE_URL
import logging
import time

logger = logging.getLogger("performance.db")

# Create base class for models
Base = declarative_base()

# SQLAlchemy engine creation logic
def get_engine():
    """Get or create SQLAlchemy engine using DATABASE_URL with optimized connection pooling"""
    engine = create_engine(
        DATABASE_URL, 
        pool_size=30,              # Increased from 20 for better concurrency
        max_overflow=20,           # Increased from 10 for burst traffic
        pool_timeout=30,           # Timeout after 30 seconds of waiting for a connection
        pool_recycle=1800,         # Recycle connections every 30 minutes to avoid stale links
        pool_pre_ping=True,        # Check connection health before using
        pool_use_lifo=True,        # Use LIFO for better connection reuse
        echo=False,                # Disable SQL logging in production (enable for debugging)
    )
    
    # Add SQLAlchemy event listeners for query performance tracking
    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault('query_start_time', []).append(time.time())
    
    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if conn.info.get('query_start_time'):
            total = time.time() - conn.info['query_start_time'].pop(-1)
            total_ms = total * 1000
            
            # Log slow queries (>100ms)
            if total_ms > 100:
                logger.warning(f"🐌 Slow query ({total_ms:.2f}ms): {statement[:150]}...")
            elif total_ms > 50:
                logger.info(f"⏱️ Query ({total_ms:.2f}ms): {statement[:150]}...")
    
    return engine

# Shared engine instance
engine = get_engine()

# Sessionmaker configuration
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency to get DB session
def get_db() -> Session:
    """Get database session using SessionLocal"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# For direct DB access (non-generator)
def get_db_session() -> Session:
    """Get database session directly using SessionLocal"""
    return SessionLocal()

# Initialize database tables
def init_db():
    """Create all tables using the global engine"""
    try:
        from app import db_models  # Import all models to register with Base
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully!")
    except Exception as e:
        print(f"⚠️ Could not create tables: {e}")
        print("⚠️ Tables may already exist or database is unavailable")

# Legacy compatibility - MockFirestore interface for gradual migration
class MockFirestore:
    """Mock Firestore for compatibility during migration"""
    
    def collection(self, collection_name: str):
        from sqlalchemy.orm import Session
        db = get_db_session()
        return MockCollection(collection_name, db)

class MockCollection:
    """Mock collection for compatibility"""
    
    def __init__(self, name: str, db: Session):
        self.name = name
        self.db = db
    
    def document(self, doc_id: str = None):
        return MockDocument(self.name, doc_id, self.db)
    
    def where(self, field: str, op: str, value):
        return MockQuery(self.name, self.db).where(field, op, value)
    
    def stream(self):
        return MockStream(self.name, self.db)
    
    def limit(self, limit: int):
        return MockQuery(self.name, self.db, limit=limit)

class MockDocument:
    """Mock document for compatibility"""
    
    def __init__(self, collection_name: str, doc_id: str, db: Session):
        self.collection_name = collection_name
        self.doc_id = doc_id
        self.db = db
    
    def set(self, data: dict):
        # Placeholder - implement based on your models
        return self
    
    def get(self):
        return MockDocumentSnapshot(self.collection_name, self.doc_id, self.db)
    
    def update(self, data: dict):
        # Placeholder - implement based on your models
        return self

class MockDocumentSnapshot:
    """Mock document snapshot for compatibility"""
    
    def __init__(self, collection_name: str, doc_id: str, db: Session):
        self.collection_name = collection_name
        self.doc_id = doc_id
        self.db = db
        self._data = None
    
    @property
    def exists(self):
        # Placeholder - query actual database
        return False
    
    def to_dict(self):
        return self._data or {}

class MockQuery:
    """Mock query for compatibility"""
    
    def __init__(self, collection_name: str, db: Session, filters: list = None, limit: int = None):
        self.collection_name = collection_name
        self.db = db
        self.filters = filters or []
        self._limit = limit
    
    def where(self, field: str, op: str, value):
        self.filters.append((field, op, value))
        return self
    
    def stream(self):
        return MockStream(self.collection_name, self.db, self.filters, self._limit)
    
    def limit(self, limit: int):
        self._limit = limit
        return self

class MockStream:
    """Mock stream for compatibility"""
    
    def __init__(self, collection_name: str, db: Session, filters: list = None, limit: int = None):
        self.collection_name = collection_name
        self.db = db
        self.filters = filters or []
        self.limit = limit
        self._items = []
    
    def __iter__(self):
        # Placeholder - return empty iterator
        return iter(self._items)

# Legacy compatibility
COLLECTIONS = {
    "USERS": "users",
    "HOSPITALS": "hospitals",
    "DOCTORS": "doctors",
    "TOKENS": "tokens",
    "PAYMENTS": "payments",
    "DEPARTMENTS": "departments",
    "APPOINTMENTS": "appointments",
    "ACTIVITIES": "activities",
    "QUICK_ACTIONS": "quick_actions",
    "COUNTERS": "counters",
    "CAPACITY": "capacity",
    "IDEMPOTENCY": "idempotency",
    "PHARMACY_ITEMS": "pharmacy_items",
    "PHARMACY_STOCK_LOGS": "pharmacy_stock_logs",
    "PHARMACY_SALES": "pharmacy_sales",
    "PHARMACY_MEDICINES": "pharmacy_medicines",
    "PHARMACY_PRESCRIPTIONS": "pharmacy_prescriptions",
    "QUEUES": "queues",
}

# Legacy function for compatibility
def initialize_firebase():
    """Legacy function - now initializes PostgreSQL connection"""
    try:
        # Test connection
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Database connection successful")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        # Don't raise - let the app start even if DB is not available
        print("⚠️ Continuing without database - will retry on first request")

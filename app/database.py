import firebase_admin
from firebase_admin import credentials, firestore
from app.config import FIREBASE_SERVICE_ACCOUNT_KEY, TESTING_MODE, COLLECTIONS as FIRESTORE_COLLECTIONS
import json
from typing import Dict, List, Any
from datetime import datetime

# Canonical Firestore collection names (keep in sync with app/config.py)
COLLECTIONS = FIRESTORE_COLLECTIONS

# Mock data storage for testing mode
_mock_data = {collection_name: {} for collection_name in set(COLLECTIONS.values())}

class MockFirestore:
    """Mock Firestore for testing without Firebase"""

    def collection(self, collection_name: str):
        return MockCollection(collection_name)

class MockCollection:
    def __init__(self, name: str):
        self.name = name

    def document(self, doc_id: str = None):
        return MockDocument(self.name, doc_id)

    def where(self, field: str, op: str, value: Any):
        return MockQuery(self.name).where(field, op, value)

    def stream(self):
        return MockStream(self.name)

    def limit(self, limit: int):
        return MockQuery(self.name, limit=limit)

class MockDocument:
    def __init__(self, collection_name: str, doc_id: str = None):
        self.collection_name = collection_name
        self.doc_id = doc_id or f"mock_{len(_mock_data[collection_name]) + 1}"

    def set(self, data: Dict):
        _mock_data[self.collection_name][self.doc_id] = data
        return self

    def get(self):
        return MockDocumentSnapshot(self.collection_name, self.doc_id)

    def update(self, data: Dict):
        if self.doc_id in _mock_data[self.collection_name]:
            _mock_data[self.collection_name][self.doc_id].update(data)
        return self

class MockDocumentSnapshot:
    def __init__(self, collection_name: str, doc_id: str):
        self.collection_name = collection_name
        self.doc_id = doc_id

    def exists(self):
        return self.doc_id in _mock_data[self.collection_name]

    def to_dict(self):
        return _mock_data[self.collection_name].get(self.doc_id, {})

class MockQuery:
    def __init__(self, collection_name: str, filters: List = None, limit: int = None):
        self.collection_name = collection_name
        self.filters = filters or []
        self._limit = limit

    def where(self, field: str, op: str, value: Any):
        self.filters.append((field, op, value))
        return self

    def stream(self):
        return MockStream(self.collection_name, self.filters, self._limit)

    def limit(self, limit: int):
        self._limit = limit
        return self

class MockStream:
    def __init__(self, collection_name: str, filters: List = None, limit: int = None):
        self.collection_name = collection_name
        self.filters = filters or []
        self.limit = limit
        self._items = []
        self._prepare_items()

    def _prepare_items(self):
        collection_data = _mock_data[self.collection_name]

        def _coerce(v: Any):
            try:
                to_dt = getattr(v, 'to_datetime', None)
                if callable(to_dt):
                    return to_dt()
            except Exception:
                pass
            return v

        def _match(data: Dict[str, Any]) -> bool:
            for field, op, value in self.filters:
                left = _coerce(data.get(field))
                right = _coerce(value)
                try:
                    if op == "==":
                        if left != right:
                            return False
                    elif op == ">=":
                        if left is None or left < right:
                            return False
                    elif op == "<=":
                        if left is None or left > right:
                            return False
                    elif op == ">":
                        if left is None or left <= right:
                            return False
                    elif op == "<":
                        if left is None or left >= right:
                            return False
                    else:
                        return False
                except Exception:
                    return False
            return True

        for doc_id, data in collection_data.items():
            if self.filters:
                if _match(data):
                    self._items.append(MockDocumentSnapshot(self.collection_name, doc_id))
            else:
                self._items.append(MockDocumentSnapshot(self.collection_name, doc_id))

        if self.limit:
            self._items = self._items[:self.limit]

    def __iter__(self):
        return iter(self._items)

# Initialize Firebase Admin SDK
def initialize_firebase():
    """Initialize Firebase Admin SDK with service account credentials"""
    global TESTING_MODE  # <--- ADD THIS LINE HERE
    import os
    
    try:
        # Check if we should even try (if explicitly set to True in config)
        if TESTING_MODE:
            print("🧪 Testing mode enabled - using mock database")
            return

        if not firebase_admin._apps:
            firebase_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
            if firebase_json:
                try:
                    cred_dict = json.loads(firebase_json)
                    cred = credentials.Certificate(cred_dict)
                    print("✅ Using Firebase credentials from environment variable")
                except json.JSONDecodeError as e:
                    print(f"❌ Invalid JSON in FIREBASE_SERVICE_ACCOUNT_JSON: {e}")
                    raise
            else:
                # IMPORTANT: Ensure this path matches one we fixed earlier!
                firebase_path = "/home/ubuntu/PulseQ_Backend/firebase_key.json"
                cred = credentials.Certificate(firebase_path)
                print(f"✅ Using Firebase credentials from file: {firebase_path}")
            
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized successfully")
            
            # SUCCESS! Now we flip switch to False so get_db() uses real DB
            TESTING_MODE = False 
            
        else:
            print("ℹ️ Firebase already initialized")
            TESTING_MODE = False # Ensure it's False if already active

    except Exception as e:
        print(f"❌ Error initializing Firebase: {e}")
        print("🧪 Falling back to testing mode")
        TESTING_MODE = True # Fallback if real init fails

# Get Firestore database client
def get_db():
    """Get Firestore database client"""
    if TESTING_MODE:
        return MockFirestore()
    return firestore.client()

# Initialize Firebase when module is imported
initialize_firebase()

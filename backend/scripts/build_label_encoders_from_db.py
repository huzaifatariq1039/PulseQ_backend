"""
Build label encoders for doctor and disease_type from Firestore data.

This script queries your Firestore database to find all unique doctor names and
disease types, then saves them to models/label_encoders.pkl for use by AIEngine.

Usage:
    python scripts/build_label_encoders_from_db.py

Environment:
    - Must have GOOGLE_APPLICATION_CREDENTIALS set or Firebase service account in config.
    - Requires firebase-admin and scikit-learn.
"""
import os
import sys
import pickle
from typing import Dict, List, Set
from pathlib import Path

# Add project root to path so we can import app modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sklearn.preprocessing import LabelEncoder
from app.database import get_db, COLLECTIONS

# Output paths
MODELS_DIR = project_root / "models"
OUT_PATH = MODELS_DIR / "label_encoders.pkl"
BAK_PATH = MODELS_DIR / "label_encoders.backup.pkl"

# Collections and fields to scan for categories
CATEGORY_SOURCES = [
    {"collection": COLLECTIONS["TOKENS"], "field": "doctor"},
    {"collection": COLLECTIONS["TOKENS"], "field": "disease_type"},
    {"collection": COLLECTIONS["DOCTORS"], "field": "name"},
]

def get_unique_values(collection: str, field: str) -> Set[str]:
    """Fetch all unique values for a field in a collection."""
    db = get_db()
    query = db.collection(collection).select([field])
    
    try:
        # Use a set to deduplicate
        values = set()
        for doc in query.stream():
            data = doc.to_dict()
            if field in data and data[field]:
                values.add(str(data[field]).strip())
        return values
    except Exception as e:
        print(f"⚠️ Error querying {collection}.{field}: {e}")
        return set()

def build_encoders() -> Dict[str, LabelEncoder]:
    """Build encoders from database values."""
    # Collect unique values for each category
    categories = {
        "doctor": set(),
        "disease_type": set(),
    }
    
    # Map fields to their target category
    field_to_category = {
        "doctor": "doctor",
        "name": "doctor",  # From DOCTORS collection
        "disease_type": "disease_type",
    }
    
    # Query all sources
    for source in CATEGORY_SOURCES:
        collection = source["collection"]
        field = source["field"]
        
        if field in field_to_category:
            cat = field_to_category[field]
            values = get_unique_values(collection, field)
            categories[cat].update(values)
            print(f"Found {len(values)} unique values in {collection}.{field}")
    
    # Ensure we have at least one value per category
    for cat, values in categories.items():
        if not values:
            print(f"⚠️ No values found for {cat}, using default")
            categories[cat] = {"<UNK>"}
    
    # Build and fit encoders
    encoders = {}
    for cat, values in categories.items():
        le = LabelEncoder()
        # Sort for consistent ordering across runs
        le.fit(sorted(values))
        encoders[cat] = le
        print(f"Encoder for {cat}: {len(le.classes_)} classes")
    
    return encoders

def backup_existing():
    """Back up existing encoders if they exist."""
    if OUT_PATH.exists() and not BAK_PATH.exists():
        try:
            with open(OUT_PATH, "rb") as src, open(BAK_PATH, "wb") as dst:
                dst.write(src.read())
            print(f"Backed up existing encoders to {BAK_PATH}")
        except Exception as e:
            print(f"⚠️ Could not back up existing encoders: {e}")

def main():
    # Ensure models directory exists
    MODELS_DIR.mkdir(exist_ok=True)
    
    # Back up existing encoders
    backup_existing()
    
    # Build new encoders
    print("Building encoders from database...")
    encoders = build_encoders()
    
    # Save to file
    with open(OUT_PATH, "wb") as f:
        pickle.dump(encoders, f)
    
    print(f"✅ Saved {len(encoders)} encoders to {OUT_PATH}")
    for cat, le in encoders.items():
        print(f"  - {cat}: {len(le.classes_)} classes")
        if len(le.classes_) <= 10:  # Print all if not too many
            print(f"    Classes: {', '.join(le.classes_)}")

if __name__ == "__main__":
    main()

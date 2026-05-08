import os
import pickle

from sklearn.preprocessing import LabelEncoder

# Edit these lists to include ALL categories your model expects
CATEGORIES = {
    "doctor": [
        "Dr Ajmal",
        # add more doctor names here, e.g., "Dr Sana", "Dr Ali"
    ],
    "disease_type": [
        "Cardiac",
        # add more disease types here, e.g., "ENT", "Ortho", "Dermatology"
    ],
}

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
OUT_PATH = os.path.join(MODELS_DIR, "label_encoders.pkl")
BAK_PATH = os.path.join(MODELS_DIR, "label_encoders.backup.pkl")


def build_encoders(categories: dict) -> dict:
    encoders = {}
    for col, values in categories.items():
        le = LabelEncoder()
        # Ensure unique, stable order
        uniq = sorted(set(values))
        if not uniq:
            raise SystemExit(f"No categories provided for '{col}'")
        le.fit(uniq)
        encoders[col] = le
    return encoders


def main():
    os.makedirs(MODELS_DIR, exist_ok=True)

    # Backup existing file
    if os.path.exists(OUT_PATH) and not os.path.exists(BAK_PATH):
        try:
            with open(OUT_PATH, "rb") as rf, open(BAK_PATH, "wb") as wf:
                wf.write(rf.read())
            print(f"Backup written to {BAK_PATH}")
        except Exception as e:
            print(f"Warning: failed to write backup: {e}")

    encoders = build_encoders(CATEGORIES)

    with open(OUT_PATH, "wb") as f:
        pickle.dump(encoders, f)

    print(f"Wrote label_encoders.pkl with keys: {list(encoders.keys())}")
    for k, le in encoders.items():
        print(f"  - {k}: classes_={list(le.classes_)}")


if __name__ == "__main__":
    main()

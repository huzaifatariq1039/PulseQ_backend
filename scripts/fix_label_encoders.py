import os
import sys
import types
import pickle
import numpy as np

try:
    from sklearn.preprocessing import LabelEncoder
except Exception:
    LabelEncoder = None  # Best effort; script can still inspect types by name

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
SRC_PATH = os.path.join(MODELS_DIR, "label_encoders.pkl")
BAK_PATH = os.path.join(MODELS_DIR, "label_encoders.backup.pkl")

EXPECTED_KEYS = ["doctor", "disease_type"]


def is_label_encoder(obj) -> bool:
    # Robust check without importing sklearn strictly
    if LabelEncoder is not None and isinstance(obj, LabelEncoder):
        return True
    return obj.__class__.__name__ == "LabelEncoder"


def load_obj(path):
    # Compatibility shim: some pickles reference a top-level module named
    # 'LabelEncoder'. We alias it to sklearn's LabelEncoder (if available)
    # or a dummy placeholder just to allow unpickling.
    try:
        from sklearn.preprocessing import LabelEncoder as SkLabelEncoder  # type: ignore
        shim = types.ModuleType("LabelEncoder")
        shim.LabelEncoder = SkLabelEncoder
        # Some pickles may reference LabelEncoder.dtype; map it to numpy.dtype
        shim.dtype = np.dtype  # type: ignore[attr-defined]
        sys.modules.setdefault("LabelEncoder", shim)
    except Exception:
        # Fallback: provide a minimal dummy to satisfy the import during unpickle
        class _DummyLabelEncoder:  # pragma: no cover
            def __init__(self, *args, **kwargs):
                pass
        shim = types.ModuleType("LabelEncoder")
        shim.LabelEncoder = _DummyLabelEncoder
        try:
            shim.dtype = np.dtype  # type: ignore[attr-defined]
        except Exception:
            pass
        sys.modules.setdefault("LabelEncoder", shim)

    with open(path, "rb") as f:
        return pickle.load(f)


def save_obj(path, obj):
    with open(path, "wb") as f:
        pickle.dump(obj, f)


def main():
    if not os.path.exists(SRC_PATH):
        raise SystemExit(f"File not found: {SRC_PATH}")

    enc = load_obj(SRC_PATH)

    # Case 1: already a dict
    if isinstance(enc, dict):
        missing = [k for k in EXPECTED_KEYS if k not in enc]
        if not missing:
            print("label_encoders.pkl is already a dict with expected keys. No change.")
            return
        else:
            print(f"Found dict but missing keys: {missing}. Will write back only available keys.")
            # keep only known keys
            fixed = {k: enc[k] for k in EXPECTED_KEYS if k in enc}
            if not fixed:
                raise SystemExit("Existing dict has none of the expected keys; aborting.")
    else:
        # Case 2: list/tuple/ndarray
        seq = None
        if isinstance(enc, (list, tuple)):
            seq = list(enc)
        elif isinstance(enc, np.ndarray):
            seq = list(enc.ravel())
        else:
            raise SystemExit(f"Unsupported label_encoders.pkl type: {type(enc).__name__}")

        # Filter only plausible encoders
        seq = [x for x in seq if hasattr(x, "classes_") or is_label_encoder(x)]
        if len(seq) < 2:
            raise SystemExit(
                "Could not infer two encoders from file. Provide a dict {'doctor': encoder, 'disease_type': encoder}."
            )

        # Heuristic: assume order [doctor, disease_type]
        fixed = {"doctor": seq[0], "disease_type": seq[1]}
        print("Converted sequence of encoders to dict: {'doctor','disease_type'}")

    # Backup original
    if not os.path.exists(BAK_PATH):
        try:
            with open(SRC_PATH, "rb") as rf, open(BAK_PATH, "wb") as wf:
                wf.write(rf.read())
            print(f"Backup written to {BAK_PATH}")
        except Exception as e:
            print(f"Warning: failed to write backup: {e}")

    # Save fixed dict
    save_obj(SRC_PATH, fixed)
    print(f"Wrote fixed dict with keys {list(fixed.keys())} to {SRC_PATH}")


if __name__ == "__main__":
    main()

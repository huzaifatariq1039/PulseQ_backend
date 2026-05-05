import os
import sys
import types
import pickle
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
# Point to the actual models folder and correct filenames
MODEL_PATH = os.path.join(BASE_DIR, "models", "opd_wait_time_model.pkl")
ENCODER_PATH = os.path.join(BASE_DIR, "models", "label_encoders.pkl")


class AIEngine:
    def __init__(self):
        self.model = None
        self.encoders = None

        # EXACT order and names used during training
        self.expected_features = [
            "hour_of_day",
            "day_of_week",
            "patients_ahead_of_user",
            "patients_in_queue",
            "queue_length_last_10_min",
            "queue_velocity",
            "last_patient_duration",
            "avg_service_time_last_5",
            "avg_service_time_last_10",
            "avg_service_time_doctor_historic",
            "doctors_available",
            "avg_wait_time_this_hour_past_week",
            "avg_wait_time_this_weekday_past_month",
            "Age",
            "Doctor Name",
            "clinic_type",
            "Disease"
        ]
        
        # Mapping from input names to expected feature names
        self.feature_mapping = {
            'age': 'Age',
            'doctor': 'Doctor Name',
            'disease_type': 'Disease',
            'avg_service_time_last_30': 'avg_service_time_last_10',
            'avg_service_time_doctor_history': 'avg_service_time_doctor_historic'
        }

    def load(self):
        # Compatibility shim: some pickles reference a top-level module named
        # 'LabelEncoder'. We alias it to sklearn's LabelEncoder for unpickling.
        try:
            from sklearn.preprocessing import LabelEncoder as SkLabelEncoder  # type: ignore
            shim = types.ModuleType("LabelEncoder")
            shim.LabelEncoder = SkLabelEncoder
            # Some pickles may reference LabelEncoder.dtype; map it to numpy.dtype
            shim.dtype = np.dtype  # type: ignore[attr-defined]
            sys.modules.setdefault("LabelEncoder", shim)
        except Exception:
            pass

        with open(MODEL_PATH, "rb") as f:
            self.model = pickle.load(f)

        with open(ENCODER_PATH, "rb") as f:
            self.encoders = pickle.load(f)

        print("AI Model Loaded Successfully")

    def _safe_encode(self, column, value):
        encoder = self.encoders.get(column)
        if encoder:
            if value in encoder.classes_:
                return encoder.transform([value])[0]
            else:
                return 0  # default for unseen (Prevents crashing on new hospitals!)
        return value
        
    def _encode_clinic_type(self, clinic_type):
        """Encode clinic_type to integer using stored encoder or default mapping."""
        if isinstance(clinic_type, (int, float)):
            return int(clinic_type)
            
        # Try to use stored encoder first
        if 'clinic_type' in self.encoders:
            return self._safe_encode('clinic_type', clinic_type)
            
        # Default mapping if no encoder is found
        clinic_mapping = {
            'General': 0,
            'Specialist': 1
        }
        return clinic_mapping.get(str(clinic_type).title(), 0)  # Default to 0 if not found

    def predict_duration(self, data_dict):
        """
        Predict consultation duration using the trained XGBoost model.
        """
        # Make a copy to avoid modifying the input
        features = data_dict.copy()
        
        # =========================================================
        # CLEANUP: Pop unused text to prevent processing errors
        # =========================================================
        features.pop("Name", None)
        features.pop("Service_Duration", None)
        features.pop("doctor_type", None) # Not in expected_features list

        # Apply feature name mapping
        for old_name, new_name in self.feature_mapping.items():
            if old_name in features and new_name not in features:
                features[new_name] = features.pop(old_name)
        
        # Set default values for required features if missing
        if 'queue_length_last_10_min' not in features:
            features['queue_length_last_10_min'] = features.get('patients_in_queue', 0)
        
        # Ensure all numeric features are actually numbers
        numeric_features = [
            "hour_of_day", "day_of_week", "patients_ahead_of_user", "patients_in_queue",
            "queue_length_last_10_min", "queue_velocity", "last_patient_duration",
            "avg_service_time_last_5", "avg_service_time_last_10", "avg_service_time_doctor_historic",
            "doctors_available", "avg_wait_time_this_hour_past_week", "avg_wait_time_this_weekday_past_month"
        ]
        for nf in numeric_features:
            if nf in features:
                try:
                    features[nf] = float(features[nf])
                except (ValueError, TypeError):
                    features[nf] = 0.0

        # Set default clinic_type if missing
        if 'clinic_type' not in features:
            features['clinic_type'] = 'General'
            
        # Encode clinic_type to integer before creating DataFrame
        features['clinic_type'] = self._encode_clinic_type(features['clinic_type'])
        
        # Encode categorical features - gracefully handles new hospital doctors
        for feat_name, possible_enc_keys in [('Doctor Name', ['Doctor Name', 'doctor']), 
                                             ('Disease', ['Disease', 'disease_type'])]:
            if feat_name in features:
                for enc_key in possible_enc_keys:
                    if enc_key in self.encoders:
                        features[feat_name] = self._safe_encode(enc_key, features[feat_name])
                        break 
        
        # Ensure all expected features are present
        missing = set(self.expected_features) - set(features.keys())
        if missing:
            print(f"[ERROR] AI Engine: Missing features: {missing}")
            raise ValueError(f"Missing required features: {', '.join(sorted(missing))}")
        
        try:
            # Create dataframe with features in exact order
            df = pd.DataFrame([features])[self.expected_features]
            
            # Make prediction and round to nearest whole number
            if hasattr(self.model, 'predict'):
                prediction = float(self.model.predict(df)[0])
                return int(round(prediction))
            else:
                raise ValueError("Model object has no 'predict' method")
            
        except Exception as e:
            print(f"❌ AI MODEL predict_duration FAILED: {e}")
            import traceback
            traceback.print_exc()
            raise ValueError(f"Prediction failed: {str(e)}")

# Instantiate the engine
ai_engine = AIEngine()
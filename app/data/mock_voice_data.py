# Mock data for Voice Assistant (simulated DB)

USERS = {
    # Simulated per-user active token and queue snapshot for "today"
    "12345": {
        "token_number": "A20",
        "appointment_date": "2025-10-06",
        "people_ahead": 5,
        "estimated_wait_minutes": 20,
        "now_serving": "A17",
        "total_queue": 42,
        "assigned_doctor_id": "doc_1",
        "hospital_id": "hosp_1",
    },
    "67890": {
        "token_number": "B15",
        "appointment_date": "2025-10-06",
        "people_ahead": 1,
        "estimated_wait_minutes": 3,
        "now_serving": "B14",
        "total_queue": 18,
        "assigned_doctor_id": "doc_2",
        "hospital_id": "hosp_1",
    },
}

DOCTORS = {
    "doc_1": {"name": "Dr. Ayesha Khan", "specialization": "Cardiologist"},
    "doc_2": {"name": "Dr. Omar Ali", "specialization": "Dermatologist"},
}

HOSPITALS = {
    "hosp_1": {
        "name": "City Hospital",
        "address": "123 Health Ave, Karachi, Pakistan",
        "address_short": "Block 5, Clifton, Karachi",
        "maps_link": "https://maps.google.com/?q=City+Hospital+Karachi",
    }
}

QUEUE = {
    "next_token_number": "A21"
}

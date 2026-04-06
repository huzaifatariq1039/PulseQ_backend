import firebase_admin
import psycopg2
from firebase_admin import credentials, firestore

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

db = firestore.client()

#PostgreSQL connection
conn = psycopg2.connect(
    dbname="PulseQ",
    user="postgres",
    password="Ist@2004",
    host="localhost",
    port="5432"
)

cur = conn.cursor()

print("Both Firebase and PostgreSQL connected successfully!")

# ID Maps
user_map = {}
hospital_map = {}
doctor_map = {}
token_map = {}

# USERS MIGRATION
print("Migrating users...")

docs = db.collection("users").stream()

for doc in docs:
    data = doc.to_dict()

    cur.execute("""
        INSERT INTO users (firebase_id, name, email, phone, role)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """, (
        doc.id,
        data.get("name"),
        data.get("email"),
        data.get("phone"),
        data.get("role", "patient")
    ))

    new_id = cur.fetchone()[0]
    user_map[doc.id] = new_id

conn.commit()

print("Users migrated!")
print("User map:", user_map)

cur.close()
conn.close()
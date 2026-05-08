# PulseQ WhatsApp Notification Scheduler (Node)

This service schedules and sends WhatsApp reminders for patient tokens using **Meta WhatsApp Cloud API**, backed by **Firestore**.

## What it does

- `scheduleTokenMessages(token)` creates a message plan based on time-to-appointment and stores messages in Firestore collection `notifications_queue` as `pending`.
- A cron worker runs every minute to send due `pending` messages and marks them `sent`.
- Before sending, it checks **stop conditions** (token status `in_consultation` / `completed` / `cancelled`). If hit, it cancels remaining `pending` messages for that token.
- Supports **instant** event-driven messages via webhooks:
  - queue alert: “Your turn is near…”
  - final call: “Please proceed to doctor now.”
- Fail-safe retries: **2 retries** (3 total attempts). Errors are stored in Firestore on the notification doc.

## Setup

```bash
cd node-notification-service
npm install
copy .env.template .env
```

Set:
- `FIREBASE_SERVICE_ACCOUNT_JSON` (service account JSON string)
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`

Run:

```bash
npm start
```

Health check: `GET /health`

## API

- `POST /schedule/token`

Body:

```json
{
  "token_id": "firestoreTokenDocId",
  "patient_id": "userId",
  "phone": "03xxxxxxxxx",
  "appointment_time": "2026-03-18T18:30:00.000Z",
  "queue_position": 7
}
```

- `POST /events/queue-alert`
- `POST /events/final-call`

Body:

```json
{ "token_id": "firestoreTokenDocId", "patient_id": "userId", "phone": "03xxxxxxxxx" }
```


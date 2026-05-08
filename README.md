# PulseQ Monorepo

This repository contains the backend and frontend for PulseQ in a single monorepo.

## Structure

- `backend/` - FastAPI backend, database helpers, migration scripts, and the Node notification service
- `frontend/` - Angular frontend

## Prerequisites

- Node.js 18+ and npm
- Python 3.11+ (or the version your backend supports)
- PostgreSQL

## Environment Files

- Backend env file: `backend/.env`
- Frontend env values are managed through Angular environment files in `frontend/src/environments/`

The backend loads `backend/.env` automatically.
Setup (One-time)
Backend Setup
cd /home/saif/Downloads/PulseQ_backend/backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
Frontend Setup
cd /home/saif/Downloads/PulseQ_backend/frontend
npm install

Running the Project
Option 1: Run in Separate Terminals (Recommended)
Terminal 1 - Backend (Port 8000):
cd /home/saif/Downloads/PulseQ_backend/backend
source venv/bin/activate  # On Windows: venv\Scripts\activate
source .venv/bin/activate && uvicorn main:app --reload --host 127.0.0.1 --port 8000
Terminal 2 - Frontend (Port 4200):
cd /home/saif/Downloads/PulseQ_backend/frontend
npm start
Then open your browser to: http://localhost:4200


## First-Time Setup

### 1) Clone and enter the repo

```bash
cd /home/Downloads/PulseQ_backend
```

### 2) Set up the backend

Create and fill in `backend/.env` with your local values.

Then install Python dependencies:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3) Set up the frontend

Install Node dependencies:

```bash
cd ../frontend
npm install
```

## Running the Project Locally

### Backend

From the `backend/` folder:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The actual app entrypoint is `main.py`, so the working command is:

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

From the `frontend/` folder:

```bash
npm start
```

This starts the Angular dev server using `proxy.conf.json`.

### Optional Node notification service

The backend also contains `backend/node-notification-service/`.
If you need it, install and run it separately:

```bash
cd ../backend/node-notification-service
npm install
npm start
```

## Notes

- Keep `backend/.env` local and never commit it.
- `node_modules/`, `dist/`, Python caches, and other generated artifacts are ignored by `.gitignore`.
- The frontend can be served independently, but for a normal local workflow you usually start backend first, then frontend.

## Suggested Run Order

1. Start PostgreSQL
2. Fill in `backend/.env`
3. Install backend dependencies
4. Install frontend dependencies with `npm install`
5. Run backend with `uvicorn`
6. Run frontend with `npm start`

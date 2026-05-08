# db_automation/config.py
# Database configuration — reads DATABASE_URL from .env (same as PulseQ app)

import os
from dotenv import load_dotenv

load_dotenv()

# Use the same DATABASE_URL as the main PulseQ app
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/pulseq"

# Async version (for asyncpg)
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

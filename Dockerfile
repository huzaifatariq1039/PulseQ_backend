# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV ENVIRONMENT production

# Set work directory
WORKDIR /app

# Install system dependencies (required for psycopg2-binary and other builds)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the entire project to the container
COPY . .

# Expose the port FastAPI will run on
# Digital Ocean App Platform will route traffic to this port
EXPOSE 8000

# Start the application using Gunicorn with Uvicorn workers for production
# We bind to 0.0.0.0 so the container is accessible externally
CMD ["gunicorn", "main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]

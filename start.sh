#!/bin/bash
set -e

gunicorn app.main:app -k uvicorn.workers.UvicornWorker

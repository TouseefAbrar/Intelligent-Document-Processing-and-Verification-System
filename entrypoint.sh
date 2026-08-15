#!/bin/sh
set -e

nginx

cd /app/backend
exec uvicorn app.main:app --host 0.0.0.0 --port 8001

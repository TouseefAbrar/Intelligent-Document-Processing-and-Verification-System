#!/bin/sh
set -e

PORT="${PORT:-80}"
export PORT

envsubst '${PORT}' < /etc/nginx/conf.d/default.conf > /tmp/default.conf
mv /tmp/default.conf /etc/nginx/conf.d/default.conf

nginx

cd /app/backend
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

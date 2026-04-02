#!/bin/bash
set -e

echo "Running database migrations..."
python /app/migrations/migrate_schema.py

echo "Running settings migrations..."
python /app/migrations/migrate_settings.py

echo "Initializing wallets..."
python /app/first_startup.py

echo "Starting API server..."
exec gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --preload --access-logfile - --error-logfile - wsgi:app

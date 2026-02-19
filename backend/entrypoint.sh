#!/bin/sh
set -e

echo "Waiting for database..."
python -c "from app.database import wait_for_db; wait_for_db()"

echo "Running migrations..."
alembic upgrade head

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

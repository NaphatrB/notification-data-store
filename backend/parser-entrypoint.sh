#!/bin/sh
set -e

echo "Waiting for database..."
python -c "from app.db import wait_for_db; wait_for_db()"

echo "Running migrations..."
alembic upgrade head

echo "Starting parser..."
exec python -m app.parser "$@"

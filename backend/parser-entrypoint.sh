#!/bin/sh
set -e

echo "Waiting for database..."
python -c "
import os, time
import psycopg2

url = os.environ.get('RAW_DATABASE_URL', os.environ.get('DATABASE_URL', ''))
# Convert async URL to libpq format
dsn = url.replace('postgresql+asyncpg://', 'postgresql://').replace('postgresql+psycopg2://', 'postgresql://')

for attempt in range(1, 11):
    try:
        conn = psycopg2.connect(dsn)
        conn.close()
        print(f'Database ready (attempt {attempt}/10)')
        break
    except Exception as e:
        print(f'Database not ready (attempt {attempt}/10): {e}')
        if attempt == 10:
            raise RuntimeError('Database not reachable after 10 attempts')
        time.sleep(2)
"

echo "Starting parser..."
exec python -m app.parser "$@"

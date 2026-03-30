#!/bin/bash
set -e

# Wait for database
echo "Waiting for database..."

python -c "
import asyncio
import asyncpg
import os
import sys
import time

async def check_db():
    uri = os.getenv('DATABASE_URL')
    if not uri:
        print('DATABASE_URL not set')
        sys.exit(1)

    uri = uri.replace('+asyncpg', '')

    for i in range(30):
        try:
            conn = await asyncpg.connect(uri)
            await conn.close()
            print('Database is ready!')
            return True
        except Exception as e:
            print(f'Database not ready yet ({e}), retrying {i+1}/30...')
            time.sleep(1)
    return False

if __name__ == '__main__':
    if not asyncio.run(check_db()):
        sys.exit(1)
"

# Run migrations/seeding only for the main API service (or if requested)
if [ "$1" == "api" ]; then
    echo "Running database seeding..."
    python -m app.core.database_seed

    echo "Starting Gunicorn..."
    exec gunicorn -k uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:8000 \
        --workers 4 \
        --timeout 120 \
        app.main:app
else
    echo "Running command: $@"
    exec "$@"
fi

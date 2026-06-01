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

# Create MinIO/S3 bucket if using S3 storage
if [ "$STORAGE_TYPE" = "s3" ]; then
    echo "Ensuring S3 bucket exists..."
    python -c "
import boto3
import os
from botocore.client import Config
from botocore.exceptions import ClientError

endpoint = os.getenv('S3_ENDPOINT_URL')
access_key = os.getenv('S3_ACCESS_KEY')
secret_key = os.getenv('S3_SECRET_KEY')
bucket_name = os.getenv('S3_BUCKET_NAME', 'plagiarism-uploads')

if not endpoint or not access_key:
    print('S3 not fully configured, skipping bucket creation')
    exit(0)

s3 = boto3.client(
    's3',
    endpoint_url=endpoint,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    config=Config(signature_version='s3v4'),
)

for attempt in range(10):
    try:
        s3.head_bucket(Bucket=bucket_name)
        print(f'Bucket \"{bucket_name}\" already exists.')
        break
    except ClientError as e:
        error_code = e.response['Error'].get('Code', '')
        if str(error_code) == '404' or 'NoSuchBucket' in str(error_code):
            try:
                s3.create_bucket(Bucket=bucket_name)
                print(f'Created bucket \"{bucket_name}\".')
                break
            except Exception as create_err:
                print(f'Failed to create bucket: {create_err}')
                break
        else:
            print(f'MinIO not ready yet (attempt {attempt+1}/10), retrying...')
            import time; time.sleep(2)
    except Exception as e:
        print(f'MinIO not ready yet (attempt {attempt+1}/10), retrying...')
        import time; time.sleep(2)
" || echo "Warning: Could not verify/create S3 bucket"
fi

# Run migrations/seeding only for the main API service (or if requested)
if [ "$1" == "api" ]; then
    echo "Running database seeding..."
    python -m app.core.database_seed

    echo "Starting Gunicorn..."
    exec gunicorn -k uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:8000 \
        --workers 4 \
        --timeout 300 \
        app.main:app
else
    echo "Running command: $@"
    exec "$@"
fi

import os

from celery import Celery
from app.core.config import settings


# include=: autodiscover_tasks() only looks for modules named `tasks`, so the
# worker never registered process_batch and rejected every job.
app = Celery('plagiarism_detection', include=['app.services.batch_processing'])

# Configure Celery with explicit settings
app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Resource management:
    # - Prefork pool with limited concurrency (ML work is CPU-heavy)
    # - Restart worker child after 5 tasks to prevent memory leaks from model accumulation
    # - Acknowledge tasks after completion (not before) so failed tasks are re-queued
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=5,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Hard stop for runaway jobs (huge scans/OCR); soft limit lets the task
    # mark the batch failed cleanly first.
    task_soft_time_limit=int(os.getenv("TASK_SOFT_TIME_LIMIT", "3300")),
    task_time_limit=int(os.getenv("TASK_TIME_LIMIT", "3600")),
    broker_connection_retry_on_startup=True,
)

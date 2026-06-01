from celery import Celery
from app.core.config import settings


app = Celery('plagiarism_detection')

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
)


# Import tasks
app.autodiscover_tasks(['app.services'])

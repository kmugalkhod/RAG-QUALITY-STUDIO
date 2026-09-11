from celery import Celery
from celery.signals import worker_process_init
from app.core.config import settings
from app.db.session import engine

celery = Celery(
    "rag_studio",
    broker=settings.redis_url,
    include=[
        "app.workers.processing",
        "app.workers.indexing",
        "app.workers.experiments",
    ],
)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=110,
    task_time_limit=120,
    broker_connection_timeout=3,
    task_publish_retry=False,
    broker_transport_options={
        "visibility_timeout": 420,
        "socket_timeout": 3,
        "socket_connect_timeout": 3,
    },
    worker_max_tasks_per_child=20,
    worker_max_memory_per_child=262144,
)


@worker_process_init.connect
def reset_connections(**kwargs):
    engine.dispose(close=False)

from celery import Celery
from celery.signals import worker_process_init
from app.core.config import settings
from app.db.session import engine

# Short steps (parse, chunk, embed, file-ingestion coordination) use the default
# queue; work that may run for up to an hour uses its own worker pool so it
# cannot occupy every worker that short steps need.
DEFAULT_QUEUE = "celery"
LONG_QUEUE = "long"

celery = Celery(
    "rag_studio",
    broker=settings.redis_url,
    include=[
        "app.workers.processing",
        "app.workers.indexing",
        "app.workers.ingestion",
        "app.workers.previews",
        "app.workers.experiments",
        "app.workers.deployed_answers",
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
    # Kilobytes of resident memory. A forked child already reports about 260 MB
    # of shared imports, so a lower limit would replace it after every task.
    worker_max_memory_per_child=409600,
    task_default_queue=DEFAULT_QUEUE,
    task_routes={
        "preview.sources": {"queue": LONG_QUEUE},
        "experiments.step": {"queue": LONG_QUEUE},
    },
)


@worker_process_init.connect
def reset_connections(**kwargs):
    engine.dispose(close=False)

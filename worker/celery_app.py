from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown
from kombu import Queue
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))
# Add current directory to path for tasks module
sys.path.insert(0, str(Path(__file__).parent))

# Get Redis URL from environment
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
DATABASE_URL = os.getenv('DATABASE_URL')

# Create Celery app
app = Celery('miaobu-worker')

# Configure Celery
app.conf.update(
    broker_url=REDIS_URL,
    result_backend=REDIS_URL,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,  # 55 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=3600,  # Results expire after 1 hour
)

# Define queues
app.conf.task_queues = (
    Queue('default', routing_key='default'),
    Queue('builds', routing_key='builds', priority=10),
    Queue('deployments', routing_key='deployments', priority=5),
)

# Task routing
app.conf.task_routes = {
    'tasks.build.*': {'queue': 'builds'},
    'tasks.deploy.*': {'queue': 'deployments'},
}

# Auto-discover tasks
app.autodiscover_tasks(['tasks'])

# Database session management
_db_session = None

@worker_process_init.connect
def init_worker(**kwargs):
    """Initialize worker process with database connection."""
    global _db_session
    if DATABASE_URL:
        from app.database import SessionLocal
        _db_session = SessionLocal()
        print("Worker process initialized with database connection")

@worker_process_shutdown.connect
def shutdown_worker(**kwargs):
    """Cleanup worker process resources."""
    global _db_session
    if _db_session:
        _db_session.close()
        print("Worker process shutdown, database connection closed")

def get_db():
    """Get database session for worker tasks."""
    if DATABASE_URL:
        from app.database import SessionLocal
        return SessionLocal()
    return None

if __name__ == '__main__':
    app.start()

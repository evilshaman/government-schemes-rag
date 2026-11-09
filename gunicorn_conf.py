"""
Gunicorn Production Server Configuration for Government Schemes Discovery Engine.
Optimized for high-concurrency container runtimes (Docker, Kubernetes, AWS ECS, GCP Cloud Run).
"""

import os
import multiprocessing

# Server Socket Binding
host = os.getenv("HOST", "0.0.0.0")
port = os.getenv("PORT", "8000")
bind = f"{host}:{port}"

# Worker Processes & Concurrency
# Formula: (2 * CPU Cores) + 1, or override via WEB_CONCURRENCY environment variable
default_workers = max(multiprocessing.cpu_count() * 2 + 1, 2)
workers = int(os.getenv("WEB_CONCURRENCY", default_workers))
worker_class = "uvicorn.workers.UvicornWorker"

# Worker Lifespan & Recycling (Prevents memory leaks in long-running processes)
max_requests = int(os.getenv("MAX_REQUESTS", "2000"))
max_requests_jitter = int(os.getenv("MAX_REQUESTS_JITTER", "200"))
timeout = int(os.getenv("TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("KEEP_ALIVE", "5"))

# Logging & Observability
loglevel = os.getenv("LOG_LEVEL", "info").lower()
accesslog = "-"  # Standard output
errorlog = "-"   # Standard error
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'

# Security & Process Identification
proc_name = "gov_schemes_rag_api"
daemon = False
preload_app = False  # Set False for safe SQLite WAL per-worker handle initialization

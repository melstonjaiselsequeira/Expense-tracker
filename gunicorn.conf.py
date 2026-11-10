import os
import multiprocessing

# Gunicorn production configuration
bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
workers = int(os.getenv("WEB_CONCURRENCY", min(multiprocessing.cpu_count() * 2, 4)))
threads = int(os.getenv("GUNICORN_THREADS", 4))
worker_class = "gthread"
timeout = int(os.getenv("GUNICORN_TIMEOUT", 120))
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")

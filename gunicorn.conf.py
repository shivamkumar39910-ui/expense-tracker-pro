import os

# Gunicorn configuration file for production deployment on Render
# High-concurrency threaded workers prevent single-request head-of-line blocking

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", 2))
threads = int(os.environ.get("GUNICORN_THREADS", 4))
worker_class = "gthread"
worker_tmp_dir = "/dev/shm"
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 50

print(f"[GUNICORN CONFIG] Loaded: workers={workers}, threads={threads}, worker_class={worker_class}")

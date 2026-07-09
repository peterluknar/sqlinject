FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Seed the DB once (the __main__ block no longer runs under gunicorn), then hand
# off to gunicorn. Concurrency is bounded to workers*threads so the app can't open
# a flood of MySQL connections under load on a small (1 vCPU) host.
CMD ["sh", "-c", "python -c 'from app import wait_for_db, init_db; wait_for_db(); init_db()' && exec gunicorn --bind 0.0.0.0:8000 --worker-class gthread --workers 2 --threads 4 --timeout 60 --max-requests 500 --max-requests-jitter 50 --worker-tmp-dir /dev/shm app:app"]

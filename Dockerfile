FROM python:3.11-slim

ARG BUILD_TEST=false

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/swap-service/ ./swap-service/
COPY app/migrations/ ./migrations/
COPY app/main.py .
COPY app/wsgi.py .
COPY app/first_startup.py .
COPY app/first-run.sh .
COPY app/backup.py .
COPY app/restore.py .

COPY data/bin/ ./data/bin/
RUN chmod +x ./data/bin/ordexcoind ./data/bin/ordexgoldd

COPY frontend/ ./frontend/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app
ENV API_HOST=0.0.0.0
ENV API_PORT=8000

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--preload", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]

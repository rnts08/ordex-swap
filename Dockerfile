FROM python:3.11-slim

ARG BUILD_TEST=false

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/swap-service/ ./swap-service/
COPY app/main.py .
COPY app/first_startup.py .
COPY app/first-run.sh .

RUN if [ "$BUILD_TEST" = "true" ]; then \
      COPY app/tests/ ./tests/; \
    fi

COPY data/bin/ /app/data/bin/
RUN chmod +x /app/data/bin/ordexcoind /app/data/bin/ordexgoldd

COPY frontend/ ./frontend/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app
ENV API_HOST=0.0.0.0
ENV API_PORT=8000

EXPOSE 8000

CMD ["python", "main.py"]

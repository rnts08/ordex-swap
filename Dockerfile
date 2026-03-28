FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl nginx && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy swap service
COPY swap-service/ ./swap-service/

# Copy main.py
COPY main.py .

# Copy daemon binaries for production mode
COPY data/bin/ordexcoind data/bin/ordexgoldd /app/data/bin/
RUN chmod +x /app/data/bin/ordexcoind /app/data/bin/ordexgoldd

# Copy frontend
COPY frontend/ ./frontend/

# Create nginx config
RUN mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
RUN rm -f /etc/nginx/sites-enabled/default

# Create nginx configuration - serves frontend + proxies API
RUN echo 'server { \
    listen 8080; \
    server_name _; \
\
    root /app/frontend; \
    index index.html; \
\
    location /api/ { \
        proxy_pass http://127.0.0.1:8000; \
        proxy_set_header Host $host; \
        proxy_set_header X-Real-IP $remote_addr; \
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; \
        proxy_set_header X-Forwarded-Proto $scheme; \
    } \
\
    location /health { \
        proxy_pass http://127.0.0.1:8000; \
    } \
\
    location / { \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/sites-available/ordex-swap

RUN ln -sf /etc/nginx/sites-available/ordex-swap /etc/nginx/sites-enabled/ordex-swap

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app
ENV API_HOST=127.0.0.1
ENV API_PORT=8000

EXPOSE 8080

CMD ["sh", "-c", "python main.py & nginx -g 'daemon off;'"]

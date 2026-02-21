# Builder stage
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
  gcc \
  g++ \
  libffi-dev \
  libssl-dev \
  libjpeg-dev \
  zlib1g-dev \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

COPY . .

# Create directories and user
RUN mkdir -p /app/logs /app/data && \
  useradd -m -u 1000 botuser && \
  chown -R botuser:botuser /app

USER botuser

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import sqlite3; conn = sqlite3.connect('/app/data/otc.db'); conn.execute('SELECT 1'); conn.close(); print('ok')" || exit 1

CMD ["python", "main.py"]
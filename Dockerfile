# Builder stage
FROM python:3.11-slim as builder

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

# Create logs directory and user
RUN mkdir -p /app/logs && \
  useradd -m -u 1000 botuser && \
  chown -R botuser:botuser /app

USER botuser

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD pgrep -f "python main.py" > /dev/null || exit 1

CMD ["python", "main.py"]
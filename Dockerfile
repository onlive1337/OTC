FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
  gcc \
  g++ \
  libffi-dev \
  libssl-dev \
  libjpeg-dev \
  zlib1g-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/logs

RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD pgrep -f "python main.py" > /dev/null || exit 1

CMD ["python", "main.py"]
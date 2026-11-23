FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt

COPY . .

# Create directories and user
RUN mkdir -p /app/logs /app/data && \
  useradd -m -u 1000 botuser && \
  chown -R botuser:botuser /app

USER botuser

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import sqlite3; conn = sqlite3.connect('/app/data/otc.db'); conn.execute('SELECT 1'); conn.close(); print('ok')" || exit 1

CMD ["python", "main.py"]

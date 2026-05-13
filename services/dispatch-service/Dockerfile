FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer cached separately from source)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app ./app

ENV PYTHONUNBUFFERED=1

EXPOSE 8003

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/healthz')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]

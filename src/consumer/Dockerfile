FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY src/consumer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/consumer/consumer.py .

# Create directories for logs
RUN mkdir -p /app/logs

# Run as non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Expose metrics port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/metrics', timeout=5)" || exit 1

CMD ["python", "consumer.py"]
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY src/producer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/producer/producer.py .

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs

# Run as non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import kafka; print('OK')" || exit 1

CMD ["python", "producer.py"]
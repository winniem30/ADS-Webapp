FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p uploads reports charts static/css static/js static/images

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/')" || exit 1

# Run with gunicorn (Linux)
CMD ["gunicorn", "app:app", "--timeout", "120", "--workers", "1", "--bind", "0.0.0.0:5000", "--access-logfile", "-", "--error-logfile", "-"]

# For Windows local testing, use: waitress-serve --port=5000 app:app

# Minimal Dockerfile for gprofiler-performance-studio test runner
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for psycopg2
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy test files and scripts
COPY . .

# Default command to run tests
CMD ["python", "run_tests.py"]
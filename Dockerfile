# Dockerfile untuk API dan Scoring services saja
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements dan install dependencies (tanpa crawler)
COPY api/requirements.txt ./api_requirements.txt
COPY scoring/requirements.txt ./scoring_requirements.txt

RUN pip install --no-cache-dir -r api_requirements.txt \
    && pip install --no-cache-dir -r scoring_requirements.txt

# Copy application code
COPY api ./api
COPY scoring ./scoring

# Create data directories
RUN mkdir -p scoring/data/scores

# Set environment variables
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Default command
CMD ["echo", "Please specify SERVICE_TYPE environment variable"]
# Multi-stage build untuk optimasi size
FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create app user (security best practice)
RUN useradd --create-home --shell /bin/bash app

WORKDIR /app

# Copy requirements first (better caching)
COPY api/requirements.txt scoring/requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip cache purge

# Copy application code
COPY --chown=app:app api ./api
COPY --chown=app:app scoring ./scoring

# Create data directories
RUN mkdir -p scoring/data/scores \
    && chown -R app:app /app

# Switch to non-root user
USER app

# Set environment variables
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Dynamic entrypoint based on SERVICE_TYPE
CMD if [ "$SERVICE_TYPE" = "api" ]; then \
        cd api && uvicorn main:app --host 0.0.0.0 --port 8000; \
    elif [ "$SERVICE_TYPE" = "scoring" ]; then \
        cd scoring && python scoring_consumer.py; \
    else \
        echo "Error: SERVICE_TYPE must be 'api' or 'scoring'"; exit 1; \
    fi
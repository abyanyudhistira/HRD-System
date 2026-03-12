# Multi-service Dockerfile - Optimized for Docker Compose
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome (needed for crawler service)
RUN wget -q -O /tmp/google-chrome-key.pub https://dl-ssl.google.com/linux/linux_signing_key.pub \
    && gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg /tmp/google-chrome-key.pub \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/* /tmp/google-chrome-key.pub

# Copy all requirements and install dependencies
COPY api/requirements.txt ./api_requirements.txt
COPY crawler/requirements.txt ./crawler_requirements.txt  
COPY scoring/requirements.txt ./scoring_requirements.txt

RUN pip install --no-cache-dir -r api_requirements.txt \
    && pip install --no-cache-dir -r crawler_requirements.txt \
    && pip install --no-cache-dir -r scoring_requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p crawler/data/output crawler/data/cookie crawler/profile scoring/data/scores

# Set environment variables
ENV PYTHONPATH=/app
ENV HEADLESS_MODE=true
ENV DISPLAY=:99

# Expose port
EXPOSE 8000

# Default command (will be overridden by docker-compose)
CMD ["echo", "Please specify SERVICE_TYPE environment variable"]
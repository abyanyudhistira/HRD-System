# Scoring Service Dockerfile for Railway
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create data directories
RUN mkdir -p data/scores

# Start scoring consumer
CMD ["python", "scoring_consumer.py"]

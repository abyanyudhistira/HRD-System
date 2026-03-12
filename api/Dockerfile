# Backend API Dockerfile for Railway
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose port
EXPOSE 8000

# Start API server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

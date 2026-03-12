#!/bin/bash
# Production start script for Railway

echo "Starting LinkedIn Crawler API..."

# Railway auto-installs dependencies from requirements.txt
# No need for venv in production

# Start API server
# Railway provides $PORT environment variable
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}

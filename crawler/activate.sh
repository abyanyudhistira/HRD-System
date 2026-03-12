#!/bin/bash

# Activate virtual environment
# Usage: source activate.sh

if [ ! -d "venv" ]; then
    echo "✗ Virtual environment not found!"
    echo "  Run setup first:"
    echo "  python3 -m venv venv"
    echo "  pip install -r requirements.txt"
    return 1 2>/dev/null || exit 1
fi

source venv/bin/activate

echo "✓ Virtual environment activated"
echo "  Python: $(which python)"
echo ""

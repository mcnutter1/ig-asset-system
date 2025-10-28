#!/bin/bash

# Database-driven Asset Tracker Poller Startup Script

echo "Starting Database-driven Asset Tracker Poller..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "Installing requirements..."
pip install -r requirements.txt

# Run the database poller
echo "Starting poller..."
python3 poller_db.py
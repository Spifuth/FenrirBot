#!/bin/bash
# Fenrir Bot - Run script
# Activates venv and starts the bot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Run setup.sh first:"
    echo "   ./scripts/setup.sh"
    exit 1
fi

# Check if user is in docker group, if not use sg
if groups | grep -q docker; then
    source venv/bin/activate
    exec python run.py
else
    echo "⚠️  Docker group not active in this session, using sg..."
    exec sg docker -c "cd $PROJECT_DIR && ./venv/bin/python run.py"
fi

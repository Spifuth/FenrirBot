#!/bin/bash
# Fenrir Bot - Setup script
# Creates virtual environment and installs dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "🐺 Fenrir Bot Setup"
echo "==================="
echo

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "   ✅ Created venv/"
else
    echo "📦 Virtual environment already exists"
fi

# Activate and install dependencies
echo
echo "📥 Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "   ✅ Dependencies installed"

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo
    echo "📝 Creating .env from template..."
    cp .env.example .env
    echo "   ✅ Created .env (edit this with your bot token!)"
fi

echo
echo "✅ Setup complete!"
echo
echo "Next steps:"
echo "  1. Edit .env with your Discord bot token and channel ID"
echo "  2. Run the bot:"
echo "     source venv/bin/activate"
echo "     python run.py"
echo

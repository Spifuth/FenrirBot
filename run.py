#!/usr/bin/env python3
"""
Fenrir Bot - Entry point

Usage:
    python run.py
    
Or with the venv:
    ./venv/bin/python run.py
"""

import sys

from src.bot import create_bot
from src.config import config


def main():
    """Main entry point"""
    print("🐺 Starting Fenrir Bot...")
    print()
    
    if not config:
        print("❌ Error: DISCORD_TOKEN not found in environment variables")
        print()
        print("   Create a .env file with your bot token:")
        print("   cp .env.example .env")
        print("   Then edit .env with your values")
        sys.exit(1)
    
    print("📦 Loading cogs...")
    bot = create_bot()
    bot.run(config.token)


if __name__ == "__main__":
    main()

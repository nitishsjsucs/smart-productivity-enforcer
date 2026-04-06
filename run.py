"""Quick start script for the Smart Productivity Enforcer."""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from smart_productivity_enforcer.config import Config
from smart_productivity_enforcer.daemon import ProductivityDaemon


async def main():
    """Run the productivity enforcer."""
    print("=" * 60)
    print("🧠 Smart Productivity Enforcer")
    print("=" * 60)
    
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  No API key found!")
        print("Please set GOOGLE_API_KEY or OPENAI_API_KEY in your .env file")
        print("\nExample .env file:")
        print("  GOOGLE_API_KEY=your-key-here")
        return
    
    config = Config.load()
    
    print(f"\n📋 Goal: {config.user_goal}")
    print(f"⏱️  Check interval: {config.check_interval_seconds}s")
    print(f"🤖 LLM: {config.llm.provider}/{config.llm.model}")
    print(f"🔒 Enforcement: {'Enabled' if config.enforcement.enabled else 'Disabled'}")
    
    print("\n" + "-" * 60)
    print("Press Ctrl+C to stop (if not in strict mode)")
    print("-" * 60 + "\n")
    
    daemon = ProductivityDaemon(config)
    
    duration = None
    if len(sys.argv) > 1:
        try:
            duration = int(sys.argv[1])
            print(f"🎯 Starting {duration}-minute focus session\n")
        except ValueError:
            pass
    
    await daemon.start(duration)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye! Stay productive!")

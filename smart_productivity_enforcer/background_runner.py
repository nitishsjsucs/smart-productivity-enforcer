"""Background runner script - launched by background_service.py"""

import sys
import asyncio
from pathlib import Path
from datetime import datetime

# PID file location
PID_FILE = Path.home() / ".smart-productivity-enforcer" / "daemon.pid"


def write_pid():
    """Write current process PID to file."""
    import os
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def cleanup():
    """Clean up PID file on exit."""
    if PID_FILE.exists():
        PID_FILE.unlink()


async def run_enforcer(session_name: str, duration_minutes: int, strict_mode: bool):
    """Run the enforcer daemon."""
    from smart_productivity_enforcer.daemon import ProductivityDaemon
    from smart_productivity_enforcer.config import Config
    
    # Write PID file
    write_pid()
    
    try:
        config = Config.load()
        
        # Find the session
        session = None
        for s in config.focus_sessions:
            if s.name == session_name:
                session = s
                break
        
        if not session:
            print(f"Session '{session_name}' not found")
            return
        
        # Override duration if specified
        if duration_minutes > 0:
            session.duration_minutes = duration_minutes
        
        # Start daemon
        daemon = ProductivityDaemon(config, session)
        await daemon.start()
        
    except Exception as e:
        print(f"Error running enforcer: {e}")
    finally:
        cleanup()


def main():
    if len(sys.argv) < 4:
        print("Usage: background_runner.py <session_name> <duration_minutes> <strict_mode>")
        sys.exit(1)
    
    session_name = sys.argv[1]
    duration_minutes = int(sys.argv[2])
    strict_mode = sys.argv[3].lower() == "true"
    
    print(f"[{datetime.now()}] Starting background enforcer")
    print(f"  Session: {session_name}")
    print(f"  Duration: {duration_minutes} min")
    print(f"  Strict: {strict_mode}")
    
    try:
        asyncio.run(run_enforcer(session_name, duration_minutes, strict_mode))
    except KeyboardInterrupt:
        print("Interrupted")
    finally:
        cleanup()


if __name__ == "__main__":
    main()

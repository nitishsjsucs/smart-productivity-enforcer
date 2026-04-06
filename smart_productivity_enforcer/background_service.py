"""Background service for running the productivity enforcer persistently."""

import os
import sys
import subprocess
import signal
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

# PID file location
PID_FILE = Path.home() / ".smart-productivity-enforcer" / "daemon.pid"
LOG_FILE = Path.home() / ".smart-productivity-enforcer" / "daemon.log"
SESSION_FILE = Path.home() / ".smart-productivity-enforcer" / "session.json"


def get_pid() -> Optional[int]:
    """Get the PID of the running daemon."""
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            # Check if process is actually running
            if is_process_running(pid):
                return pid
            else:
                # Stale PID file
                PID_FILE.unlink()
        except (ValueError, OSError):
            pass
    return None


def is_process_running(pid: int) -> bool:
    """Check if a process with given PID is running."""
    try:
        # On Windows, this doesn't kill but checks if process exists
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def save_session(session_name: str, duration_minutes: int, strict_mode: bool) -> None:
    """Save session info for background process."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    session_data = {
        "session_name": session_name,
        "duration_minutes": duration_minutes,
        "strict_mode": strict_mode,
        "start_time": datetime.now().isoformat()
    }
    SESSION_FILE.write_text(json.dumps(session_data))


def load_session() -> Optional[dict]:
    """Load session info."""
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return None


def clear_session() -> None:
    """Clear session info."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def start_background(session_name: str, duration_minutes: int, strict_mode: bool = True) -> bool:
    """
    Start the enforcer as a background process.
    Returns True if started successfully.
    """
    # Check if already running
    existing_pid = get_pid()
    if existing_pid:
        print(f"[!] Enforcer already running (PID: {existing_pid})")
        return False
    
    # Ensure directories exist
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Save session info
    save_session(session_name, duration_minutes, strict_mode)
    
    # Get the path to the runner script
    runner_script = Path(__file__).parent / "background_runner.py"
    
    # Start the background process using pythonw (no console window)
    # On Windows, use CREATE_NO_WINDOW flag
    if sys.platform == "win32":
        # Use pythonw to avoid console window
        python_exe = sys.executable.replace("python.exe", "pythonw.exe")
        if not Path(python_exe).exists():
            python_exe = sys.executable
        
        # Start detached process
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        process = subprocess.Popen(
            [python_exe, str(runner_script), session_name, str(duration_minutes), str(strict_mode)],
            stdout=open(LOG_FILE, "a"),
            stderr=subprocess.STDOUT,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True
        )
    else:
        # Unix-like systems
        process = subprocess.Popen(
            [sys.executable, str(runner_script), session_name, str(duration_minutes), str(strict_mode)],
            stdout=open(LOG_FILE, "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
    
    # Wait a moment and check if it started
    time.sleep(1)
    
    # Check if PID file was created
    pid = get_pid()
    if pid:
        print(f"[✓] Enforcer started in background (PID: {pid})")
        print(f"    Session: {session_name}")
        print(f"    Duration: {duration_minutes} minutes")
        print(f"    Strict mode: {strict_mode}")
        print(f"\n    Use 'spe stop' to stop (password required during session)")
        print(f"    Use 'spe status' to check status")
        return True
    else:
        print("[!] Failed to start background process")
        return False


def stop_background(password: Optional[str] = None) -> bool:
    """
    Stop the background enforcer.
    Returns True if stopped successfully.
    """
    pid = get_pid()
    if not pid:
        print("[!] No enforcer running")
        return False
    
    # Check if in strict session
    session = load_session()
    if session and session.get("strict_mode"):
        start_time = datetime.fromisoformat(session["start_time"])
        duration = session["duration_minutes"]
        elapsed = (datetime.now() - start_time).total_seconds() / 60
        
        if elapsed < duration:
            remaining = duration - elapsed
            if not password:
                print(f"[!] Session in progress ({remaining:.1f} min remaining)")
                print("    Use 'spe stop --password <your_password>' to force stop")
                return False
            # TODO: Verify password against config
            print(f"[!] Force stopping session ({remaining:.1f} min remaining)")
    
    # Kill the process
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], 
                         capture_output=True, check=True)
        else:
            os.kill(pid, signal.SIGTERM)
        
        # Clean up
        if PID_FILE.exists():
            PID_FILE.unlink()
        clear_session()
        
        print(f"[✓] Enforcer stopped (PID: {pid})")
        return True
        
    except Exception as e:
        print(f"[!] Failed to stop: {e}")
        return False


def get_status() -> dict:
    """Get the status of the background enforcer."""
    pid = get_pid()
    session = load_session()
    
    status = {
        "running": pid is not None,
        "pid": pid,
        "session": None
    }
    
    if session:
        start_time = datetime.fromisoformat(session["start_time"])
        duration = session["duration_minutes"]
        elapsed = (datetime.now() - start_time).total_seconds() / 60
        remaining = max(0, duration - elapsed)
        
        status["session"] = {
            "name": session["session_name"],
            "duration_minutes": duration,
            "elapsed_minutes": round(elapsed, 1),
            "remaining_minutes": round(remaining, 1),
            "strict_mode": session.get("strict_mode", False),
            "start_time": session["start_time"]
        }
    
    return status


def print_status() -> None:
    """Print formatted status."""
    status = get_status()
    
    if not status["running"]:
        print("● Enforcer: Not running")
        return
    
    print(f"● Enforcer: Running (PID: {status['pid']})")
    
    if status["session"]:
        s = status["session"]
        print(f"  Session: {s['name']}")
        print(f"  Duration: {s['duration_minutes']} minutes")
        print(f"  Elapsed: {s['elapsed_minutes']} minutes")
        print(f"  Remaining: {s['remaining_minutes']} minutes")
        print(f"  Strict mode: {'Yes' if s['strict_mode'] else 'No'}")

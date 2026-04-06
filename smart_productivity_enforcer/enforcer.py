"""Enforcement module - takes action on unproductive activity."""

import asyncio
import ctypes
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

import psutil

try:
    import win32gui
    import win32con
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

from smart_productivity_enforcer.config import Config, ProductivityLevel
from smart_productivity_enforcer.activity_monitor import ActivitySnapshot, WindowInfo
from smart_productivity_enforcer.llm_evaluator import EvaluationResult
from smart_productivity_enforcer.websocket_server import get_websocket_server


class Enforcer:
    """Enforces productivity by taking action on distracting activities."""
    
    def __init__(self, config: Config):
        self.config = config
        self.warning_shown = False
        self.warning_start_time: Optional[datetime] = None
        self.enforcement_log: list[dict] = []
        
    async def enforce(self, snapshot: ActivitySnapshot, evaluation: EvaluationResult) -> bool:
        """
        Take enforcement action based on evaluation.
        Returns True if action was taken.
        """
        if not self.config.enforcement.enabled:
            return False
        
        if not evaluation.should_close:
            return False
        
        if evaluation.classification not in [ProductivityLevel.UNPRODUCTIVE, ProductivityLevel.BLOCKED]:
            return False
        
        # Close immediately - no warnings, no popups
        action_taken = await self._take_action(snapshot, evaluation)
        return action_taken
    
    async def _show_warning(self, snapshot: ActivitySnapshot, evaluation: EvaluationResult) -> None:
        """Show a warning notification before taking action."""
        title = "Productivity Enforcer Warning"
        message = f"⚠️ Unproductive activity detected!\n\n"
        message += f"Reason: {evaluation.reason}\n"
        message += f"This will be closed in {self.config.enforcement.warning_duration_seconds} seconds.\n"
        message += f"Return to productive work to dismiss."
        
        await self._show_notification(title, message)
        
        self._log_enforcement({
            "type": "warning",
            "timestamp": datetime.now().isoformat(),
            "window": snapshot.active_window.title if snapshot.active_window else "Unknown",
            "reason": evaluation.reason
        })
    
    async def _show_notification(self, title: str, message: str) -> None:
        """Show a Windows notification."""
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(title, message, duration=5, threaded=True)
        except ImportError:
            if HAS_PYAUTOGUI:
                pyautogui.alert(text=message, title=title, button='OK')
            else:
                print(f"[NOTIFICATION] {title}: {message}")
    
    async def _take_action(self, snapshot: ActivitySnapshot, evaluation: EvaluationResult) -> bool:
        """Take enforcement action - close the unproductive window/tab."""
        if not snapshot.active_window:
            return False
        
        window = snapshot.active_window
        action_type = "unknown"
        success = False
        
        try:
            if window.is_browser and snapshot.browser_tab:
                if self.config.enforcement.close_unproductive_tabs:
                    success = await self._close_browser_tab(window)
                    action_type = "close_tab"
            else:
                if self.config.enforcement.close_unproductive_apps:
                    success = await self._close_application(window)
                    action_type = "close_app"
            
            if self.config.enforcement.take_screenshots_for_review:
                await self._take_screenshot(snapshot, evaluation)
            
            self._log_enforcement({
                "type": action_type,
                "success": success,
                "timestamp": datetime.now().isoformat(),
                "window_title": window.title,
                "process": window.process_name,
                "reason": evaluation.reason,
                "classification": evaluation.classification.value
            })
            
            return success
            
        except Exception as e:
            print(f"Enforcement error: {e}")
            self._log_enforcement({
                "type": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            })
            return False
    
    async def _close_browser_tab(self, window: WindowInfo, snapshot: ActivitySnapshot = None) -> bool:
        """Close the current browser tab - prefer extension, fallback to keyboard."""
        ws_server = get_websocket_server()
        
        # Try to close via extension first (more reliable)
        if ws_server.is_connected():
            active_tab = ws_server.get_active_tab()
            if active_tab:
                success = await ws_server.close_tab(active_tab.id)
                if success:
                    print(f"[Enforcer] Closed tab via extension: {active_tab.url[:50]}")
                    return True
        
        # Fallback to keyboard shortcut
        if not HAS_WIN32:
            return False
        
        try:
            win32gui.SetForegroundWindow(window.hwnd)
            await asyncio.sleep(0.1)
            
            if HAS_PYAUTOGUI:
                pyautogui.hotkey('ctrl', 'w')
                await asyncio.sleep(0.2)
                return True
            else:
                import subprocess
                subprocess.run([
                    'powershell', '-Command',
                    '[System.Windows.Forms.SendKeys]::SendWait("^w")'
                ], capture_output=True)
                return True
                
        except Exception as e:
            print(f"Error closing browser tab: {e}")
            return False
    
    async def _close_application(self, window: WindowInfo) -> bool:
        """Close an application window."""
        if not HAS_WIN32:
            return False
        
        try:
            win32gui.PostMessage(window.hwnd, win32con.WM_CLOSE, 0, 0)
            await asyncio.sleep(0.5)
            
            if win32gui.IsWindow(window.hwnd):
                try:
                    process = psutil.Process(window.process_id)
                    process.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            return True
            
        except Exception as e:
            print(f"Error closing application: {e}")
            return False
    
    async def _kill_process(self, process_name: str) -> bool:
        """Kill all processes with the given name."""
        killed = False
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                if proc.info['name'].lower() == process_name.lower():
                    proc.terminate()
                    killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return killed
    
    async def _take_screenshot(self, snapshot: ActivitySnapshot, evaluation: EvaluationResult) -> None:
        """Take a screenshot for review."""
        try:
            if HAS_PYAUTOGUI:
                screenshot = pyautogui.screenshot()
                
                screenshots_dir = Path.home() / ".smart-productivity-enforcer" / "screenshots"
                screenshots_dir.mkdir(parents=True, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"enforcement_{timestamp}.png"
                screenshot.save(screenshots_dir / filename)
        except Exception as e:
            print(f"Screenshot error: {e}")
    
    def _log_enforcement(self, entry: dict) -> None:
        """Log enforcement action."""
        self.enforcement_log.append(entry)
        
        log_dir = Path.home() / ".smart-productivity-enforcer" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / f"enforcement_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    async def block_process_permanently(self, process_name: str) -> bool:
        """Block a process from running during focus session."""
        await self._kill_process(process_name)
        return True


class BypassProtection:
    """Prevents the user from easily disabling the enforcer."""
    
    def __init__(self, config: Config):
        self.config = config
        self.session_start: Optional[datetime] = None
        self.session_duration_minutes: int = 0
        self.is_locked: bool = False
    
    def start_session(self, duration_minutes: int) -> bool:
        """Start a protected focus session."""
        if self.is_locked:
            return False
        
        self.session_start = datetime.now()
        self.session_duration_minutes = duration_minutes
        self.is_locked = True
        
        self._save_session_state()
        
        return True
    
    def can_disable(self) -> tuple[bool, str]:
        """Check if the enforcer can be disabled."""
        if not self.is_locked:
            return True, "Not in a focus session"
        
        if not self.session_start:
            return True, "No active session"
        
        elapsed = (datetime.now() - self.session_start).total_seconds() / 60
        remaining = self.session_duration_minutes - elapsed
        
        if remaining <= 0:
            self.is_locked = False
            return True, "Session completed"
        
        if remaining < self.config.enforcement.min_session_duration_minutes:
            return False, f"Cannot disable. {remaining:.0f} minutes remaining in session."
        
        if self.config.enforcement.require_password_to_disable:
            return False, "Password required to disable during session"
        
        return False, f"Focus session active. {remaining:.0f} minutes remaining."
    
    def verify_password(self, password: str) -> bool:
        """Verify the disable password."""
        if not self.config.enforcement.password_hash:
            return True
        
        import hashlib
        hashed = hashlib.sha256(password.encode()).hexdigest()
        return hashed == self.config.enforcement.password_hash
    
    def force_disable(self, password: str) -> tuple[bool, str]:
        """Force disable with password."""
        if not self.verify_password(password):
            return False, "Incorrect password"
        
        self.is_locked = False
        self.session_start = None
        self._save_session_state()
        
        return True, "Session ended"
    
    def get_session_status(self) -> dict:
        """Get current session status."""
        if not self.is_locked or not self.session_start:
            return {
                "active": False,
                "remaining_minutes": 0
            }
        
        elapsed = (datetime.now() - self.session_start).total_seconds() / 60
        remaining = max(0, self.session_duration_minutes - elapsed)
        
        return {
            "active": True,
            "start_time": self.session_start.isoformat(),
            "duration_minutes": self.session_duration_minutes,
            "elapsed_minutes": elapsed,
            "remaining_minutes": remaining
        }
    
    def _save_session_state(self) -> None:
        """Save session state to file for persistence."""
        state_file = Path.home() / ".smart-productivity-enforcer" / "session_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        
        state = {
            "is_locked": self.is_locked,
            "session_start": self.session_start.isoformat() if self.session_start else None,
            "session_duration_minutes": self.session_duration_minutes
        }
        
        with open(state_file, "w") as f:
            json.dump(state, f)
    
    def _load_session_state(self) -> None:
        """Load session state from file."""
        state_file = Path.home() / ".smart-productivity-enforcer" / "session_state.json"
        
        if not state_file.exists():
            return
        
        try:
            with open(state_file, "r") as f:
                state = json.load(f)
            
            self.is_locked = state.get("is_locked", False)
            self.session_duration_minutes = state.get("session_duration_minutes", 0)
            
            if state.get("session_start"):
                self.session_start = datetime.fromisoformat(state["session_start"])
                
                elapsed = (datetime.now() - self.session_start).total_seconds() / 60
                if elapsed >= self.session_duration_minutes:
                    self.is_locked = False
                    self.session_start = None
        except Exception:
            pass

"""Activity Monitor - Detects and tracks user activity on Windows."""

import asyncio
import ctypes
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from pathlib import Path

import psutil

try:
    import win32gui
    import win32process
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

from smart_productivity_enforcer.config import Config, ProductivityLevel


@dataclass
class WindowInfo:
    """Information about an active window."""
    hwnd: int
    title: str
    process_name: str
    process_id: int
    class_name: str
    is_browser: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class BrowserTabInfo:
    """Information about a browser tab."""
    url: str
    title: str
    domain: str
    is_youtube: bool = False
    is_shorts: bool = False
    youtube_video_id: Optional[str] = None
    youtube_channel: Optional[str] = None
    content_summary: Optional[str] = None


@dataclass
class ActivitySnapshot:
    """A snapshot of the current user activity."""
    timestamp: datetime
    active_window: Optional[WindowInfo]
    browser_tab: Optional[BrowserTabInfo]
    running_processes: list[str]
    idle_time_seconds: float
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "active_window": {
                "title": self.active_window.title if self.active_window else None,
                "process": self.active_window.process_name if self.active_window else None,
            },
            "browser_tab": {
                "url": self.browser_tab.url if self.browser_tab else None,
                "title": self.browser_tab.title if self.browser_tab else None,
                "domain": self.browser_tab.domain if self.browser_tab else None,
            } if self.browser_tab else None,
            "idle_time": self.idle_time_seconds,
        }


class ActivityMonitor:
    """Monitors user activity on Windows."""
    
    BROWSER_PROCESSES = {
        "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
        "opera.exe", "vivaldi.exe", "chromium.exe"
    }
    
    def __init__(self, config: Config):
        self.config = config
        self.activity_log: list[ActivitySnapshot] = []
        self._browser_controller = None
        
    async def get_active_window(self) -> Optional[WindowInfo]:
        """Get information about the currently active window."""
        if not HAS_WIN32:
            return None
            
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
                
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            
            try:
                process = psutil.Process(pid)
                process_name = process.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                process_name = "Unknown"
            
            is_browser = process_name.lower() in self.BROWSER_PROCESSES
            
            return WindowInfo(
                hwnd=hwnd,
                title=title,
                process_name=process_name,
                process_id=pid,
                class_name=class_name,
                is_browser=is_browser
            )
        except Exception as e:
            print(f"Error getting active window: {e}")
            return None
    
    async def get_browser_tab_info(self, window_info: WindowInfo) -> Optional[BrowserTabInfo]:
        """Get information about the current browser tab using browser-use."""
        if not window_info.is_browser:
            return None
        
        title = window_info.title
        
        url = self._extract_url_from_title(title, window_info.process_name)
        domain = self._extract_domain(url) if url else ""
        
        is_youtube = "youtube.com" in domain or "youtu.be" in domain or "youtube" in title.lower()
        video_id = None
        channel = None
        is_shorts = False
        
        if is_youtube or "youtube" in title.lower():
            is_youtube = True
            video_id = self._extract_youtube_video_id(url)
            channel = self._extract_youtube_channel(title)
            # Detect Shorts from title (since URL isn't always available)
            is_shorts = "shorts" in title.lower() or "#shorts" in title.lower()
        
        return BrowserTabInfo(
            url=url or "",
            title=title,
            domain=domain,
            is_youtube=is_youtube,
            is_shorts=is_shorts,
            youtube_video_id=video_id,
            youtube_channel=channel
        )
    
    def _extract_url_from_title(self, title: str, process_name: str) -> Optional[str]:
        """Try to extract URL from browser window title."""
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        match = re.search(url_pattern, title)
        if match:
            return match.group(0)
        
        if " - " in title:
            parts = title.split(" - ")
            for part in parts:
                if "." in part and "/" not in part:
                    return f"https://{part.strip()}"
        
        return None
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        if not url:
            return ""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]
            return domain.lower().replace("www.", "")
        except Exception:
            return ""
    
    def _extract_youtube_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL."""
        if not url:
            return None
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
            r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def _extract_youtube_channel(self, title: str) -> Optional[str]:
        """Try to extract YouTube channel from title."""
        if " - YouTube" in title:
            parts = title.rsplit(" - ", 2)
            if len(parts) >= 2:
                return parts[-2].strip()
        return None
    
    def get_idle_time(self) -> float:
        """Get system idle time in seconds."""
        if not HAS_WIN32:
            return 0.0
            
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [
                ('cbSize', ctypes.c_uint),
                ('dwTime', ctypes.c_uint),
            ]
        
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return millis / 1000.0
        return 0.0
    
    def get_running_processes(self) -> list[str]:
        """Get list of running process names."""
        processes = set()
        for proc in psutil.process_iter(['name']):
            try:
                processes.add(proc.info['name'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return list(processes)
    
    async def take_snapshot(self) -> ActivitySnapshot:
        """Take a snapshot of current activity."""
        active_window = await self.get_active_window()
        browser_tab = None
        
        if active_window and active_window.is_browser:
            browser_tab = await self.get_browser_tab_info(active_window)
        
        snapshot = ActivitySnapshot(
            timestamp=datetime.now(),
            active_window=active_window,
            browser_tab=browser_tab,
            running_processes=self.get_running_processes(),
            idle_time_seconds=self.get_idle_time()
        )
        
        self.activity_log.append(snapshot)
        
        if len(self.activity_log) > 1000:
            self.activity_log = self.activity_log[-500:]
        
        return snapshot
    
    def log_activity(self, snapshot: ActivitySnapshot) -> None:
        """Log activity to file."""
        log_dir = Path.home() / ".smart-productivity-enforcer" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / f"activity_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        
        with open(log_file, "a") as f:
            f.write(json.dumps(snapshot.to_dict()) + "\n")

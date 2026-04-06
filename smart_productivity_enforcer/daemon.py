"""Main daemon service for the Smart Productivity Enforcer."""

import asyncio
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from smart_productivity_enforcer.config import Config, ProductivityLevel
from smart_productivity_enforcer.activity_monitor import ActivityMonitor, ActivitySnapshot, BrowserTabInfo
from smart_productivity_enforcer.llm_evaluator import ProductivityEvaluator, EvaluationResult
from smart_productivity_enforcer.enforcer import Enforcer, BypassProtection
from smart_productivity_enforcer.browser_controller import BrowserController
from smart_productivity_enforcer.websocket_server import get_websocket_server, ExtensionWebSocketServer
from smart_productivity_enforcer.activity_logger import get_activity_logger, ActivityLogger


console = Console()


class ProductivityDaemon:
    """Main daemon that runs the productivity enforcement loop."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.load()
        self.monitor = ActivityMonitor(self.config)
        self.evaluator = ProductivityEvaluator(self.config)
        self.enforcer = Enforcer(self.config)
        self.bypass_protection = BypassProtection(self.config)
        self.browser_controller = BrowserController(self.config)
        self.ws_server: ExtensionWebSocketServer = get_websocket_server()
        self.activity_logger: ActivityLogger = get_activity_logger(self.config)
        
        self._running = False
        self._paused = False
        self._last_snapshot: Optional[ActivitySnapshot] = None
        self._last_evaluation: Optional[EvaluationResult] = None
        self._stats = {
            "productive_time": 0,
            "unproductive_time": 0,
            "neutral_time": 0,
            "enforcement_actions": 0,
            "start_time": None,
        }
    
    async def start(self, duration_minutes: Optional[int] = None) -> None:
        """Start the productivity enforcement daemon."""
        self._running = True
        self._stats["start_time"] = datetime.now()
        
        if duration_minutes:
            self.bypass_protection.start_session(duration_minutes)
            console.print(f"[bold green]🔒 Focus session started for {duration_minutes} minutes[/bold green]")
        
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        # Start WebSocket server for Chrome extension
        try:
            await self.ws_server.start()
            console.print("[green]✓ Extension server started on ws://localhost:9876[/green]")
        except Exception as e:
            console.print(f"[yellow]Extension server failed: {e}[/yellow]")
        
        try:
            await self.browser_controller.connect_to_existing_browser()
        except Exception:
            if not self.ws_server.is_connected():
                console.print("[yellow]Install the Chrome extension for better tab detection.[/yellow]")
        
        console.print("[bold green]🚀 Smart Productivity Enforcer started![/bold green]")
        console.print(f"[dim]Goal: {self.config.user_goal}[/dim]")
        console.print(f"[dim]Check interval: {self.config.check_interval_seconds}s[/dim]")
        console.print("[dim]Press Ctrl+C to stop (if not in locked session)[/dim]\n")
        
        await self._run_loop()
    
    async def _run_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            if self._paused:
                await asyncio.sleep(1)
                continue
            
            try:
                snapshot = await self.monitor.take_snapshot()
                
                # Enhance snapshot with real URLs from Chrome extension
                if self.ws_server.is_connected():
                    active_tab = self.ws_server.get_active_tab()
                    if active_tab and snapshot.active_window and snapshot.active_window.is_browser:
                        # Override with real URL from extension
                        snapshot.browser_tab = BrowserTabInfo(
                            url=active_tab.url,
                            title=active_tab.title,
                            domain=self._extract_domain(active_tab.url),
                            is_youtube="youtube.com" in active_tab.url or "youtu.be" in active_tab.url,
                            is_shorts="/shorts/" in active_tab.url
                        )
                
                self._last_snapshot = snapshot
                
                # Log ALL activity for daily analysis
                if snapshot.active_window:
                    url = None
                    domain = None
                    if snapshot.browser_tab:
                        url = snapshot.browser_tab.url
                        domain = snapshot.browser_tab.domain
                    
                    self.activity_logger.log_activity(
                        window_title=snapshot.active_window.title,
                        process_name=snapshot.active_window.process_name,
                        url=url,
                        domain=domain,
                        duration_seconds=self.config.check_interval_seconds
                    )
                
                if self.config.enforcement.log_all_activity:
                    self.monitor.log_activity(snapshot)
                
                evaluation = await self.evaluator.evaluate(snapshot)
                self._last_evaluation = evaluation
                
                self._update_stats(evaluation)
                
                if self.config.enforcement.enabled:
                    action_taken = await self.enforcer.enforce(snapshot, evaluation)
                    if action_taken:
                        self._stats["enforcement_actions"] += 1
                
                self._print_status(snapshot, evaluation)
                
            except Exception as e:
                console.print(f"[red]Error in monitoring loop: {e}[/red]")
            
            await asyncio.sleep(self.config.check_interval_seconds)
    
    def _update_stats(self, evaluation: EvaluationResult) -> None:
        """Update productivity statistics."""
        interval = self.config.check_interval_seconds
        
        if evaluation.classification == ProductivityLevel.PRODUCTIVE:
            self._stats["productive_time"] += interval
        elif evaluation.classification == ProductivityLevel.UNPRODUCTIVE:
            self._stats["unproductive_time"] += interval
        else:
            self._stats["neutral_time"] += interval
    
    def _print_status(self, snapshot: ActivitySnapshot, evaluation: EvaluationResult) -> None:
        """Print current status."""
        status_color = {
            ProductivityLevel.PRODUCTIVE: "green",
            ProductivityLevel.NEUTRAL: "yellow",
            ProductivityLevel.UNPRODUCTIVE: "red",
            ProductivityLevel.BLOCKED: "red bold",
        }
        
        color = status_color.get(evaluation.classification, "white")
        window_title = snapshot.active_window.title[:50] if snapshot.active_window else "None"
        
        status_line = (
            f"[{color}]●[/{color}] "
            f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim] | "
            f"[{color}]{evaluation.classification.value.upper()}[/{color}] | "
            f"{window_title}..."
        )
        
        # Only show ACTION for UNPRODUCTIVE or BLOCKED - never for PRODUCTIVE/NEUTRAL
        if evaluation.should_close and evaluation.classification in [ProductivityLevel.UNPRODUCTIVE, ProductivityLevel.BLOCKED]:
            status_line += f" [red bold]⚠ CLOSING[/red bold]"
        
        console.print(status_line)
    
    def _handle_shutdown(self, signum, frame) -> None:
        """Handle shutdown signal."""
        can_disable, reason = self.bypass_protection.can_disable()
        
        if not can_disable:
            console.print(f"\n[red bold]Cannot stop: {reason}[/red bold]")
            console.print("[yellow]Complete your focus session or use password to force stop.[/yellow]")
            return
        
        console.print("\n[yellow]Shutting down...[/yellow]")
        self._running = False
        self._print_summary()
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc or ""
        except Exception:
            return ""
    
    async def close_tab_via_extension(self, tab_id: int) -> bool:
        """Close a browser tab via the Chrome extension."""
        if self.ws_server.is_connected():
            return await self.ws_server.close_tab(tab_id)
        return False
    
    async def close_tabs_by_url_pattern(self, pattern: str) -> bool:
        """Close all tabs matching a URL pattern via the extension."""
        if self.ws_server.is_connected():
            return await self.ws_server.close_tabs_by_url(pattern)
        return False
    
    def _print_summary(self) -> None:
        """Print session summary."""
        if not self._stats["start_time"]:
            return
        
        duration = (datetime.now() - self._stats["start_time"]).total_seconds()
        
        table = Table(title="📊 Session Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Total Duration", f"{duration/60:.1f} minutes")
        table.add_row("Productive Time", f"{self._stats['productive_time']/60:.1f} minutes")
        table.add_row("Unproductive Time", f"{self._stats['unproductive_time']/60:.1f} minutes")
        table.add_row("Neutral Time", f"{self._stats['neutral_time']/60:.1f} minutes")
        table.add_row("Enforcement Actions", str(self._stats['enforcement_actions']))
        
        if duration > 0:
            productivity_pct = (self._stats['productive_time'] / duration) * 100
            table.add_row("Productivity Score", f"{productivity_pct:.1f}%")
        
        console.print(table)
    
    def pause(self) -> None:
        """Pause monitoring."""
        self._paused = True
        console.print("[yellow]⏸ Monitoring paused[/yellow]")
    
    def resume(self) -> None:
        """Resume monitoring."""
        self._paused = False
        console.print("[green]▶ Monitoring resumed[/green]")
    
    def stop(self, password: Optional[str] = None) -> tuple[bool, str]:
        """Stop the daemon."""
        can_disable, reason = self.bypass_protection.can_disable()
        
        if not can_disable:
            if password:
                success, msg = self.bypass_protection.force_disable(password)
                if success:
                    self._running = False
                    self._print_summary()
                return success, msg
            return False, reason
        
        self._running = False
        self._print_summary()
        return True, "Stopped"
    
    def get_status(self) -> dict:
        """Get current daemon status."""
        session_status = self.bypass_protection.get_session_status()
        
        return {
            "running": self._running,
            "paused": self._paused,
            "session": session_status,
            "stats": self._stats,
            "last_activity": self._last_snapshot.to_dict() if self._last_snapshot else None,
            "last_evaluation": {
                "classification": self._last_evaluation.classification.value,
                "confidence": self._last_evaluation.confidence,
                "reason": self._last_evaluation.reason,
            } if self._last_evaluation else None,
        }


async def run_daemon(duration_minutes: Optional[int] = None) -> None:
    """Run the productivity daemon."""
    config = Config.load()
    daemon = ProductivityDaemon(config)
    await daemon.start(duration_minutes)


def main():
    """Entry point for the daemon."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Smart Productivity Enforcer Daemon")
    parser.add_argument(
        "--duration", "-d",
        type=int,
        help="Focus session duration in minutes"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict mode (harder to disable)"
    )
    
    args = parser.parse_args()
    
    if args.strict:
        config = Config.load()
        config.enforcement.bypass_protection_enabled = True
        config.enforcement.require_password_to_disable = True
        config.save()
    
    try:
        asyncio.run(run_daemon(args.duration))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")


if __name__ == "__main__":
    main()

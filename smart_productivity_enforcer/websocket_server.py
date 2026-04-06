"""WebSocket server for Chrome extension communication."""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, Dict, List, Any
import aiohttp
from aiohttp import web, WSMsgType


@dataclass
class BrowserTab:
    """Information about a browser tab from the extension."""
    id: int
    url: str
    title: str
    active: bool = False
    window_id: int = 0
    fav_icon_url: str = ""
    last_updated: datetime = field(default_factory=datetime.now)


class ExtensionWebSocketServer:
    """WebSocket server that communicates with the Chrome extension."""
    
    def __init__(self, host: str = "localhost", port: int = 9876):
        self.host = host
        self.port = port
        self.app = web.Application()
        self.app.router.add_get("/", self.websocket_handler)
        self.runner: Optional[web.AppRunner] = None
        self.clients: List[web.WebSocketResponse] = []
        self.tabs: Dict[int, BrowserTab] = {}
        self.on_tab_update: Optional[Callable[[Dict[int, BrowserTab]], None]] = None
        self.on_tab_activated: Optional[Callable[[BrowserTab], None]] = None
        self._running = False
    
    async def start(self):
        """Start the WebSocket server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        self._running = True
        print(f"[WebSocket] Server started on ws://{self.host}:{self.port}")
    
    async def stop(self):
        """Stop the WebSocket server."""
        self._running = False
        for client in self.clients:
            await client.close()
        self.clients.clear()
        if self.runner:
            await self.runner.cleanup()
        print("[WebSocket] Server stopped")
    
    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections from the extension."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.clients.append(ws)
        print(f"[WebSocket] Extension connected. Total clients: {len(self.clients)}")
        
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_message(data, ws)
                    except json.JSONDecodeError:
                        print(f"[WebSocket] Invalid JSON: {msg.data}")
                elif msg.type == WSMsgType.ERROR:
                    print(f"[WebSocket] Error: {ws.exception()}")
        finally:
            self.clients.remove(ws)
            print(f"[WebSocket] Extension disconnected. Total clients: {len(self.clients)}")
        
        return ws
    
    async def _handle_message(self, data: dict, ws: web.WebSocketResponse):
        """Handle incoming messages from the extension."""
        msg_type = data.get("type", "")
        
        if msg_type == "tabs_update":
            # Full tab list update
            tabs_data = data.get("tabs", [])
            self.tabs.clear()
            for tab_data in tabs_data:
                tab = BrowserTab(
                    id=tab_data.get("id", 0),
                    url=tab_data.get("url", ""),
                    title=tab_data.get("title", ""),
                    active=tab_data.get("active", False),
                    window_id=tab_data.get("windowId", 0),
                    fav_icon_url=tab_data.get("favIconUrl", "")
                )
                self.tabs[tab.id] = tab
            
            if self.on_tab_update:
                self.on_tab_update(self.tabs)
        
        elif msg_type == "tab_created":
            tab_data = data.get("tab", {})
            tab = BrowserTab(
                id=tab_data.get("id", 0),
                url=tab_data.get("url", ""),
                title=tab_data.get("title", ""),
                window_id=tab_data.get("windowId", 0)
            )
            self.tabs[tab.id] = tab
        
        elif msg_type == "tab_updated":
            tab_id = data.get("tabId")
            if tab_id in self.tabs:
                self.tabs[tab_id].url = data.get("url", self.tabs[tab_id].url)
                self.tabs[tab_id].title = data.get("title", self.tabs[tab_id].title)
                self.tabs[tab_id].last_updated = datetime.now()
        
        elif msg_type == "tab_removed":
            tab_id = data.get("tabId")
            if tab_id in self.tabs:
                del self.tabs[tab_id]
        
        elif msg_type == "tab_activated":
            tab_data = data.get("tab", {})
            tab_id = tab_data.get("id")
            
            # Update active status
            for tid, tab in self.tabs.items():
                tab.active = (tid == tab_id)
            
            if tab_id in self.tabs and self.on_tab_activated:
                self.on_tab_activated(self.tabs[tab_id])
        
        elif msg_type == "tab_closed":
            success = data.get("success", False)
            tab_id = data.get("tabId")
            if success:
                print(f"[WebSocket] Tab {tab_id} closed successfully")
            else:
                print(f"[WebSocket] Failed to close tab {tab_id}: {data.get('error')}")
        
        elif msg_type == "pong":
            pass  # Keep-alive response
    
    async def close_tab(self, tab_id: int) -> bool:
        """Send command to close a specific tab."""
        if not self.clients:
            print("[WebSocket] No extension connected")
            return False
        
        message = json.dumps({
            "type": "close_tab",
            "tabId": tab_id
        })
        
        for client in self.clients:
            try:
                await client.send_str(message)
                return True
            except Exception as e:
                print(f"[WebSocket] Failed to send close command: {e}")
        
        return False
    
    async def close_tabs_by_url(self, url_pattern: str) -> bool:
        """Send command to close all tabs matching a URL pattern."""
        if not self.clients:
            print("[WebSocket] No extension connected")
            return False
        
        message = json.dumps({
            "type": "close_tabs_by_url",
            "urlPattern": url_pattern
        })
        
        for client in self.clients:
            try:
                await client.send_str(message)
                return True
            except Exception as e:
                print(f"[WebSocket] Failed to send close command: {e}")
        
        return False
    
    async def request_tabs(self):
        """Request the extension to send all tabs."""
        if not self.clients:
            return
        
        message = json.dumps({"type": "get_tabs"})
        for client in self.clients:
            try:
                await client.send_str(message)
            except Exception:
                pass
    
    def get_active_tab(self) -> Optional[BrowserTab]:
        """Get the currently active browser tab."""
        for tab in self.tabs.values():
            if tab.active:
                return tab
        return None
    
    def get_tabs_by_domain(self, domain: str) -> List[BrowserTab]:
        """Get all tabs matching a domain."""
        return [tab for tab in self.tabs.values() if domain in tab.url]
    
    def is_connected(self) -> bool:
        """Check if any extension is connected."""
        return len(self.clients) > 0


# Singleton instance
_server_instance: Optional[ExtensionWebSocketServer] = None


def get_websocket_server() -> ExtensionWebSocketServer:
    """Get the singleton WebSocket server instance."""
    global _server_instance
    if _server_instance is None:
        _server_instance = ExtensionWebSocketServer()
    return _server_instance

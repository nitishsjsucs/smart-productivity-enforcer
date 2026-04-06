"""Browser controller for advanced tab management using browser-use."""

import asyncio
import re
from dataclasses import dataclass
from typing import Optional, List
from urllib.parse import urlparse

try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from smart_productivity_enforcer.config import Config


@dataclass
class TabInfo:
    """Information about a browser tab."""
    page_id: str
    url: str
    title: str
    domain: str
    is_youtube: bool
    content_preview: Optional[str] = None


class BrowserController:
    """Controls browser tabs for productivity enforcement."""
    
    def __init__(self, config: Config):
        self.config = config
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._connected = False
    
    async def connect_to_existing_browser(self, cdp_url: str = "http://localhost:9222") -> bool:
        """Connect to an existing browser instance via CDP."""
        if not HAS_PLAYWRIGHT:
            print("Playwright not installed. Run: pip install playwright && playwright install")
            return False
        
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
            
            contexts = self._browser.contexts
            if contexts:
                self._context = contexts[0]
            
            self._connected = True
            return True
            
        except Exception as e:
            print(f"Failed to connect to browser: {e}")
            print("Make sure your browser is running with remote debugging enabled:")
            print('  chrome.exe --remote-debugging-port=9222')
            return False
    
    async def get_all_tabs(self) -> List[TabInfo]:
        """Get information about all open tabs."""
        if not self._connected or not self._context:
            return []
        
        tabs = []
        for page in self._context.pages:
            try:
                url = page.url
                title = await page.title()
                domain = self._extract_domain(url)
                
                tabs.append(TabInfo(
                    page_id=str(id(page)),
                    url=url,
                    title=title,
                    domain=domain,
                    is_youtube="youtube.com" in domain or "youtu.be" in domain
                ))
            except Exception:
                continue
        
        return tabs
    
    async def get_active_tab(self) -> Optional[TabInfo]:
        """Get the currently active tab."""
        if not self._connected or not self._context:
            return None
        
        pages = self._context.pages
        if not pages:
            return None
        
        page = pages[-1]
        
        try:
            url = page.url
            title = await page.title()
            domain = self._extract_domain(url)
            
            content_preview = None
            try:
                content_preview = await page.evaluate('''
                    () => {
                        const main = document.querySelector('main') || document.body;
                        return main.innerText.substring(0, 500);
                    }
                ''')
            except Exception:
                pass
            
            return TabInfo(
                page_id=str(id(page)),
                url=url,
                title=title,
                domain=domain,
                is_youtube="youtube.com" in domain or "youtu.be" in domain,
                content_preview=content_preview
            )
        except Exception as e:
            print(f"Error getting active tab: {e}")
            return None
    
    async def close_tab_by_url(self, url_pattern: str) -> int:
        """Close all tabs matching the URL pattern. Returns count of closed tabs."""
        if not self._connected or not self._context:
            return 0
        
        closed = 0
        for page in list(self._context.pages):
            try:
                if re.search(url_pattern, page.url):
                    await page.close()
                    closed += 1
            except Exception:
                continue
        
        return closed
    
    async def close_tab_by_domain(self, domain: str) -> int:
        """Close all tabs from a specific domain."""
        if not self._connected or not self._context:
            return 0
        
        closed = 0
        for page in list(self._context.pages):
            try:
                page_domain = self._extract_domain(page.url)
                if domain.lower() in page_domain.lower():
                    await page.close()
                    closed += 1
            except Exception:
                continue
        
        return closed
    
    async def close_youtube_entertainment(self) -> int:
        """Close YouTube tabs that appear to be entertainment."""
        if not self._connected or not self._context:
            return 0
        
        youtube_config = self.config.youtube
        closed = 0
        
        for page in list(self._context.pages):
            try:
                url = page.url
                if "youtube.com" not in url and "youtu.be" not in url:
                    continue
                
                if "/shorts/" in url and youtube_config.block_shorts:
                    await page.close()
                    closed += 1
                    continue
                
                title = await page.title()
                title_lower = title.lower()
                
                is_productive = False
                for keyword in youtube_config.productive_keywords:
                    if keyword.lower() in title_lower:
                        is_productive = True
                        break
                
                for channel in youtube_config.productive_channels:
                    if channel.lower() in title_lower:
                        is_productive = True
                        break
                
                if not is_productive:
                    for keyword in youtube_config.unproductive_keywords:
                        if keyword.lower() in title_lower:
                            await page.close()
                            closed += 1
                            break
                
            except Exception:
                continue
        
        return closed
    
    async def inject_productivity_overlay(self, page: Page, message: str) -> None:
        """Inject a productivity warning overlay into a page."""
        try:
            await page.evaluate(f'''
                () => {{
                    if (document.getElementById('spe-overlay')) return;
                    
                    const overlay = document.createElement('div');
                    overlay.id = 'spe-overlay';
                    overlay.innerHTML = `
                        <div style="
                            position: fixed;
                            top: 0;
                            left: 0;
                            width: 100%;
                            height: 100%;
                            background: rgba(0, 0, 0, 0.9);
                            z-index: 999999;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            flex-direction: column;
                            color: white;
                            font-family: Arial, sans-serif;
                        ">
                            <h1 style="font-size: 48px; margin-bottom: 20px;">⚠️ Focus Mode Active</h1>
                            <p style="font-size: 24px; max-width: 600px; text-align: center;">
                                {message}
                            </p>
                            <p style="font-size: 18px; margin-top: 30px; color: #ff6b6b;">
                                This tab will be closed in 5 seconds...
                            </p>
                        </div>
                    `;
                    document.body.appendChild(overlay);
                }}
            ''')
        except Exception as e:
            print(f"Failed to inject overlay: {e}")
    
    async def get_youtube_video_info(self, page: Page) -> dict:
        """Extract detailed info from a YouTube video page."""
        try:
            info = await page.evaluate('''
                () => {
                    const title = document.querySelector('h1.ytd-video-primary-info-renderer')?.textContent || 
                                  document.querySelector('h1.ytd-watch-metadata')?.textContent || '';
                    const channel = document.querySelector('#channel-name a')?.textContent || 
                                    document.querySelector('ytd-channel-name a')?.textContent || '';
                    const description = document.querySelector('#description')?.textContent?.substring(0, 500) || '';
                    const views = document.querySelector('.view-count')?.textContent || '';
                    
                    return { title, channel, description, views };
                }
            ''')
            return info
        except Exception:
            return {}
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]
            return domain.lower().replace("www.", "")
        except Exception:
            return ""
    
    async def disconnect(self) -> None:
        """Disconnect from browser."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._connected = False


class BrowserLauncher:
    """Launches browsers with debugging enabled for control."""
    
    CHROME_PATHS = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    ]
    
    EDGE_PATHS = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    
    @classmethod
    async def launch_chrome_with_debugging(cls, port: int = 9222, user_data_dir: Optional[str] = None) -> bool:
        """Launch Chrome with remote debugging enabled."""
        import subprocess
        import os
        
        chrome_path = None
        for path in cls.CHROME_PATHS:
            expanded = os.path.expandvars(path)
            if os.path.exists(expanded):
                chrome_path = expanded
                break
        
        if not chrome_path:
            print("Chrome not found")
            return False
        
        args = [
            chrome_path,
            f"--remote-debugging-port={port}",
        ]
        
        if user_data_dir:
            args.append(f"--user-data-dir={user_data_dir}")
        
        try:
            subprocess.Popen(args, start_new_session=True)
            await asyncio.sleep(2)
            return True
        except Exception as e:
            print(f"Failed to launch Chrome: {e}")
            return False
    
    @classmethod
    async def launch_edge_with_debugging(cls, port: int = 9222) -> bool:
        """Launch Edge with remote debugging enabled."""
        import subprocess
        import os
        
        edge_path = None
        for path in cls.EDGE_PATHS:
            if os.path.exists(path):
                edge_path = path
                break
        
        if not edge_path:
            print("Edge not found")
            return False
        
        args = [
            edge_path,
            f"--remote-debugging-port={port}",
        ]
        
        try:
            subprocess.Popen(args, start_new_session=True)
            await asyncio.sleep(2)
            return True
        except Exception as e:
            print(f"Failed to launch Edge: {e}")
            return False

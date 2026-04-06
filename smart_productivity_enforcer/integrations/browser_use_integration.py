"""Integration with browser-use for advanced browser automation."""

import asyncio
import sys
from pathlib import Path
from typing import Optional, Any, List
from dataclasses import dataclass

BROWSER_USE_PATH = Path(__file__).parent.parent.parent.parent / "browser-use"
if str(BROWSER_USE_PATH) not in sys.path:
    sys.path.insert(0, str(BROWSER_USE_PATH))

try:
    from browser_use import Agent, Browser
    HAS_BROWSER_USE = True
except ImportError:
    HAS_BROWSER_USE = False
    Agent = None
    Browser = None


@dataclass
class PageAnalysis:
    """Analysis of a web page's content."""
    url: str
    title: str
    main_topic: str
    is_educational: bool
    is_entertainment: bool
    productivity_score: float
    summary: str


class BrowserUseIntegration:
    """Integration with browser-use for advanced browser control."""
    
    def __init__(self):
        self.agent: Optional[Any] = None
        self.browser: Optional[Any] = None
        self._initialized = False
    
    def is_available(self) -> bool:
        """Check if browser-use is available."""
        return HAS_BROWSER_USE
    
    async def initialize(self, llm_config: dict) -> bool:
        """Initialize the browser-use agent."""
        if not HAS_BROWSER_USE:
            return False
        
        try:
            import os
            
            self.browser = Browser()
            
            self._initialized = True
            return True
            
        except Exception as e:
            print(f"Failed to initialize browser-use: {e}")
            return False
    
    async def analyze_current_page(self) -> Optional[PageAnalysis]:
        """Analyze the current browser page for productivity."""
        if not self._initialized:
            return None
        
        try:
            return None
        except Exception as e:
            print(f"Error analyzing page: {e}")
            return None
    
    async def close_tab_by_content(self, content_pattern: str) -> bool:
        """Close tabs containing specific content."""
        if not self._initialized:
            return False
        
        try:
            return False
        except Exception:
            return False
    
    async def get_youtube_video_details(self, video_url: str) -> Optional[dict]:
        """Get detailed information about a YouTube video."""
        if not self._initialized:
            return None
        
        try:
            return None
        except Exception:
            return None
    
    async def execute_browser_action(self, action: str) -> Optional[str]:
        """Execute a browser action using the agent."""
        if not self._initialized or not self.agent:
            return None
        
        try:
            history = await self.agent.run()
            return str(history)
        except Exception as e:
            return f"Error: {e}"
    
    async def cleanup(self) -> None:
        """Clean up browser resources."""
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass


class SmartYouTubeAnalyzer:
    """Analyze YouTube content for productivity classification."""
    
    EDUCATIONAL_INDICATORS = [
        "tutorial", "course", "learn", "how to", "explained",
        "programming", "coding", "development", "engineering",
        "lecture", "lesson", "education", "training",
        "documentation", "deep dive", "tech talk", "conference"
    ]
    
    ENTERTAINMENT_INDICATORS = [
        "funny", "compilation", "reaction", "prank", "challenge",
        "vlog", "drama", "gossip", "celebrity", "unboxing",
        "haul", "mukbang", "asmr", "shorts", "tiktok",
        "meme", "fail", "try not to laugh"
    ]
    
    EDUCATIONAL_CHANNELS = [
        "fireship", "theprimeagen", "traversymedia", "freecodecamp",
        "computerphile", "3blue1brown", "twominutepapers",
        "mitopencourseware", "stanfordonline", "crashcourse",
        "arjancodes", "techwithth", "webdevimplified", "techwithtim",
        "sentdex", "corey schafer", "networkchuck"
    ]
    
    @classmethod
    def analyze_title(cls, title: str) -> dict:
        """Analyze a video title for productivity indicators."""
        title_lower = title.lower()
        
        educational_score = 0
        entertainment_score = 0
        
        for indicator in cls.EDUCATIONAL_INDICATORS:
            if indicator in title_lower:
                educational_score += 1
        
        for indicator in cls.ENTERTAINMENT_INDICATORS:
            if indicator in title_lower:
                entertainment_score += 1
        
        is_educational = educational_score > entertainment_score
        is_entertainment = entertainment_score > educational_score
        
        if educational_score == 0 and entertainment_score == 0:
            classification = "unknown"
            confidence = 0.3
        elif is_educational:
            classification = "educational"
            confidence = min(0.9, 0.5 + (educational_score * 0.1))
        else:
            classification = "entertainment"
            confidence = min(0.9, 0.5 + (entertainment_score * 0.1))
        
        return {
            "classification": classification,
            "confidence": confidence,
            "educational_score": educational_score,
            "entertainment_score": entertainment_score,
            "is_educational": is_educational,
            "is_entertainment": is_entertainment
        }
    
    @classmethod
    def is_educational_channel(cls, channel_name: str) -> bool:
        """Check if a channel is known to be educational."""
        channel_lower = channel_name.lower()
        for edu_channel in cls.EDUCATIONAL_CHANNELS:
            if edu_channel in channel_lower:
                return True
        return False
    
    @classmethod
    def analyze_url(cls, url: str) -> dict:
        """Analyze a YouTube URL for productivity indicators."""
        url_lower = url.lower()
        
        if "/shorts/" in url_lower:
            return {
                "classification": "entertainment",
                "confidence": 0.95,
                "reason": "YouTube Shorts are typically entertainment"
            }
        
        if url_lower.rstrip("/") in ["https://youtube.com", "https://www.youtube.com"]:
            return {
                "classification": "browsing",
                "confidence": 0.8,
                "reason": "YouTube homepage browsing"
            }
        
        if "/results?" in url_lower:
            return {
                "classification": "searching",
                "confidence": 0.5,
                "reason": "YouTube search - depends on query"
            }
        
        if "/watch?" in url_lower:
            return {
                "classification": "video",
                "confidence": 0.5,
                "reason": "Watching a video - needs title analysis"
            }
        
        return {
            "classification": "unknown",
            "confidence": 0.3,
            "reason": "Unknown YouTube page type"
        }

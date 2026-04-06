"""Configuration for the Smart Productivity Enforcer."""

import os
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class ProductivityLevel(str, Enum):
    """Productivity classification levels."""
    PRODUCTIVE = "productive"
    NEUTRAL = "neutral"
    UNPRODUCTIVE = "unproductive"
    BLOCKED = "blocked"


class AppRule(BaseModel):
    """Rule for a specific application."""
    name: str
    process_name: Optional[str] = None
    window_title_contains: Optional[list[str]] = None
    default_classification: ProductivityLevel = ProductivityLevel.NEUTRAL
    always_allow: bool = False
    always_block: bool = False


class BrowserRule(BaseModel):
    """Rule for browser tab evaluation."""
    domain: str
    default_classification: ProductivityLevel = ProductivityLevel.NEUTRAL
    use_llm_evaluation: bool = True
    productive_keywords: list[str] = Field(default_factory=list)
    unproductive_keywords: list[str] = Field(default_factory=list)
    always_allow: bool = False
    always_block: bool = False


class YouTubeRule(BaseModel):
    """Special rules for YouTube - the biggest time sink."""
    enabled: bool = True
    use_llm_evaluation: bool = True
    productive_channels: list[str] = Field(default_factory=lambda: [
        "Fireship", "ThePrimeagen", "ArjanCodes", "TechWithTim",
        "Computerphile", "3Blue1Brown", "Two Minute Papers",
        "MIT OpenCourseWare", "freeCodeCamp.org", "Traversy Media"
    ])
    productive_keywords: list[str] = Field(default_factory=lambda: [
        "tutorial", "course", "programming", "coding", "software",
        "engineering", "machine learning", "AI", "development",
        "algorithm", "data structure", "system design", "tech talk",
        "conference", "lecture", "education", "learn", "how to code"
    ])
    unproductive_keywords: list[str] = Field(default_factory=lambda: [
        "funny", "prank", "reaction", "drama", "gossip", "celebrity",
        "shorts", "tiktok compilation", "meme", "fail compilation",
        "entertainment", "vlog", "unboxing", "haul"
    ])
    block_shorts: bool = True
    block_homepage_suggestions: bool = True
    max_daily_entertainment_minutes: int = 30


class FocusSession(BaseModel):
    """Configuration for a focus session."""
    name: str
    duration_minutes: int = 60
    strict_mode: bool = True
    allowed_apps: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    break_duration_minutes: int = 10
    auto_extend: bool = False


class EnforcementConfig(BaseModel):
    """Configuration for how enforcement actions are taken."""
    enabled: bool = True
    warning_before_close: bool = True
    warning_duration_seconds: int = 5
    close_unproductive_tabs: bool = True
    close_unproductive_apps: bool = True
    take_screenshots_for_review: bool = True
    log_all_activity: bool = True
    bypass_protection_enabled: bool = True
    require_password_to_disable: bool = True
    password_hash: Optional[str] = None
    min_session_duration_minutes: int = 15


class LLMConfig(BaseModel):
    """Configuration for the LLM evaluator."""
    provider: str = "ollama"  # ollama (free), google, openai, anthropic
    model: str = "qwen3:1.7b"  # Fast 1.4GB local model - free
    temperature: float = 0.3
    max_tokens: int = 500
    evaluation_prompt_template: str = """You are a productivity evaluator. Analyze the following activity and determine if it's productive or not.

Context:
- User's stated goal: {user_goal}
- Current application: {app_name}
- Window title: {window_title}
- URL (if browser): {url}
- Page title (if browser): {page_title}
- Page content summary: {content_summary}

Productive activities include:
- Work-related tasks
- Learning and education (tutorials, courses, documentation)
- Software development
- Research for work/study
- Professional communication

Unproductive activities include:
- Entertainment videos (unless during designated break)
- Social media scrolling
- Gaming (unless designated)
- News/gossip sites
- Shopping (unless work-related)

Respond with a JSON object:
{{
    "classification": "productive" | "neutral" | "unproductive",
    "confidence": 0.0-1.0,
    "reason": "brief explanation",
    "should_close": true | false
}}"""


class Config(BaseModel):
    """Main configuration for the Smart Productivity Enforcer."""
    user_goal: str = "Focus on software development and learning"
    check_interval_seconds: int = 10
    llm: LLMConfig = Field(default_factory=LLMConfig)
    enforcement: EnforcementConfig = Field(default_factory=EnforcementConfig)
    youtube: YouTubeRule = Field(default_factory=YouTubeRule)
    app_rules: list[AppRule] = Field(default_factory=lambda: [
        AppRule(
            name="Visual Studio Code",
            process_name="Code.exe",
            default_classification=ProductivityLevel.PRODUCTIVE,
            always_allow=True
        ),
        AppRule(
            name="Windsurf",
            process_name="Windsurf.exe",
            default_classification=ProductivityLevel.PRODUCTIVE,
            always_allow=True
        ),
        AppRule(
            name="PyCharm",
            process_name="pycharm64.exe",
            default_classification=ProductivityLevel.PRODUCTIVE,
            always_allow=True
        ),
        AppRule(
            name="Terminal",
            process_name="WindowsTerminal.exe",
            default_classification=ProductivityLevel.PRODUCTIVE,
            always_allow=True
        ),
        AppRule(
            name="Notepad++",
            process_name="notepad++.exe",
            default_classification=ProductivityLevel.PRODUCTIVE,
            always_allow=True
        ),
        AppRule(
            name="Spotify",
            process_name="Spotify.exe",
            default_classification=ProductivityLevel.NEUTRAL,
            always_allow=True
        ),
        AppRule(
            name="Discord",
            process_name="Discord.exe",
            default_classification=ProductivityLevel.UNPRODUCTIVE,
            always_block=False
        ),
        AppRule(
            name="Steam",
            process_name="steam.exe",
            default_classification=ProductivityLevel.UNPRODUCTIVE,
            always_block=True
        ),
        AppRule(
            name="Games",
            window_title_contains=["game", "minecraft", "valorant", "fortnite"],
            default_classification=ProductivityLevel.BLOCKED,
            always_block=True
        ),
    ])
    browser_rules: list[BrowserRule] = Field(default_factory=lambda: [
        BrowserRule(
            domain="github.com",
            default_classification=ProductivityLevel.PRODUCTIVE,
            always_allow=True
        ),
        BrowserRule(
            domain="stackoverflow.com",
            default_classification=ProductivityLevel.PRODUCTIVE,
            always_allow=True
        ),
        BrowserRule(
            domain="docs.python.org",
            default_classification=ProductivityLevel.PRODUCTIVE,
            always_allow=True
        ),
        BrowserRule(
            domain="reddit.com",
            default_classification=ProductivityLevel.UNPRODUCTIVE,
            use_llm_evaluation=True,
            productive_keywords=["programming", "python", "javascript", "learnprogramming"],
            unproductive_keywords=["funny", "memes", "gaming", "videos"]
        ),
        BrowserRule(
            domain="twitter.com",
            default_classification=ProductivityLevel.UNPRODUCTIVE,
            use_llm_evaluation=False
        ),
        BrowserRule(
            domain="x.com",
            default_classification=ProductivityLevel.UNPRODUCTIVE,
            use_llm_evaluation=False
        ),
        BrowserRule(
            domain="facebook.com",
            default_classification=ProductivityLevel.UNPRODUCTIVE,
            always_block=True
        ),
        BrowserRule(
            domain="instagram.com",
            default_classification=ProductivityLevel.UNPRODUCTIVE,
            always_block=True
        ),
        BrowserRule(
            domain="tiktok.com",
            default_classification=ProductivityLevel.BLOCKED,
            always_block=True
        ),
        BrowserRule(
            domain="netflix.com",
            default_classification=ProductivityLevel.BLOCKED,
            always_block=True
        ),
        BrowserRule(
            domain="primevideo.com",
            default_classification=ProductivityLevel.BLOCKED,
            always_block=True
        ),
        BrowserRule(
            domain="disneyplus.com",
            default_classification=ProductivityLevel.BLOCKED,
            always_block=True
        ),
        BrowserRule(
            domain="hulu.com",
            default_classification=ProductivityLevel.BLOCKED,
            always_block=True
        ),
        BrowserRule(
            domain="twitch.tv",
            default_classification=ProductivityLevel.UNPRODUCTIVE,
            always_block=True
        ),
    ])
    focus_sessions: list[FocusSession] = Field(default_factory=lambda: [
        FocusSession(
            name="Deep Work",
            duration_minutes=2,
            strict_mode=True,
            allowed_apps=["Code.exe", "Windsurf.exe", "WindowsTerminal.exe", "pycharm64.exe"],
            allowed_domains=["github.com", "stackoverflow.com", "docs.python.org"]
        ),
        FocusSession(
            name="Learning",
            duration_minutes=60,
            strict_mode=False,
            allowed_apps=["Code.exe", "chrome.exe", "msedge.exe"],
            allowed_domains=["youtube.com", "udemy.com", "coursera.org", "github.com"]
        ),
    ])
    
    @classmethod
    def get_config_path(cls) -> Path:
        """Get the configuration file path."""
        config_dir = Path.home() / ".smart-productivity-enforcer"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "config.json"
    
    @classmethod
    def load(cls) -> "Config":
        """Load configuration from file or create default."""
        config_path = cls.get_config_path()
        if config_path.exists():
            with open(config_path, "r") as f:
                data = json.load(f)
                return cls(**data)
        return cls()
    
    def save(self) -> None:
        """Save configuration to file."""
        config_path = self.get_config_path()
        with open(config_path, "w") as f:
            json.dump(self.model_dump(), f, indent=2)

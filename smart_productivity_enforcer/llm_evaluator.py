"""LLM-based productivity evaluator with Ollama support and smart caching."""

import json
import os
import requests
from dataclasses import dataclass
from typing import Optional, Dict
from datetime import datetime, timedelta

from smart_productivity_enforcer.config import Config, ProductivityLevel, YouTubeRule
from smart_productivity_enforcer.activity_monitor import ActivitySnapshot, BrowserTabInfo


@dataclass
class EvaluationResult:
    """Result of productivity evaluation."""
    classification: ProductivityLevel
    confidence: float
    reason: str
    should_close: bool
    used_llm: bool = False


@dataclass  
class CachedEvaluation:
    """Cached evaluation result with timestamp."""
    result: EvaluationResult
    timestamp: datetime
    key: str


class ProductivityEvaluator:
    """Evaluates user activity for productivity using rules and LLM with smart caching."""
    
    def __init__(self, config: Config):
        self.config = config
        self._llm_client = None
        self._llm_provider = None
        # Cache: key -> CachedEvaluation (only call LLM once per unique URL/app)
        self._evaluation_cache: Dict[str, CachedEvaluation] = {}
        self._cache_ttl_hours = 24  # Cache results for 24 hours
        self._last_activity_key: Optional[str] = None  # Track last activity to detect changes
        self._init_llm()
    
    def _init_llm(self) -> None:
        """Initialize the LLM client based on config."""
        provider = self.config.llm.provider.lower()
        self._llm_provider = provider
        
        if provider == "ollama":
            # Ollama - free local inference with glm-4.7:cloud
            try:
                response = requests.get("http://localhost:11434/api/tags", timeout=2)
                if response.status_code == 200:
                    self._llm_client = "ollama"
                    print(f"[LLM] ✓ Using Ollama with model: {self.config.llm.model}")
                else:
                    print("[LLM] Ollama not responding")
            except Exception as e:
                print(f"[LLM] Ollama not available: {e}")
        
        elif provider == "google":
            try:
                import google.generativeai as genai
                api_key = os.getenv("GOOGLE_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
                    self._llm_client = genai.GenerativeModel(self.config.llm.model)
            except ImportError:
                print("google-generativeai not installed")
                
        elif provider == "openai":
            try:
                from openai import OpenAI
                api_key = os.getenv("OPENAI_API_KEY")
                if api_key:
                    self._llm_client = OpenAI(api_key=api_key)
            except ImportError:
                print("openai not installed")
                
        elif provider == "anthropic":
            try:
                from anthropic import Anthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if api_key:
                    self._llm_client = Anthropic(api_key=api_key)
            except ImportError:
                print("anthropic not installed")
    
    def _get_cache_key(self, snapshot: ActivitySnapshot) -> str:
        """Generate a unique cache key for the current activity."""
        if snapshot.browser_tab and snapshot.browser_tab.url:
            # For browser tabs, use URL (without query params for stability)
            url = snapshot.browser_tab.url.split('?')[0]
            return f"url:{url}"
        elif snapshot.active_window:
            # For apps, use process name only (title changes too often)
            return f"app:{snapshot.active_window.process_name.lower()}"
        return ""
    
    def is_activity_changed(self, snapshot: ActivitySnapshot) -> bool:
        """Check if activity changed from last check (for optimizing LLM calls)."""
        current_key = self._get_cache_key(snapshot)
        changed = current_key != self._last_activity_key
        self._last_activity_key = current_key
        return changed
    
    def _get_cached_result(self, key: str) -> Optional[EvaluationResult]:
        """Get cached evaluation result if valid."""
        if not key or key not in self._evaluation_cache:
            return None
        
        cached = self._evaluation_cache[key]
        age = datetime.now() - cached.timestamp
        
        if age < timedelta(hours=self._cache_ttl_hours):
            return cached.result
        
        # Cache expired, remove it
        del self._evaluation_cache[key]
        return None
    
    def _cache_result(self, key: str, result: EvaluationResult) -> None:
        """Cache an evaluation result."""
        if key:
            self._evaluation_cache[key] = CachedEvaluation(
                result=result,
                timestamp=datetime.now(),
                key=key
            )
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        return {
            "cached_items": len(self._evaluation_cache),
            "cache_keys": list(self._evaluation_cache.keys())[:10]
        }
    
    async def evaluate(self, snapshot: ActivitySnapshot) -> EvaluationResult:
        """Evaluate the productivity of a given activity snapshot with smart caching."""
        if not snapshot.active_window:
            return EvaluationResult(
                classification=ProductivityLevel.NEUTRAL,
                confidence=1.0,
                reason="No active window detected",
                should_close=False
            )
        
        if snapshot.idle_time_seconds > 300:
            return EvaluationResult(
                classification=ProductivityLevel.NEUTRAL,
                confidence=1.0,
                reason="User is idle",
                should_close=False
            )
        
        # Generate cache key for this activity
        cache_key = self._get_cache_key(snapshot)
        
        # Check YouTube FIRST before other rules (it's the biggest time sink)
        if snapshot.browser_tab and snapshot.browser_tab.is_youtube:
            youtube_result = self._evaluate_youtube(snapshot.browser_tab)
            if youtube_result:
                return youtube_result
        
        # Also check window title for YouTube even without browser_tab
        if snapshot.active_window and "youtube" in snapshot.active_window.title.lower():
            from smart_productivity_enforcer.activity_monitor import BrowserTabInfo
            fake_tab = BrowserTabInfo(
                url="",
                title=snapshot.active_window.title,
                domain="youtube.com",
                is_youtube=True,
                is_shorts="shorts" in snapshot.active_window.title.lower()
            )
            youtube_result = self._evaluate_youtube(fake_tab)
            if youtube_result:
                return youtube_result
        
        # Check rules first (fast, no LLM needed)
        rule_result = self._evaluate_by_rules(snapshot)
        if rule_result:
            return rule_result
        
        # Check cache - avoid LLM call if we've seen this before
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            # Return cached result with note
            return EvaluationResult(
                classification=cached_result.classification,
                confidence=cached_result.confidence,
                reason=f"[cached] {cached_result.reason}",
                should_close=cached_result.should_close,
                used_llm=False
            )
        
        # Only call LLM for NEW, uncached, ambiguous content
        if self._should_use_llm(snapshot):
            llm_result = await self._evaluate_with_llm(snapshot)
            if llm_result:
                # Cache the LLM result for future use
                self._cache_result(cache_key, llm_result)
                return llm_result
        
        return EvaluationResult(
            classification=ProductivityLevel.NEUTRAL,
            confidence=0.5,
            reason="Could not determine productivity level",
            should_close=False
        )
    
    def _evaluate_by_rules(self, snapshot: ActivitySnapshot) -> Optional[EvaluationResult]:
        """Evaluate using predefined rules."""
        window = snapshot.active_window
        if not window:
            return None
        
        process_name = window.process_name.lower()
        title_lower = window.title.lower()
        
        # Check for blocked sites in window title (even without browser extension)
        blocked_sites = ["netflix", "primevideo", "disneyplus", "hulu", "twitch", "tiktok"]
        for site in blocked_sites:
            if site in title_lower:
                return EvaluationResult(
                    classification=ProductivityLevel.BLOCKED,
                    confidence=1.0,
                    reason=f"{site} is blocked",
                    should_close=True
                )
        
        for rule in self.config.app_rules:
            if rule.process_name and rule.process_name.lower() == process_name:
                if rule.always_allow:
                    return EvaluationResult(
                        classification=ProductivityLevel.PRODUCTIVE,
                        confidence=1.0,
                        reason=f"{rule.name} is always allowed",
                        should_close=False
                    )
                if rule.always_block:
                    return EvaluationResult(
                        classification=ProductivityLevel.BLOCKED,
                        confidence=1.0,
                        reason=f"{rule.name} is blocked during focus time",
                        should_close=True
                    )
            
            if rule.window_title_contains:
                for keyword in rule.window_title_contains:
                    if keyword.lower() in title_lower:
                        if rule.always_block:
                            return EvaluationResult(
                                classification=ProductivityLevel.BLOCKED,
                                confidence=1.0,
                                reason=f"Window contains blocked keyword: {keyword}",
                                should_close=True
                            )
                        return EvaluationResult(
                            classification=rule.default_classification,
                            confidence=0.8,
                            reason=f"Matched rule: {rule.name}",
                            should_close=rule.default_classification == ProductivityLevel.BLOCKED
                        )
        
        if snapshot.browser_tab:
            tab = snapshot.browser_tab
            for rule in self.config.browser_rules:
                if rule.domain in tab.domain:
                    if rule.always_allow:
                        return EvaluationResult(
                            classification=ProductivityLevel.PRODUCTIVE,
                            confidence=1.0,
                            reason=f"{rule.domain} is always allowed",
                            should_close=False
                        )
                    if rule.always_block:
                        return EvaluationResult(
                            classification=ProductivityLevel.BLOCKED,
                            confidence=1.0,
                            reason=f"{rule.domain} is blocked",
                            should_close=True
                        )
                    
                    for keyword in rule.productive_keywords:
                        if keyword.lower() in tab.title.lower() or keyword.lower() in tab.url.lower():
                            return EvaluationResult(
                                classification=ProductivityLevel.PRODUCTIVE,
                                confidence=0.8,
                                reason=f"Contains productive keyword: {keyword}",
                                should_close=False
                            )
                    
                    for keyword in rule.unproductive_keywords:
                        if keyword.lower() in tab.title.lower():
                            return EvaluationResult(
                                classification=ProductivityLevel.UNPRODUCTIVE,
                                confidence=0.8,
                                reason=f"Contains unproductive keyword: {keyword}",
                                should_close=True
                            )
        
        return None
    
    def _evaluate_youtube(self, tab: BrowserTabInfo) -> Optional[EvaluationResult]:
        """Special evaluation for YouTube content."""
        youtube_config = self.config.youtube
        
        if not youtube_config.enabled:
            return None
        
        # Block Shorts - check both URL and title-based detection
        if youtube_config.block_shorts and (tab.is_shorts or "/shorts/" in tab.url or "shorts" in tab.title.lower()):
            return EvaluationResult(
                classification=ProductivityLevel.BLOCKED,
                confidence=1.0,
                reason="YouTube Shorts are blocked",
                should_close=True
            )
        
        if youtube_config.block_homepage_suggestions:
            if tab.url.rstrip('/') in ["https://youtube.com", "https://www.youtube.com"]:
                return EvaluationResult(
                    classification=ProductivityLevel.UNPRODUCTIVE,
                    confidence=0.9,
                    reason="YouTube homepage browsing is discouraged",
                    should_close=True
                )
        
        if tab.youtube_channel:
            for channel in youtube_config.productive_channels:
                if channel.lower() in tab.youtube_channel.lower():
                    return EvaluationResult(
                        classification=ProductivityLevel.PRODUCTIVE,
                        confidence=0.95,
                        reason=f"Watching educational channel: {channel}",
                        should_close=False
                    )
        
        title_lower = tab.title.lower()
        
        for keyword in youtube_config.productive_keywords:
            if keyword.lower() in title_lower:
                return EvaluationResult(
                    classification=ProductivityLevel.PRODUCTIVE,
                    confidence=0.8,
                    reason=f"Video appears educational (keyword: {keyword})",
                    should_close=False
                )
        
        for keyword in youtube_config.unproductive_keywords:
            if keyword.lower() in title_lower:
                return EvaluationResult(
                    classification=ProductivityLevel.UNPRODUCTIVE,
                    confidence=0.85,
                    reason=f"Video appears to be entertainment (keyword: {keyword})",
                    should_close=True
                )
        
        # For ambiguous YouTube content, use LLM to make smart decision
        # Check if title suggests educational content
        educational_signals = [
            'tutorial', 'learn', 'course', 'lecture', 'explained', 'how to',
            'introduction', 'guide', 'basics', 'advanced', 'programming',
            'coding', 'developer', 'engineer', 'software', 'backend', 'frontend',
            'database', 'api', 'http', 'algorithm', 'data structure', 'system design',
            'interview', 'career', 'tech', 'computer science', 'machine learning',
            'ai', 'python', 'javascript', 'java', 'react', 'node', 'aws', 'docker',
            'kubernetes', 'devops', 'git', 'linux', 'web development', 'mobile',
            'understanding', 'deep dive', 'masterclass', 'bootcamp', 'crash course'
        ]
        
        title_lower = tab.title.lower()
        for signal in educational_signals:
            if signal in title_lower:
                return EvaluationResult(
                    classification=ProductivityLevel.PRODUCTIVE,
                    confidence=0.75,
                    reason=f"YouTube video appears educational (signal: {signal})",
                    should_close=False
                )
        
        # If still ambiguous, return None to trigger LLM evaluation
        return None
    
    def _should_use_llm(self, snapshot: ActivitySnapshot) -> bool:
        """Determine if LLM evaluation should be used."""
        if not self._llm_client:
            return False
        
        if snapshot.browser_tab:
            for rule in self.config.browser_rules:
                if rule.domain in snapshot.browser_tab.domain:
                    return rule.use_llm_evaluation
        
        return True
    
    async def _evaluate_with_llm(self, snapshot: ActivitySnapshot) -> Optional[EvaluationResult]:
        """Use LLM to evaluate the activity."""
        if not self._llm_client:
            return None
        
        prompt = self.config.llm.evaluation_prompt_template.format(
            user_goal=self.config.user_goal,
            app_name=snapshot.active_window.process_name if snapshot.active_window else "Unknown",
            window_title=snapshot.active_window.title if snapshot.active_window else "Unknown",
            url=snapshot.browser_tab.url if snapshot.browser_tab else "N/A",
            page_title=snapshot.browser_tab.title if snapshot.browser_tab else "N/A",
            content_summary=snapshot.browser_tab.content_summary if snapshot.browser_tab else "N/A"
        )
        
        try:
            provider = self.config.llm.provider.lower()
            
            if provider == "ollama":
                # Free local inference with Ollama
                response = requests.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": self.config.llm.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": self.config.llm.temperature,
                            "num_predict": self.config.llm.max_tokens
                        }
                    },
                    timeout=30
                )
                if response.status_code == 200:
                    text = response.json().get("response", "")
                else:
                    print(f"[LLM] Ollama error: {response.status_code}")
                    return None
            
            elif provider == "google":
                response = self._llm_client.generate_content(prompt)
                text = response.text
                
            elif provider == "openai":
                response = self._llm_client.chat.completions.create(
                    model=self.config.llm.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.config.llm.temperature,
                    max_tokens=self.config.llm.max_tokens
                )
                text = response.choices[0].message.content
                
            elif provider == "anthropic":
                response = self._llm_client.messages.create(
                    model=self.config.llm.model,
                    max_tokens=self.config.llm.max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )
                text = response.content[0].text
            else:
                return None
            
            # Parse the response - try JSON first, then regex fallback
            classification = ProductivityLevel.NEUTRAL
            confidence = 0.5
            reason = "LLM evaluation"
            should_close = False
            
            try:
                json_match = text
                if "```json" in text:
                    json_match = text.split("```json")[1].split("```")[0]
                elif "```" in text:
                    json_match = text.split("```")[1].split("```")[0]
                
                # Try to find JSON object in the text
                import re
                json_pattern = re.search(r'\{[^{}]*"classification"[^{}]*\}', json_match, re.DOTALL)
                if json_pattern:
                    json_match = json_pattern.group()
                
                result = json.loads(json_match.strip())
                
                classification_map = {
                    "productive": ProductivityLevel.PRODUCTIVE,
                    "neutral": ProductivityLevel.NEUTRAL,
                    "unproductive": ProductivityLevel.UNPRODUCTIVE,
                }
                
                classification = classification_map.get(result.get("classification", "neutral").lower(), ProductivityLevel.NEUTRAL)
                confidence = float(result.get("confidence", 0.5))
                reason = result.get("reason", "LLM evaluation")
                
            except json.JSONDecodeError:
                # Regex fallback - extract classification from text
                import re
                text_lower = text.lower()
                if "unproductive" in text_lower:
                    classification = ProductivityLevel.UNPRODUCTIVE
                    should_close = True
                elif "productive" in text_lower and "unproductive" not in text_lower:
                    classification = ProductivityLevel.PRODUCTIVE
                reason = "Parsed from LLM text"
            
            # ONLY close unproductive items - never close productive/neutral
            if classification == ProductivityLevel.UNPRODUCTIVE:
                should_close = True
            else:
                should_close = False
            
            return EvaluationResult(
                classification=classification,
                confidence=confidence,
                reason=reason,
                should_close=should_close,
                used_llm=True
            )
            
        except Exception as e:
            print(f"LLM evaluation error: {e}")
            return None

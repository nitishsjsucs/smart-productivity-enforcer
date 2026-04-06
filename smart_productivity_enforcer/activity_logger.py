"""Activity logging and daily analysis system."""

import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict

from smart_productivity_enforcer.config import Config, BrowserRule, AppRule, ProductivityLevel


@dataclass
class ActivityEntry:
    """A single activity log entry."""
    timestamp: str
    window_title: str
    process_name: str
    url: Optional[str] = None
    domain: Optional[str] = None
    duration_seconds: int = 10  # Default check interval


@dataclass
class DailyActivityLog:
    """Daily activity log with aggregated data."""
    date: str
    entries: List[ActivityEntry] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)  # domain/app -> total seconds


class ActivityLogger:
    """Logs all user activity for daily analysis."""
    
    def __init__(self, config: Config):
        self.config = config
        self.log_dir = Path.home() / ".smart-productivity-enforcer" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_log: Optional[DailyActivityLog] = None
        self._last_entry: Optional[ActivityEntry] = None
    
    def _get_log_file(self, log_date: date = None) -> Path:
        """Get the log file path for a given date."""
        if log_date is None:
            log_date = date.today()
        return self.log_dir / f"activity_{log_date.isoformat()}.json"
    
    def _load_or_create_log(self, log_date: date = None) -> DailyActivityLog:
        """Load existing log or create new one."""
        if log_date is None:
            log_date = date.today()
        
        log_file = self._get_log_file(log_date)
        
        if log_file.exists():
            try:
                with open(log_file, 'r') as f:
                    data = json.load(f)
                    entries = [ActivityEntry(**e) for e in data.get('entries', [])]
                    return DailyActivityLog(
                        date=data['date'],
                        entries=entries,
                        summary=data.get('summary', {})
                    )
            except Exception as e:
                print(f"Error loading log: {e}")
        
        return DailyActivityLog(date=log_date.isoformat())
    
    def _save_log(self, log: DailyActivityLog) -> None:
        """Save the activity log to disk."""
        log_file = self._get_log_file(date.fromisoformat(log.date))
        
        data = {
            'date': log.date,
            'entries': [asdict(e) for e in log.entries],
            'summary': log.summary
        }
        
        with open(log_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def log_activity(self, window_title: str, process_name: str, 
                     url: Optional[str] = None, domain: Optional[str] = None,
                     duration_seconds: int = 10) -> None:
        """Log a single activity entry."""
        today = date.today()
        
        # Load today's log if not loaded or date changed
        if self._current_log is None or self._current_log.date != today.isoformat():
            self._current_log = self._load_or_create_log(today)
        
        entry = ActivityEntry(
            timestamp=datetime.now().isoformat(),
            window_title=window_title,
            process_name=process_name,
            url=url,
            domain=domain,
            duration_seconds=duration_seconds
        )
        
        # Don't log duplicate consecutive entries
        if self._last_entry:
            if (self._last_entry.window_title == entry.window_title and
                self._last_entry.url == entry.url):
                # Just update duration in summary
                pass
            else:
                self._current_log.entries.append(entry)
        else:
            self._current_log.entries.append(entry)
        
        self._last_entry = entry
        
        # Update summary
        key = domain or process_name
        if key:
            self._current_log.summary[key] = self._current_log.summary.get(key, 0) + duration_seconds
        
        # Save periodically (every 10 entries)
        if len(self._current_log.entries) % 10 == 0:
            self._save_log(self._current_log)
    
    def save_current_log(self) -> None:
        """Force save the current log."""
        if self._current_log:
            self._save_log(self._current_log)
    
    def get_daily_summary(self, log_date: date = None) -> Dict[str, Any]:
        """Get a summary of activity for a given date."""
        log = self._load_or_create_log(log_date)
        
        # Aggregate by domain and app
        domains = defaultdict(int)
        apps = defaultdict(int)
        
        for entry in log.entries:
            if entry.domain:
                domains[entry.domain] += entry.duration_seconds
            apps[entry.process_name] += entry.duration_seconds
        
        # Sort by time spent
        sorted_domains = sorted(domains.items(), key=lambda x: x[1], reverse=True)
        sorted_apps = sorted(apps.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'date': log.date,
            'total_entries': len(log.entries),
            'top_domains': sorted_domains[:20],
            'top_apps': sorted_apps[:20],
            'unique_domains': list(domains.keys()),
            'unique_apps': list(apps.keys())
        }
    
    def get_logs_for_analysis(self, days: int = 1) -> List[Dict[str, Any]]:
        """Get activity logs for the specified number of days."""
        logs = []
        today = date.today()
        
        for i in range(days):
            log_date = date.fromordinal(today.toordinal() - i)
            summary = self.get_daily_summary(log_date)
            if summary['total_entries'] > 0:
                logs.append(summary)
        
        return logs


class DailyAnalyzer:
    """Analyzes daily activity using OpenAI and updates rules."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = ActivityLogger(config)
        self._openai_client = None
    
    def _get_openai_client(self):
        """Get or create OpenAI client."""
        if self._openai_client is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set in environment")
            
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=api_key)
        
        return self._openai_client
    
    async def analyze_and_update_rules(self, days: int = 1) -> Dict[str, Any]:
        """
        Analyze recent activity and automatically update block/allow rules.
        Returns the analysis results and changes made.
        """
        logs = self.logger.get_logs_for_analysis(days)
        
        if not logs:
            return {'error': 'No activity logs found', 'changes': []}
        
        # Prepare data for OpenAI
        all_domains = set()
        all_apps = set()
        
        for log in logs:
            all_domains.update(log['unique_domains'])
            all_apps.update(log['unique_apps'])
        
        # Get current rules to exclude already classified items
        existing_blocked_domains = {r.domain for r in self.config.browser_rules if r.always_block}
        existing_allowed_domains = {r.domain for r in self.config.browser_rules if r.always_allow}
        existing_blocked_apps = {r.process_name.lower() for r in self.config.app_rules if r.always_block}
        existing_allowed_apps = {r.process_name.lower() for r in self.config.app_rules if r.always_allow}
        
        # Filter out already classified items
        new_domains = [d for d in all_domains if d and 
                       d not in existing_blocked_domains and 
                       d not in existing_allowed_domains]
        new_apps = [a for a in all_apps if a and 
                    a.lower() not in existing_blocked_apps and 
                    a.lower() not in existing_allowed_apps]
        
        if not new_domains and not new_apps:
            return {'message': 'All items already classified', 'changes': []}
        
        # Call OpenAI for classification
        result = await self._classify_with_openai(new_domains, new_apps, logs)
        
        # Apply the classifications
        changes = self._apply_classifications(result)
        
        # Save updated config
        self.config.save()
        
        return {
            'analyzed_domains': len(new_domains),
            'analyzed_apps': len(new_apps),
            'classifications': result,
            'changes': changes
        }
    
    async def _classify_with_openai(self, domains: List[str], apps: List[str], 
                                     logs: List[Dict]) -> Dict[str, Any]:
        """Use OpenAI to classify domains and apps."""
        client = self._get_openai_client()
        
        # Build context from logs
        context_parts = []
        for log in logs:
            context_parts.append(f"Date: {log['date']}")
            context_parts.append("Top domains by time:")
            for domain, seconds in log['top_domains'][:10]:
                context_parts.append(f"  - {domain}: {seconds//60} minutes")
            context_parts.append("Top apps by time:")
            for app, seconds in log['top_apps'][:10]:
                context_parts.append(f"  - {app}: {seconds//60} minutes")
        
        context = "\n".join(context_parts)
        
        prompt = f"""You are a productivity classifier for a Masters student studying Software Engineering.

The student's goal is: {self.config.user_goal}

Based on the following activity data, classify each domain and application as either:
- PRODUCTIVE: Directly helps with software engineering studies, coding, research, documentation
- UNPRODUCTIVE: Entertainment, social media, gaming, time-wasting sites
- NEUTRAL: Could go either way, depends on context (don't block these)

Activity context:
{context}

Items to classify:

DOMAINS:
{json.dumps(domains, indent=2)}

APPLICATIONS:
{json.dumps(apps, indent=2)}

Respond in JSON format:
{{
    "productive_domains": ["domain1", "domain2"],
    "unproductive_domains": ["domain3", "domain4"],
    "productive_apps": ["app1.exe", "app2.exe"],
    "unproductive_apps": ["app3.exe", "app4.exe"],
    "reasoning": "Brief explanation of key decisions"
}}

Be strict but fair. YouTube should be unproductive unless it's clearly educational channels.
Gaming platforms (Steam, Epic, etc.) are always unproductive.
Social media is always unproductive.
Development tools, IDEs, terminals are productive.
Documentation and learning sites are productive."""

        response = client.chat.completions.create(
            model="gpt-5.2",  # Best OpenAI model for daily analysis
            messages=[
                {"role": "system", "content": "You are a productivity classification assistant. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content
        return json.loads(result_text)
    
    def _apply_classifications(self, classifications: Dict[str, Any]) -> List[str]:
        """Apply the AI classifications to the config."""
        changes = []
        
        # Add productive domains
        for domain in classifications.get('productive_domains', []):
            if domain and not any(r.domain == domain for r in self.config.browser_rules):
                self.config.browser_rules.append(BrowserRule(
                    domain=domain,
                    default_classification=ProductivityLevel.PRODUCTIVE,
                    always_allow=True
                ))
                changes.append(f"✓ Allowed domain: {domain}")
        
        # Add unproductive domains (blocked)
        for domain in classifications.get('unproductive_domains', []):
            if domain and not any(r.domain == domain for r in self.config.browser_rules):
                self.config.browser_rules.append(BrowserRule(
                    domain=domain,
                    default_classification=ProductivityLevel.BLOCKED,
                    always_block=True
                ))
                changes.append(f"✗ Blocked domain: {domain}")
        
        # Add productive apps
        for app in classifications.get('productive_apps', []):
            if app and not any(r.process_name.lower() == app.lower() for r in self.config.app_rules):
                self.config.app_rules.append(AppRule(
                    name=app,
                    process_name=app,
                    default_classification=ProductivityLevel.PRODUCTIVE,
                    always_allow=True
                ))
                changes.append(f"✓ Allowed app: {app}")
        
        # Add unproductive apps (blocked)
        for app in classifications.get('unproductive_apps', []):
            if app and not any(r.process_name.lower() == app.lower() for r in self.config.app_rules):
                self.config.app_rules.append(AppRule(
                    name=app,
                    process_name=app,
                    default_classification=ProductivityLevel.BLOCKED,
                    always_block=True
                ))
                changes.append(f"✗ Blocked app: {app}")
        
        return changes


# Singleton instances
_logger_instance: Optional[ActivityLogger] = None
_analyzer_instance: Optional[DailyAnalyzer] = None


def get_activity_logger(config: Config = None) -> ActivityLogger:
    """Get the singleton activity logger."""
    global _logger_instance
    if _logger_instance is None:
        if config is None:
            config = Config.load()
        _logger_instance = ActivityLogger(config)
    return _logger_instance


def get_daily_analyzer(config: Config = None) -> DailyAnalyzer:
    """Get the singleton daily analyzer."""
    global _analyzer_instance
    if _analyzer_instance is None:
        if config is None:
            config = Config.load()
        _analyzer_instance = DailyAnalyzer(config)
    return _analyzer_instance

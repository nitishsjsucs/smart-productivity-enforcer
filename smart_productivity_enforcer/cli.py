"""Command-line interface for Smart Productivity Enforcer."""

import asyncio
import hashlib
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm

from smart_productivity_enforcer.config import Config, ProductivityLevel
from smart_productivity_enforcer.daemon import ProductivityDaemon, run_daemon

app = typer.Typer(
    name="spe",
    help="Smart Productivity Enforcer - AI-powered focus and productivity system"
)
console = Console()


@app.command()
def start(
    duration: Optional[int] = typer.Option(
        None, "--duration", "-d",
        help="Focus session duration in minutes"
    ),
    strict: bool = typer.Option(
        False, "--strict", "-s",
        help="Enable strict mode (requires password to disable)"
    ),
    goal: Optional[str] = typer.Option(
        None, "--goal", "-g",
        help="Set your productivity goal for this session"
    ),
):
    """Start the productivity enforcer daemon."""
    config = Config.load()
    
    if goal:
        config.user_goal = goal
    
    if strict:
        config.enforcement.bypass_protection_enabled = True
        config.enforcement.require_password_to_disable = True
        
        if not config.enforcement.password_hash:
            password = Prompt.ask("Set a password for strict mode", password=True)
            config.enforcement.password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        config.save()
    
    console.print("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    console.print("[bold blue]       🧠 Smart Productivity Enforcer[/bold blue]")
    console.print("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")
    
    asyncio.run(run_daemon(duration))


@app.command()
def focus(
    preset: str = typer.Argument(
        ...,
        help="Focus session preset name (e.g., 'Deep Work', 'Learning')"
    ),
    duration: Optional[int] = typer.Option(
        None, "--duration", "-d",
        help="Override preset duration"
    ),
    background: bool = typer.Option(
        False, "--background", "-b",
        help="Run in background (survives terminal close)"
    ),
):
    """Start a predefined focus session."""
    config = Config.load()
    
    session = None
    for s in config.focus_sessions:
        if s.name.lower() == preset.lower():
            session = s
            break
    
    if not session:
        console.print(f"[red]Focus session '{preset}' not found.[/red]")
        console.print("Available sessions:")
        for s in config.focus_sessions:
            console.print(f"  - {s.name} ({s.duration_minutes} min)")
        raise typer.Exit(1)
    
    actual_duration = duration or session.duration_minutes
    
    if background:
        # Start in background mode
        from smart_productivity_enforcer.background_service import start_background
        console.print(f"[bold green]Starting '{session.name}' in background mode[/bold green]")
        start_background(session.name, actual_duration, session.strict_mode)
        return
    
    console.print(f"[bold green]Starting '{session.name}' focus session[/bold green]")
    console.print(f"Duration: {actual_duration} minutes")
    console.print(f"Strict mode: {session.strict_mode}")
    
    if session.strict_mode:
        config.enforcement.bypass_protection_enabled = True
    
    config.save()
    asyncio.run(run_daemon(actual_duration))


@app.command()
def bg(
    preset: str = typer.Argument(
        "Deep Work",
        help="Focus session preset name"
    ),
    duration: Optional[int] = typer.Option(
        None, "--duration", "-d",
        help="Override preset duration"
    ),
):
    """Start enforcer in background mode (shortcut for 'focus --background')."""
    from smart_productivity_enforcer.background_service import start_background
    
    config = Config.load()
    
    session = None
    for s in config.focus_sessions:
        if s.name.lower() == preset.lower():
            session = s
            break
    
    if not session:
        console.print(f"[red]Focus session '{preset}' not found.[/red]")
        raise typer.Exit(1)
    
    actual_duration = duration or session.duration_minutes
    start_background(session.name, actual_duration, session.strict_mode)


@app.command()
def stop(
    password: Optional[str] = typer.Option(
        None, "--password", "-p",
        help="Password to force stop during strict session"
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Force stop without password prompt"
    ),
):
    """Stop the background enforcer."""
    from smart_productivity_enforcer.background_service import stop_background, get_status
    
    status = get_status()
    
    if not status["running"]:
        console.print("[yellow]No enforcer running[/yellow]")
        return
    
    # Check if in strict session
    if status["session"] and status["session"]["strict_mode"]:
        remaining = status["session"]["remaining_minutes"]
        if remaining > 0 and not password and not force:
            console.print(f"[red]Session in progress ({remaining:.1f} min remaining)[/red]")
            password = Prompt.ask("Enter password to force stop", password=True)
    
    stop_background(password)


@app.command()
def status():
    """Check enforcer status."""
    from smart_productivity_enforcer.background_service import print_status
    print_status()


@app.command()
def config_cmd(
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
    reset: bool = typer.Option(False, "--reset", help="Reset to default configuration"),
    set_goal: Optional[str] = typer.Option(None, "--goal", help="Set productivity goal"),
    set_password: bool = typer.Option(False, "--set-password", help="Set/change bypass password"),
):
    """Manage configuration."""
    config = Config.load()
    
    if reset:
        if Confirm.ask("Reset all settings to default?"):
            config = Config()
            config.save()
            console.print("[green]Configuration reset to defaults.[/green]")
        return
    
    if set_goal:
        config.user_goal = set_goal
        config.save()
        console.print(f"[green]Goal set to: {set_goal}[/green]")
        return
    
    if set_password:
        password = Prompt.ask("Enter new password", password=True)
        confirm = Prompt.ask("Confirm password", password=True)
        
        if password != confirm:
            console.print("[red]Passwords don't match.[/red]")
            raise typer.Exit(1)
        
        config.enforcement.password_hash = hashlib.sha256(password.encode()).hexdigest()
        config.save()
        console.print("[green]Password updated.[/green]")
        return
    
    if show:
        table = Table(title="Current Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Goal", config.user_goal)
        table.add_row("Check Interval", f"{config.check_interval_seconds}s")
        table.add_row("LLM Provider", config.llm.provider)
        table.add_row("LLM Model", config.llm.model)
        table.add_row("Enforcement Enabled", str(config.enforcement.enabled))
        table.add_row("Warning Before Close", str(config.enforcement.warning_before_close))
        table.add_row("Close Unproductive Tabs", str(config.enforcement.close_unproductive_tabs))
        table.add_row("Close Unproductive Apps", str(config.enforcement.close_unproductive_apps))
        table.add_row("Bypass Protection", str(config.enforcement.bypass_protection_enabled))
        table.add_row("Password Required", str(config.enforcement.require_password_to_disable))
        table.add_row("YouTube Shorts Blocked", str(config.youtube.block_shorts))
        table.add_row("YouTube Homepage Blocked", str(config.youtube.block_homepage_suggestions))
        
        console.print(table)
        
        console.print("\n[bold]Allowed Apps:[/bold]")
        for rule in config.app_rules:
            if rule.always_allow:
                console.print(f"  [green]✓[/green] {rule.name}")
        
        console.print("\n[bold]Blocked Apps:[/bold]")
        for rule in config.app_rules:
            if rule.always_block:
                console.print(f"  [red]✗[/red] {rule.name}")
        
        console.print("\n[bold]Productive Domains:[/bold]")
        for rule in config.browser_rules:
            if rule.always_allow:
                console.print(f"  [green]✓[/green] {rule.domain}")
        
        console.print("\n[bold]Blocked Domains:[/bold]")
        for rule in config.browser_rules:
            if rule.always_block:
                console.print(f"  [red]✗[/red] {rule.domain}")


@app.command()
def allow(
    name: str = typer.Argument(..., help="App process name or domain to allow"),
    app: bool = typer.Option(False, "--app", "-a", help="Add as application rule"),
    domain: bool = typer.Option(False, "--domain", "-d", help="Add as domain rule"),
):
    """Add an always-allowed app or domain."""
    config = Config.load()
    
    if app or (not app and not domain and ".exe" in name.lower()):
        from smart_productivity_enforcer.config import AppRule
        new_rule = AppRule(
            name=name,
            process_name=name,
            default_classification=ProductivityLevel.PRODUCTIVE,
            always_allow=True
        )
        config.app_rules.append(new_rule)
        config.save()
        console.print(f"[green]Added {name} to allowed apps.[/green]")
    else:
        from smart_productivity_enforcer.config import BrowserRule
        new_rule = BrowserRule(
            domain=name,
            default_classification=ProductivityLevel.PRODUCTIVE,
            always_allow=True
        )
        config.browser_rules.append(new_rule)
        config.save()
        console.print(f"[green]Added {name} to allowed domains.[/green]")


@app.command()
def block(
    name: str = typer.Argument(..., help="App process name or domain to block"),
    app: bool = typer.Option(False, "--app", "-a", help="Add as application rule"),
    domain: bool = typer.Option(False, "--domain", "-d", help="Add as domain rule"),
):
    """Add an always-blocked app or domain."""
    config = Config.load()
    
    if app or (not app and not domain and ".exe" in name.lower()):
        from smart_productivity_enforcer.config import AppRule
        new_rule = AppRule(
            name=name,
            process_name=name,
            default_classification=ProductivityLevel.BLOCKED,
            always_block=True
        )
        config.app_rules.append(new_rule)
        config.save()
        console.print(f"[red]Added {name} to blocked apps.[/red]")
    else:
        from smart_productivity_enforcer.config import BrowserRule
        new_rule = BrowserRule(
            domain=name,
            default_classification=ProductivityLevel.BLOCKED,
            always_block=True
        )
        config.browser_rules.append(new_rule)
        config.save()
        console.print(f"[red]Added {name} to blocked domains.[/red]")


@app.command()
def youtube(
    block_shorts: Optional[bool] = typer.Option(None, "--block-shorts/--allow-shorts"),
    block_homepage: Optional[bool] = typer.Option(None, "--block-homepage/--allow-homepage"),
    add_channel: Optional[str] = typer.Option(None, "--add-channel", help="Add productive channel"),
    remove_channel: Optional[str] = typer.Option(None, "--remove-channel", help="Remove channel"),
    show: bool = typer.Option(False, "--show", help="Show YouTube settings"),
):
    """Configure YouTube-specific rules."""
    config = Config.load()
    
    if block_shorts is not None:
        config.youtube.block_shorts = block_shorts
        config.save()
        status = "blocked" if block_shorts else "allowed"
        console.print(f"[yellow]YouTube Shorts are now {status}.[/yellow]")
    
    if block_homepage is not None:
        config.youtube.block_homepage_suggestions = block_homepage
        config.save()
        status = "blocked" if block_homepage else "allowed"
        console.print(f"[yellow]YouTube homepage is now {status}.[/yellow]")
    
    if add_channel:
        if add_channel not in config.youtube.productive_channels:
            config.youtube.productive_channels.append(add_channel)
            config.save()
            console.print(f"[green]Added '{add_channel}' to productive channels.[/green]")
        else:
            console.print(f"[yellow]'{add_channel}' is already in productive channels.[/yellow]")
    
    if remove_channel:
        if remove_channel in config.youtube.productive_channels:
            config.youtube.productive_channels.remove(remove_channel)
            config.save()
            console.print(f"[red]Removed '{remove_channel}' from productive channels.[/red]")
    
    if show:
        console.print("\n[bold]YouTube Configuration:[/bold]")
        console.print(f"  Block Shorts: {config.youtube.block_shorts}")
        console.print(f"  Block Homepage: {config.youtube.block_homepage_suggestions}")
        console.print(f"  Use LLM Evaluation: {config.youtube.use_llm_evaluation}")
        console.print(f"  Max Entertainment Minutes: {config.youtube.max_daily_entertainment_minutes}")
        
        console.print("\n[bold]Productive Channels:[/bold]")
        for channel in config.youtube.productive_channels:
            console.print(f"  [green]✓[/green] {channel}")
        
        console.print("\n[bold]Productive Keywords:[/bold]")
        console.print(f"  {', '.join(config.youtube.productive_keywords[:10])}...")
        
        console.print("\n[bold]Unproductive Keywords:[/bold]")
        console.print(f"  {', '.join(config.youtube.unproductive_keywords[:10])}...")


@app.command()
def stats(
    today: bool = typer.Option(True, "--today", help="Show today's stats"),
    week: bool = typer.Option(False, "--week", help="Show this week's stats"),
):
    """Show productivity statistics."""
    from pathlib import Path
    from datetime import datetime, timedelta
    import json
    
    log_dir = Path.home() / ".smart-productivity-enforcer" / "logs"
    
    if not log_dir.exists():
        console.print("[yellow]No activity logs found yet.[/yellow]")
        return
    
    stats = {
        "productive": 0,
        "unproductive": 0,
        "neutral": 0,
        "enforcement_actions": 0,
    }
    
    if week:
        start_date = datetime.now() - timedelta(days=7)
    else:
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    for log_file in log_dir.glob("enforcement_*.jsonl"):
        try:
            file_date_str = log_file.stem.replace("enforcement_", "")
            file_date = datetime.strptime(file_date_str, "%Y-%m-%d")
            
            if file_date >= start_date:
                with open(log_file, "r") as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            if entry.get("type") in ["close_tab", "close_app"]:
                                stats["enforcement_actions"] += 1
                        except json.JSONDecodeError:
                            continue
        except (ValueError, Exception):
            continue
    
    table = Table(title=f"Productivity Stats ({'This Week' if week else 'Today'})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Enforcement Actions", str(stats["enforcement_actions"]))
    
    console.print(table)


@app.command()
def sessions():
    """List available focus session presets."""
    config = Config.load()
    
    table = Table(title="Focus Session Presets")
    table.add_column("Name", style="cyan")
    table.add_column("Duration", style="green")
    table.add_column("Strict Mode", style="yellow")
    table.add_column("Allowed Apps", style="blue")
    
    for session in config.focus_sessions:
        table.add_row(
            session.name,
            f"{session.duration_minutes} min",
            "Yes" if session.strict_mode else "No",
            ", ".join(session.allowed_apps[:3]) + ("..." if len(session.allowed_apps) > 3 else "")
        )
    
    console.print(table)
    console.print("\n[dim]Use 'spe focus <name>' to start a session[/dim]")


@app.command()
def stop(
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password to force stop"),
):
    """Stop the running daemon (if allowed)."""
    console.print("[yellow]To stop the daemon, press Ctrl+C in the terminal where it's running.[/yellow]")
    console.print("[yellow]If in strict mode, you'll need to provide the password.[/yellow]")


@app.command()
def logs(
    days: int = typer.Option(1, "--days", "-d", help="Number of days to show"),
):
    """View activity logs summary."""
    from smart_productivity_enforcer.activity_logger import get_activity_logger
    
    config = Config.load()
    logger = get_activity_logger(config)
    
    for i in range(days):
        from datetime import date, timedelta
        log_date = date.today() - timedelta(days=i)
        summary = logger.get_daily_summary(log_date)
        
        if summary['total_entries'] == 0:
            console.print(f"\n[dim]No activity logged for {log_date}[/dim]")
            continue
        
        console.print(f"\n[bold cyan]📊 Activity for {summary['date']}[/bold cyan]")
        console.print(f"Total entries: {summary['total_entries']}")
        
        if summary['top_domains']:
            table = Table(title="Top Domains")
            table.add_column("Domain", style="cyan")
            table.add_column("Time", style="green")
            
            for domain, seconds in summary['top_domains'][:10]:
                minutes = seconds // 60
                table.add_row(domain, f"{minutes} min")
            
            console.print(table)
        
        if summary['top_apps']:
            table = Table(title="Top Applications")
            table.add_column("Application", style="cyan")
            table.add_column("Time", style="green")
            
            for app, seconds in summary['top_apps'][:10]:
                minutes = seconds // 60
                table.add_row(app, f"{minutes} min")
            
            console.print(table)


@app.command()
def analyze(
    days: int = typer.Option(1, "--days", "-d", help="Number of days to analyze"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be classified without applying"),
):
    """Analyze activity with AI and auto-update block/allow lists."""
    import os
    
    if not os.getenv("OPENAI_API_KEY"):
        console.print("[red]Error: OPENAI_API_KEY not set in environment[/red]")
        console.print("[yellow]Add OPENAI_API_KEY=your-key to your .env file[/yellow]")
        return
    
    from smart_productivity_enforcer.activity_logger import get_daily_analyzer
    
    config = Config.load()
    analyzer = get_daily_analyzer(config)
    
    console.print(f"[bold]🤖 Analyzing {days} day(s) of activity with GPT-4o...[/bold]")
    
    try:
        result = asyncio.run(analyzer.analyze_and_update_rules(days))
        
        if 'error' in result:
            console.print(f"[red]{result['error']}[/red]")
            return
        
        if 'message' in result:
            console.print(f"[yellow]{result['message']}[/yellow]")
            return
        
        console.print(f"\n[green]✓ Analyzed {result.get('analyzed_domains', 0)} domains and {result.get('analyzed_apps', 0)} apps[/green]")
        
        if result.get('classifications', {}).get('reasoning'):
            console.print(f"\n[dim]AI Reasoning: {result['classifications']['reasoning']}[/dim]")
        
        if result.get('changes'):
            console.print("\n[bold]Changes made:[/bold]")
            for change in result['changes']:
                console.print(f"  {change}")
        else:
            console.print("\n[yellow]No new items to classify[/yellow]")
            
    except Exception as e:
        console.print(f"[red]Error during analysis: {e}[/red]")


@app.command()
def learn():
    """Quick command to analyze today's activity and update rules."""
    import os
    
    if not os.getenv("OPENAI_API_KEY"):
        console.print("[red]Error: OPENAI_API_KEY not set in environment[/red]")
        console.print("[yellow]Add OPENAI_API_KEY=your-key to your .env file[/yellow]")
        return
    
    from smart_productivity_enforcer.activity_logger import get_daily_analyzer
    
    config = Config.load()
    analyzer = get_daily_analyzer(config)
    
    console.print("[bold]🧠 Learning from today's activity...[/bold]")
    
    try:
        result = asyncio.run(analyzer.analyze_and_update_rules(1))
        
        if result.get('changes'):
            console.print("\n[green]✓ Updated rules based on your activity:[/green]")
            for change in result['changes']:
                console.print(f"  {change}")
            console.print("\n[dim]Rules saved to config. Will apply on next session.[/dim]")
        else:
            console.print("[yellow]No new items to learn from today's activity.[/yellow]")
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()

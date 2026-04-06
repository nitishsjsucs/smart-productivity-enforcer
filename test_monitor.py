"""Test script to verify the activity monitor is working."""

import asyncio
from rich.console import Console
from rich.table import Table

from smart_productivity_enforcer.config import Config
from smart_productivity_enforcer.activity_monitor import ActivityMonitor
from smart_productivity_enforcer.llm_evaluator import ProductivityEvaluator

console = Console()


async def test_activity_monitor():
    """Test the activity monitoring capabilities."""
    console.print("\n[bold blue]🔍 Testing Activity Monitor[/bold blue]\n")
    
    config = Config.load()
    monitor = ActivityMonitor(config)
    
    console.print("[cyan]Taking activity snapshot...[/cyan]")
    snapshot = await monitor.take_snapshot()
    
    table = Table(title="Activity Snapshot")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    if snapshot.active_window:
        table.add_row("Window Title", snapshot.active_window.title[:60] + "...")
        table.add_row("Process", snapshot.active_window.process_name)
        table.add_row("Is Browser", str(snapshot.active_window.is_browser))
    else:
        table.add_row("Active Window", "None detected")
    
    if snapshot.browser_tab:
        table.add_row("Tab URL", snapshot.browser_tab.url[:60] + "..." if snapshot.browser_tab.url else "N/A")
        table.add_row("Tab Domain", snapshot.browser_tab.domain)
        table.add_row("Is YouTube", str(snapshot.browser_tab.is_youtube))
    
    table.add_row("Idle Time", f"{snapshot.idle_time_seconds:.1f} seconds")
    table.add_row("Running Processes", str(len(snapshot.running_processes)))
    
    console.print(table)
    
    return snapshot


async def test_evaluator(snapshot):
    """Test the productivity evaluator."""
    console.print("\n[bold blue]🤖 Testing Productivity Evaluator[/bold blue]\n")
    
    config = Config.load()
    evaluator = ProductivityEvaluator(config)
    
    console.print("[cyan]Evaluating activity...[/cyan]")
    result = await evaluator.evaluate(snapshot)
    
    color_map = {
        "productive": "green",
        "neutral": "yellow",
        "unproductive": "red",
        "blocked": "red bold"
    }
    color = color_map.get(result.classification.value, "white")
    
    table = Table(title="Evaluation Result")
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    
    table.add_row("Classification", f"[{color}]{result.classification.value.upper()}[/{color}]")
    table.add_row("Confidence", f"{result.confidence:.1%}")
    table.add_row("Reason", result.reason)
    table.add_row("Should Close", f"[red]{result.should_close}[/red]" if result.should_close else str(result.should_close))
    table.add_row("Used LLM", str(result.used_llm))
    
    console.print(table)


async def test_continuous(duration_seconds: int = 30):
    """Run continuous monitoring for a duration."""
    console.print(f"\n[bold blue]📊 Continuous Monitoring ({duration_seconds}s)[/bold blue]\n")
    
    config = Config.load()
    config.check_interval_seconds = 5
    monitor = ActivityMonitor(config)
    evaluator = ProductivityEvaluator(config)
    
    start_time = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start_time) < duration_seconds:
        snapshot = await monitor.take_snapshot()
        result = await evaluator.evaluate(snapshot)
        
        color_map = {
            "productive": "green",
            "neutral": "yellow", 
            "unproductive": "red",
            "blocked": "red"
        }
        color = color_map.get(result.classification.value, "white")
        
        window_title = snapshot.active_window.title[:40] if snapshot.active_window else "None"
        console.print(
            f"[{color}]●[/{color}] "
            f"[dim]{result.classification.value:12}[/dim] | "
            f"{window_title}..."
        )
        
        await asyncio.sleep(5)
    
    console.print("\n[green]✓ Continuous monitoring test complete![/green]")


async def main():
    """Run all tests."""
    console.print("[bold]=" * 60)
    console.print("[bold cyan]Smart Productivity Enforcer - Test Suite[/bold cyan]")
    console.print("[bold]=" * 60)
    
    snapshot = await test_activity_monitor()
    
    await test_evaluator(snapshot)
    
    console.print("\n[yellow]Starting 30-second continuous monitoring test...[/yellow]")
    console.print("[dim]Press Ctrl+C to skip[/dim]\n")
    
    try:
        await test_continuous(30)
    except KeyboardInterrupt:
        console.print("\n[yellow]Skipped continuous test[/yellow]")
    
    console.print("\n[bold green]✓ All tests complete![/bold green]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Tests interrupted[/yellow]")

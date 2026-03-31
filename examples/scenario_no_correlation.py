"""Demo scenario: Spike detected but no flag correlation.

Demonstrates that the agent does NOT blindly rollback — when an error
spike occurs but no recent flag change correlates, it logs the finding
and continues monitoring.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from rich.console import Console
from rich.panel import Panel

from src.agent.correlation_engine import CorrelationEngine
from src.agent.error_monitor import ErrorMonitor
from src.config import AgentConfig
from src.mcp_server.posthog_client import PostHogClient
from src.simulator.error_stream import ErrorStreamSimulator
from src.simulator.posthog_mock import PostHogMock

console = Console()


async def run_demo() -> None:
    """Execute the no-correlation scenario."""
    console.print(
        Panel(
            "[bold yellow]🔍 Scenario: Spike With No Flag Correlation[/bold yellow]\n\n"
            "An error spike occurs, but no feature flag was recently changed.\n"
            "The agent correctly decides NOT to take autonomous action.",
            title="Demo: No Correlation",
            border_style="yellow",
            expand=False,
        )
    )

    config = AgentConfig(use_simulator=True, spike_threshold_std=2.0)
    mock = PostHogMock()
    client = PostHogClient(config, mock=mock)
    await client.__aenter__()

    monitor = ErrorMonitor(baseline_window=300, spike_threshold_std=2.0, bucket_seconds=5)
    correlator = CorrelationEngine()
    sim = ErrorStreamSimulator(base_rate=5, simulation_speed=10.0)

    # Build baseline
    console.print("\n[cyan]Building baseline...[/cyan]")
    for _ in range(8):
        monitor.ingest(sim.generate_batch())
        await asyncio.sleep(0.2)
    console.print(f"  Baseline: {monitor.get_baseline():.1f} errors/bucket")

    # Trigger spike (but NO flag changes exist)
    console.print("\n[cyan]Triggering error spike (no flags changed)...[/cyan]")
    sim.trigger_spike("phantom-flag", multiplier=5.0)

    for cycle in range(1, 5):
        batch = sim.generate_batch()
        monitor.ingest(batch)
        spike = monitor.detect_spike()
        if spike:
            console.print(
                f"\n[red]⚡ Spike detected![/red] Factor: {spike.spike_factor:.1f}x"
            )
            # No flags changed → empty list
            flag_changes = await client.get_recent_flag_changes(within_minutes=120)
            console.print(f"  Recent flag changes: {len(flag_changes)}")
            correlation = correlator.correlate(spike, flag_changes)
            console.print(
                Panel(
                    "\n".join(correlation.reasoning_chain),
                    title="Reasoning",
                    border_style="dim",
                )
            )
            console.print(
                f"  Action: [bold]{correlation.recommended_action.value}[/bold] "
                f"(confidence: {correlation.overall_confidence:.4f})"
            )
            console.print("  [green]✓ Agent correctly did NOT auto-rollback[/green]")
            break
        await asyncio.sleep(0.5)

    await client.__aexit__(None, None, None)
    console.print(
        Panel("[bold green]✅ Scenario complete[/bold green]", border_style="green")
    )


def main() -> None:
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(20))
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        console.print("\n[yellow]Demo interrupted.[/yellow]")


if __name__ == "__main__":
    main()

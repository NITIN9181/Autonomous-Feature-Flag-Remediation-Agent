"""Demo scenario: Agent hits safety limit and requests human approval.

Shows the safety guard in action — after exhausting the auto-rollback
rate limit, the agent requests human approval instead of proceeding.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from rich.console import Console
from rich.panel import Panel

from src.agent.correlation_engine import CorrelationEngine
from src.agent.error_monitor import ErrorMonitor
from src.agent.incident_reporter import IncidentReporter
from src.agent.safety import SafetyGuard
from src.config import AgentConfig
from src.mcp_server.posthog_client import PostHogClient
from src.mcp_server.tools import MCPTools
from src.models import FlagAction, RollbackAction
from src.simulator.error_stream import ErrorStreamSimulator
from src.simulator.posthog_mock import PostHogMock
from src.simulator.slack_webhook import SlackWebhookSimulator

console = Console()


async def run_demo() -> None:
    """Execute the safety-gate scenario."""
    console.print(
        Panel(
            "[bold red]🛡️ Scenario: Safety Gate — Rate Limit Hit[/bold red]\n\n"
            "The agent has already performed 2 auto-rollbacks this hour.\n"
            "When a third spike occurs, the safety guard blocks autonomous\n"
            "action and requests human approval.",
            title="Demo: Safety Gate",
            border_style="red",
            expand=False,
        )
    )

    config = AgentConfig(
        use_simulator=True,
        max_auto_rollbacks_per_hour=2,
        cooldown_after_rollback_seconds=5,
        spike_threshold_std=2.0,
    )

    mock = PostHogMock()
    client = PostHogClient(config, mock=mock)
    await client.__aenter__()

    safety = SafetyGuard(config)
    tools = MCPTools(client, config, safety)
    monitor = ErrorMonitor(baseline_window=300, spike_threshold_std=2.0, bucket_seconds=5)
    correlator = CorrelationEngine(auto_threshold=0.70)
    slack_sim = SlackWebhookSimulator()
    reporter = IncidentReporter(slack_sim=slack_sim)
    sim = ErrorStreamSimulator(base_rate=5, simulation_speed=10.0)

    # Build baseline
    console.print("\n[cyan]Building baseline...[/cyan]")
    for _ in range(8):
        monitor.ingest(sim.generate_batch())
        await asyncio.sleep(0.1)

    # Simulate 3 flags being deployed
    for i, flag_key in enumerate(["flag-alpha", "flag-beta", "flag-gamma"]):
        await client.create_flag(flag_key, enabled=True)
        console.print(f"\n[bold]── Incident {i + 1}: '{flag_key}' ──[/bold]")

        # Trigger spike
        sim.trigger_spike(flag_key, multiplier=5.0)
        for _ in range(3):
            monitor.ingest(sim.generate_batch())
            await asyncio.sleep(0.2)

        spike = monitor.detect_spike()
        if spike is None:
            console.print("  [dim]No spike (insufficient signal)[/dim]")
            sim.stop_spike()
            continue

        flag_changes = await client.get_recent_flag_changes(within_minutes=120)
        correlation = correlator.correlate(spike, flag_changes)

        rollback = RollbackAction(
            flag_key=flag_key,
            action=FlagAction.DISABLE,
            reason=f"Spike {spike.spike_factor:.1f}x correlated with '{flag_key}'",
            confidence=correlation.overall_confidence,
        )

        safety_decision = safety.can_execute(rollback)
        if safety_decision.allowed:
            await tools.toggle_feature_flag(flag_key, "rollback", rollback.reason)
            console.print(f"  [green]✓ Auto-rollback of '{flag_key}' succeeded[/green]")
        else:
            console.print(
                Panel(
                    f"[bold yellow]⚠ SAFETY GATE ACTIVATED[/bold yellow]\n\n"
                    + "\n".join(f"• {r}" for r in safety_decision.reasons)
                    + "\n\nOverrides needed: "
                    + ", ".join(safety_decision.overrides_needed),
                    border_style="yellow",
                )
            )
            summary = reporter.generate_summary(spike, correlation, "safety_blocked")
            await reporter.post_to_slack(summary, "")
            console.print("  [yellow]Human approval requested — Slack notification sent[/yellow]")

        sim.stop_spike()
        await asyncio.sleep(0.5)

    console.print(
        Panel(
            f"[bold green]✅ Demo complete[/bold green]\n"
            f"Audit trail entries: {len(safety.get_audit_trail())}\n"
            f"Slack notifications: {len(slack_sim.messages)}",
            border_style="green",
        )
    )
    await client.__aexit__(None, None, None)


def main() -> None:
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(20))
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        console.print("\n[yellow]Demo interrupted.[/yellow]")


if __name__ == "__main__":
    main()

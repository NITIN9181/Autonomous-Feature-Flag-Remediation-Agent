"""Demo scenario: Error spike triggers autonomous rollback.

This is the flagship demo — it runs the full remediation loop end-to-end:

1. Starts the simulator generating normal background traffic.
2. Shows the agent monitoring peacefully.
3. Simulates a feature flag being enabled (``new-checkout-flow``).
4. Immediately injects correlated errors.
5. Agent detects the spike within 1–2 polling cycles.
6. Agent performs correlation analysis (reasoning chain visible).
7. Agent decides to rollback with high confidence.
8. Agent executes rollback via ``toggle_feature_flag``.
9. Shows the incident summary posted to mock Slack.
10. Agent verifies error rate drops after rollback.

Total runtime: ~2–3 minutes.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.agent.correlation_engine import CorrelationEngine
from src.agent.error_monitor import ErrorMonitor
from src.agent.incident_reporter import IncidentReporter
from src.agent.safety import SafetyGuard
from src.config import AgentConfig
from src.mcp_server.posthog_client import PostHogClient
from src.mcp_server.tools import MCPTools
from src.models import FlagAction, RecommendedAction, RollbackAction
from src.simulator.error_stream import ErrorStreamSimulator
from src.simulator.posthog_mock import PostHogMock
from src.simulator.slack_webhook import SlackWebhookSimulator

console = Console()


async def run_demo() -> None:
    """Execute the full spike → rollback demo."""

    console.print(
        Panel(
            "[bold green]🎬 Autonomous Feature Flag Remediation — Live Demo[/bold green]\n\n"
            "This demo simulates a real-world incident where a newly-enabled\n"
            "feature flag causes a cascade of checkout errors. The agent will\n"
            "detect the spike, correlate it with the flag change, and\n"
            "autonomously roll it back.\n\n"
            "[dim]Duration: ~2 minutes[/dim]",
            title="PostHog Flag Agent Demo",
            border_style="bright_green",
            expand=False,
        )
    )

    # ── Setup ────────────────────────────────────────────────
    config = AgentConfig(
        use_simulator=True,
        poll_interval_seconds=5,
        spike_threshold_std=2.5,
        correlation_confidence_auto_threshold=0.75,
        max_auto_rollbacks_per_hour=5,
        cooldown_after_rollback_seconds=10,
    )

    mock = PostHogMock()
    client = PostHogClient(config, mock=mock)
    await client.__aenter__()

    safety = SafetyGuard(config)
    tools = MCPTools(client, config, safety)
    monitor = ErrorMonitor(
        baseline_window=300,
        spike_threshold_std=config.spike_threshold_std,
        bucket_seconds=5,
    )
    correlator = CorrelationEngine(
        auto_threshold=config.correlation_confidence_auto_threshold,
        alert_threshold=config.correlation_confidence_alert_threshold,
    )
    slack_sim = SlackWebhookSimulator()
    reporter = IncidentReporter(slack_sim=slack_sim)
    sim = ErrorStreamSimulator(base_rate=5, simulation_speed=10.0)

    # ── Phase A: Build baseline (normal traffic) ─────────────
    console.print("\n[bold cyan]▸ Phase A: Building baseline (normal traffic)...[/bold cyan]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Ingesting baseline errors...", total=8)
        for i in range(8):
            batch = sim.generate_batch()
            monitor.ingest(batch)
            progress.update(task, advance=1)
            await asyncio.sleep(0.3)

    baseline = monitor.get_baseline()
    console.print(f"  Baseline established: [bold]{baseline:.1f}[/bold] errors/bucket\n")

    # ── Phase B: Enable feature flag ─────────────────────────
    console.print("[bold cyan]▸ Phase B: Enabling 'new-checkout-flow' feature flag...[/bold cyan]")
    await client.create_flag("new-checkout-flow", enabled=True, rollout_percentage=100)
    console.print("  [green]✓ Flag 'new-checkout-flow' is now ACTIVE[/green]\n")
    await asyncio.sleep(1)

    # ── Phase C: Inject error spike ──────────────────────────
    console.print("[bold cyan]▸ Phase C: Simulating correlated error spike...[/bold cyan]")
    sim.trigger_spike("new-checkout-flow", multiplier=6.0)

    spike_detected = False
    for cycle in range(1, 6):
        console.print(f"\n[dim]── Detection cycle {cycle} ──[/dim]")

        batch = sim.generate_batch()
        console.print(f"  Ingested [bold]{len(batch)}[/bold] errors")
        monitor.ingest(batch)

        spike = monitor.detect_spike()
        if spike is None:
            console.print("  [green]✓ No spike detected (still building signal)[/green]")
            await asyncio.sleep(1)
            continue

        spike_detected = True
        console.print(
            Panel(
                f"[bold red]⚡ SPIKE DETECTED[/bold red]\n"
                f"Rate: {spike.current_rate:.1f} errors/bucket "
                f"(baseline: {spike.baseline_rate:.1f})\n"
                f"Spike factor: {spike.spike_factor:.1f}x\n"
                f"Affected services: {', '.join(spike.affected_services)}",
                border_style="red",
            )
        )

        # Correlate
        console.print("[cyan]Correlating with flag changes...[/cyan]")
        flag_changes = await client.get_recent_flag_changes(within_minutes=120)
        correlation = correlator.correlate(spike, flag_changes)

        console.print(
            Panel(
                "\n".join(correlation.reasoning_chain),
                title="🔍 Reasoning Chain",
                border_style="yellow",
            )
        )

        # Decide
        flag_key = correlation.correlated_flag.flag_key if correlation.correlated_flag else "N/A"
        console.print(
            f"  Decision: [bold]{correlation.recommended_action.value}[/bold] "
            f"| Confidence: [bold]{correlation.overall_confidence:.4f}[/bold] "
            f"| Flag: [bold]{flag_key}[/bold]"
        )

        if correlation.recommended_action == RecommendedAction.AUTO_ROLLBACK and flag_key != "N/A":
            # Safety check
            rollback = RollbackAction(
                flag_key=flag_key,
                action=FlagAction.DISABLE,
                reason=f"Demo auto-rollback: {spike.spike_factor:.1f}x spike",
                confidence=correlation.overall_confidence,
            )
            safety_result = safety.can_execute(rollback)

            if safety_result.allowed:
                console.print(f"\n[bold]Executing rollback of '{flag_key}'...[/bold]")
                result = await tools.toggle_feature_flag(
                    flag_key=flag_key,
                    action="rollback",
                    reason=rollback.reason,
                )
                console.print(f"  [bold green]✓ Flag '{flag_key}' ROLLED BACK[/bold green]")
                sim.stop_spike()

                # Generate incident summary
                summary = reporter.generate_summary(spike, correlation, "auto_rollback")
                await reporter.post_to_slack(summary, "")

                # Verify
                console.print("\n[cyan]Verifying remediation...[/cyan]")
                await asyncio.sleep(2)
                verify_batch = sim.generate_batch()
                monitor.ingest(verify_batch)
                new_spike = monitor.detect_spike()
                if new_spike is None:
                    console.print("  [bold green]✓ Error rate returned to normal![/bold green]")
                    summary.verification_status = "resolved"
                else:
                    console.print("  [yellow]⚠ Errors still elevated — escalating[/yellow]")
                    summary.verification_status = "escalated"

                break
            else:
                console.print(
                    f"  [yellow]Safety blocked: {'; '.join(safety_result.reasons)}[/yellow]"
                )
        await asyncio.sleep(1)

    if not spike_detected:
        console.print("[yellow]No spike detected in allotted cycles — try again.[/yellow]")

    # ── Summary ──────────────────────────────────────────────
    console.print(
        Panel(
            "[bold green]✅ Demo Complete[/bold green]\n\n"
            f"Baseline errors/bucket: {baseline:.1f}\n"
            f"Spike factor at detection: {spike.spike_factor:.1f}x\n" if spike_detected else ""
            f"Slack messages sent: {len(slack_sim.messages)}\n"
            f"Audit trail entries: {len(safety.get_audit_trail())}",
            title="Results",
            border_style="green",
        )
    )

    await client.__aexit__(None, None, None)


def main() -> None:
    """CLI entry-point."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(20),
    )
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        console.print("\n[yellow]Demo interrupted.[/yellow]")


if __name__ == "__main__":
    main()

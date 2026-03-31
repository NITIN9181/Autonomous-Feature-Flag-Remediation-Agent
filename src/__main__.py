import asyncio
import sys

import click
import structlog
from rich.console import Console

from src.agent.remediation_agent import RemediationAgent
from src.config import AgentConfig
from src.mcp_server.server import serve_stdio

console = Console()

@click.group()
def cli():
    """Autonomous Feature Flag Remediation Agent -- CLI."""
    # Setup structured logging
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
    )

@cli.command()
def agent():
    """Run the autonomous remediation agent in a continuous loop."""
    config = AgentConfig()
    agent = RemediationAgent(config)
    console.print("[bold green]Starting Autonomous Remediation Agent...[/bold green]")
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Agent stopped by user.[/yellow]")

@cli.command()
def server():
    """Run the MCP server over stdio."""
    console.print("[bold blue]Starting MCP Server (stdio)...[/bold blue]")
    asyncio.run(serve_stdio())

@cli.command()
def demo():
    """Run the flagship spike->rollback demo scenario."""
    from examples.scenario_spike import main as run_demo
    run_demo()

@cli.command()
def simulate():
    """Run the interactive error stream simulator."""
    from src.simulator.error_stream import ErrorStreamSimulator
    from src.simulator.posthog_mock import PostHogMock
    
    config = AgentConfig(use_simulator=True)
    sim = ErrorStreamSimulator(base_rate=5)
    console.print("[bold cyan]Starting Error Stream Simulator...[/bold cyan]")
    try:
        while True:
            batch = sim.generate_batch()
            console.print(f"Generated {len(batch)} errors")
            asyncio.run(asyncio.sleep(5))
    except KeyboardInterrupt:
        console.print("\n[yellow]Simulator stopped.[/yellow]")

def main():
    cli()

if __name__ == "__main__":
    main()

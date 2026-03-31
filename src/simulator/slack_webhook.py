from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import structlog
from rich.console import Console
from rich.panel import Panel

logger = structlog.get_logger()
console = Console()


class SlackWebhookSimulator:
    """Mocks Slack's incoming webhook for visual demo feedback."""

    def __init__(self):
        self.messages: List[Dict[str, Any]] = []

    async def post_message(self, message: Dict[str, Any]) -> None:
        """Simulate posting to Slack by printing to console with pretty formatting."""
        self.messages.append(message)
        
        # Visual notification
        console.print("\n")
        console.print(
            Panel(
                f"[bold cyan]Slack Notification Received[/bold cyan]\n"
                f"Incident: {message.get('incident_id')}\n"
                f"Plan: {message.get('remediation_plan')}\n"
                f"Confidence: [bold]{message.get('correlation', {}).get('overall_confidence', 0):.4f}[/bold]",
                title="Slack Mock",
                border_style="cyan",
                expand=False,
            )
        )
        logger.info("Message intercepted by Slack simulator", incident_id=message.get('incident_id'))
        await asyncio.sleep(0.1)

    def get_messages(self) -> List[Dict[str, Any]]:
        return self.messages

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx
import structlog
from src.models import (
    CorrelationResult,
    ErrorLog,
    IncidentSummary,
    SpikeEvent,
)

logger = structlog.get_logger()


class IncidentReporter:
    """Generates and distributes incident reports."""

    def __init__(self, slack_sim: Optional[Any] = None):
        self.slack_sim = slack_sim

    def generate_summary(
        self, spike: SpikeEvent, correlation: CorrelationResult, outcome: str
    ) -> IncidentSummary:
        """Create a structured summary of the incident."""
        incident_id = f"inc_{int(spike.onset_timestamp.timestamp())}"
        
        remediation_plan = "None"
        if outcome == "auto_rollback":
            remediation_plan = f"Automatically disabled flag `{correlation.correlated_flag.flag_key}`"
        elif outcome == "safety_blocked":
            remediation_plan = f"Recommend manual disable of `{correlation.correlated_flag.flag_key}` (Automated action blocked by safety guard)"
        elif outcome == "manual_recommendation":
             remediation_plan = f"High probability cause: `{correlation.correlated_flag.flag_key}`. Investigation recommended."

        return IncidentSummary(
            incident_id=incident_id,
            spike=spike,
            correlation=correlation,
            remediation_plan=remediation_plan,
        )

    async def post_to_slack(self, summary: IncidentSummary, webhook_url: str) -> bool:
        """Post the incident report to Slack using Block Kit."""
        if self.slack_sim:
            await self.slack_sim.post_message(summary.model_dump(mode="json"))
            return True

        if not webhook_url:
            logger.info("No Slack webhook configured, skipping notification", summary=summary.incident_id)
            return False

        blocks = self._build_slack_blocks(summary)
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(webhook_url, json={"blocks": blocks})
                resp.raise_for_status()
            logger.info("Posted incident to Slack", incident=summary.incident_id)
            return True
        except Exception as e:
            logger.error("Failed to post to Slack", error=str(e))
            return False

    def _build_slack_blocks(self, summary: IncidentSummary) -> List[Dict[str, Any]]:
        """Construct Slack Block Kit UI."""
        corr = summary.correlation
        spike = summary.spike
        flag_key = corr.correlated_flag.flag_key if corr.correlated_flag else "N/A"
        
        status_emoji = "🟠"
        if summary.verification_status == "resolved":
            status_emoji = "✅"
        elif summary.verification_status == "escalated":
            status_emoji = "🚨"

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🛡️ Autonomous Remediation Summary: {summary.incident_id}"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Status:* {status_emoji} {summary.verification_status or 'Investigating'}"},
                    {"type": "mrkdwn", "text": f"*Confidence:* `{corr.overall_confidence:.4f}`"}
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Remediation:* {summary.remediation_plan}"}
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Spike Detect:* {spike.spike_factor:.1f}x baseline ({spike.current_rate} vs {spike.baseline_rate:.1f} errors/bucket)"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Correlated Flag:* `{flag_key}`"}
            }
        ]

        # Add reasoning chain
        reasoning = "\n".join([f"• {r}" for r in corr.reasoning_chain[:3]])
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Reasoning:*\n{reasoning}"}
        })
        
        # Add sample errors
        if spike.sample_errors:
            error_text = "\n".join([f"> `{e.message[:80]}...`" for e in spike.sample_errors[:2]])
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Sample Errors:*\n{error_text}"}
            })

        return blocks

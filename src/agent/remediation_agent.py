from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from src.agent.correlation_engine import CorrelationEngine
from src.agent.error_monitor import ErrorMonitor
from src.agent.incident_reporter import IncidentReporter
from src.agent.safety import SafetyGuard
from src.config import AgentConfig
from src.mcp_server.posthog_client import PostHogClient
from src.mcp_server.tools import MCPTools
from src.models import (
    AuditEntry,
    CorrelationResult,
    FlagAction,
    RecommendedAction,
    RollbackAction,
    SpikeEvent,
)

logger = structlog.get_logger()


class RemediationAgent:
    """The autonomous reasoning loop for feature flag remediation."""

    def __init__(self, config: AgentConfig, client: Optional[PostHogClient] = None):
        self.config = config
        self.client = client or PostHogClient(config)
        self.safety = SafetyGuard(config)
        self.tools = MCPTools(self.client, config, self.safety)
        self.monitor = ErrorMonitor(
            baseline_window=config.baseline_window_seconds,
            spike_threshold_std=config.spike_threshold_std,
        )
        self.correlator = CorrelationEngine(
            auto_threshold=config.correlation_confidence_auto_threshold,
            alert_threshold=config.correlation_confidence_alert_threshold,
        )
        self.reporter = IncidentReporter()
        self.is_running = False

    async def run(self) -> None:
        """Start the continuous monitoring loop."""
        self.is_running = True
        logger.info("Agent loop started", poll_interval=self.config.poll_interval_seconds)

        async with self.client:
            while self.is_running:
                try:
                    await self._run_cycle()
                except Exception as e:
                    logger.error("Agent cycle failed", error=str(e))
                
                await asyncio.sleep(self.config.poll_interval_seconds)

    async def _run_cycle(self) -> None:
        """Execute a single phase of the remediation loop."""
        # 1. MONITOR - Fetch errors
        logger.debug("Phase 1: MONITOR - Fetching errors")
        errors = await self.client.get_errors(minutes=5)
        self.monitor.ingest(errors)

        # 2. DETECT - Check for spikes
        logger.debug("Phase 2: DETECT - Checking for spikes")
        spike = self.monitor.detect_spike()
        if not spike:
            return

        logger.warn(
            "Spike detected!",
            factor=f"{spike.spike_factor:.2f}x",
            services=spike.affected_services,
        )

        # 3. CORRELATE - Search for related flag changes
        logger.debug("Phase 3: CORRELATE - Searching for flag changes")
        flag_changes = await self.client.get_recent_flag_changes(within_minutes=120)
        correlation = self.correlator.correlate(spike, flag_changes)

        logger.info(
            "Correlation analysis complete",
            flag=correlation.correlated_flag.flag_key if correlation.correlated_flag else "None",
            confidence=f"{correlation.overall_confidence:.4f}",
            action=correlation.recommended_action.value,
        )

        # 4. DECIDE - Determine action
        logger.debug("Phase 4: DECIDE - Determining action")
        if correlation.recommended_action == RecommendedAction.AUTO_ROLLBACK:
            await self._handle_auto_rollback(spike, correlation)
        elif correlation.recommended_action == RecommendedAction.RECOMMEND_ROLLBACK:
            await self._handle_recommendation(spike, correlation)
        else:
            logger.info("Decision: Log and monitor (low confidence)")

    async def _handle_auto_rollback(self, spike: SpikeEvent, correlation: CorrelationResult) -> None:
        """Execute autonomous remediation."""
        flag_key = correlation.correlated_flag.flag_key
        logger.info("Decision: EXECUTE AUTO-ROLLBACK", flag=flag_key)

        rollback = RollbackAction(
            flag_key=flag_key,
            action=FlagAction.DISABLE,
            reason=f"Auto-rollback: {spike.spike_factor:.1f}x spike in {', '.join(spike.affected_services)}",
            confidence=correlation.overall_confidence,
        )

        # Safety Check
        safety_result = self.safety.can_execute(rollback)
        if not safety_result.allowed:
            logger.warn("Safety blocked auto-rollback", reasons=safety_result.reasons)
            summary = self.reporter.generate_summary(spike, correlation, "safety_blocked")
            summary.safety_details = safety_result
            await self.reporter.post_to_slack(summary, self.config.slack_webhook_url)
            return

        # ACT
        logger.info("Phase 5: ACT - Toggling flag", flag=flag_key)
        try:
            result = await self.tools.toggle_feature_flag(
                flag_key=flag_key,
                action="rollback",
                reason=rollback.reason,
            )
            
            # VERIFY
            logger.info("Phase 6: VERIFY - Monitoring for remediation")
            summary = self.reporter.generate_summary(spike, correlation, "auto_rollback")
            await asyncio.sleep(60) # Wait for propagation
            
            # Post-action verification
            verify_errors = await self.client.get_errors(minutes=2)
            self.monitor.ingest(verify_errors)
            new_spike = self.monitor.detect_spike()
            
            if not new_spike:
                logger.info("Remediation verified: Error rate normalized", flag=flag_key)
                summary.verification_status = "resolved"
            else:
                logger.error("Remediation failed: Errors persist after rollback", flag=flag_key)
                summary.verification_status = "escalated"

            await self.reporter.post_to_slack(summary, self.config.slack_webhook_url)

        except Exception as e:
            logger.error("Rollback execution failed", error=str(e))

    async def _handle_recommendation(self, spike: SpikeEvent, correlation: CorrelationResult) -> None:
        """Report a correlation that requires human intervention."""
        logger.info("Decision: RECOMMEND ROLLBACK (Human in loop)")
        summary = self.reporter.generate_summary(spike, correlation, "manual_recommendation")
        await self.reporter.post_to_slack(summary, self.config.slack_webhook_url)

    def stop(self) -> None:
        """Stop the loop gracefully."""
        self.is_running = False

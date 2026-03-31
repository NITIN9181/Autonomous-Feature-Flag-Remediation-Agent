from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, List

from src.config import AgentConfig
from src.mcp_server.posthog_client import PostHogClient
from src.models import (
    AuditEntry,
    FlagAction,
    FlagState,
    RecommendedAction,
    RollbackAction,
    Severity,
)


class MCPTools:
    """Implementation of MCP tools for PostHog flag remediation."""

    def __init__(self, client: PostHogClient, config: AgentConfig, safety: Any):
        self.client = client
        self.config = config
        self.safety = safety

    async def read_error_logs(
        self,
        time_window_minutes: int = 5,
        severity: str = "critical",
        service: str | None = None,
    ) -> List[dict[str, Any]]:
        """Fetch recent error log entries."""
        errors = await self.client.get_errors(
            minutes=time_window_minutes, severity=Severity(severity), service=service
        )
        return [e.model_dump(mode="json") for e in errors]

    async def check_flag_status(
        self,
        flag_key: str,
        include_variants: bool = True,
    ) -> dict[str, Any]:
        """Check flag status."""
        flag = await self.client.get_flag_status(flag_key)
        return flag.model_dump(mode="json")

    async def toggle_feature_flag(
        self,
        flag_key: str,
        action: str,
        reason: str,
        rollout_percentage: int | None = None,
    ) -> dict[str, Any]:
        """Perform flag toggle with safety checks."""
        # Map action string to enum
        try:
            flag_action = FlagAction(action.lower())
        except ValueError:
            return {"error": f"Invalid action: {action}. Use 'enable', 'disable', or 'rollback'."}

        # 1. Check current status
        current_flag = await self.client.get_flag_status(flag_key)

        # 2. Safety Check
        rollback = RollbackAction(
            flag_key=flag_key,
            action=flag_action,
            reason=reason,
            confidence=1.0,  # Manual call implies 100% confidence
        )
        safety_result = self.safety.can_execute(rollback)

        if not safety_result.allowed:
            # Audit the blocked action
            audit = AuditEntry(
                action=action,
                flag_key=flag_key,
                decision="blocked",
                confidence=1.0,
                reasoning="; ".join(safety_result.reasons),
                outcome="safety_blocked",
            )
            self.safety.record_audit(audit)
            return {
                "error": "Safety check failed",
                "reasons": safety_result.reasons,
                "overrides_needed": safety_result.overrides_needed,
                "audit_entry": audit.model_dump(mode="json"),
            }

        # 3. Execute
        new_state = await self.client.update_flag(
            flag_key=flag_key,
            enabled=(flag_action != FlagAction.DISABLE),
            rollout_percentage=rollout_percentage,
        )

        # 4. Audit result
        audit = AuditEntry(
            action=action,
            flag_key=flag_key,
            decision="executed",
            confidence=1.0,
            reasoning=f"Manual toggle: {reason}",
            outcome="success",
        )
        self.safety.record_audit(audit)

        return {
            "success": True,
            "flag_key": flag_key,
            "before": current_flag.model_dump(mode="json"),
            "after": new_state.model_dump(mode="json"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "audit_entry": audit.model_dump(mode="json"),
        }

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from src.config import AgentConfig
from src.models import AuditEntry, RollbackAction, SafetyDecision


class SafetyGuard:
    """Enforces safety boundaries for autonomous actions."""

    def __init__(self, config: AgentConfig):
        self.config = config
        # Audit trail of executed actions
        self.audit_trail: List[AuditEntry] = []
        
        # Rate limiting history (timestamps of auto-rollbacks)
        self.rollback_history: deque[datetime] = deque()

    def can_execute(self, proposal: RollbackAction) -> SafetyDecision:
        """Validate if a proposed action adheres to all safety rules."""
        reasons = []
        overrides = []

        # 1. Protected Flags
        if proposal.flag_key in self.config.protected_flags:
            reasons.append(f"Flag '{proposal.flag_key}' is in the PROTECTED list and cannot be auto-toggled.")
            overrides.append("remove_from_protected_list")

        # 2. Rate Limiting (Rollbacks per hour)
        self._prune_history()
        if len(self.rollback_history) >= self.config.max_auto_rollbacks_per_hour:
            reasons.append(f"Rate limit exceeded: {len(self.rollback_history)}/{self.config.max_auto_rollbacks_per_hour} rollbacks in the last hour.")
            overrides.append("increase_rate_limit")

        # 3. Cooldown Period
        if self.rollback_history:
            last_rollback = self.rollback_history[-1]
            time_since = (datetime.now(timezone.utc) - last_rollback).total_seconds()
            if time_since < self.config.cooldown_after_rollback_seconds:
                remaining = int(self.config.cooldown_after_rollback_seconds - time_since)
                reasons.append(f"Cooldown active: {remaining}s remaining after last rollback.")
                overrides.append("skip_cooldown")

        # 4. Confidence Threshold (Double Check)
        if proposal.confidence < self.config.correlation_confidence_auto_threshold:
            reasons.append(f"Confidence score {proposal.confidence:.4f} is below the automation threshold of {self.config.correlation_confidence_auto_threshold}.")
            overrides.append("lower_confidence_threshold")

        is_allowed = len(reasons) == 0
        return SafetyDecision(
            allowed=is_allowed,
            reasons=reasons,
            overrides_needed=overrides
        )

    def record_audit(self, entry: AuditEntry) -> None:
        """Persist an action or attempt to the audit trail."""
        self.audit_trail.append(entry)
        
        # If successfully executed a rollback, record for rate limiting
        if entry.action in ["rollback", "disable"] and entry.decision == "executed":
            self.rollback_history.append(entry.timestamp)

    def get_audit_trail(self) -> List[AuditEntry]:
        """Return the complete audit trail."""
        return self.audit_trail

    def _prune_history(self) -> None:
        """Clear rate limit history entries older than 1 hour."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        while self.rollback_history and self.rollback_history[0] < cutoff:
            self.rollback_history.popleft()

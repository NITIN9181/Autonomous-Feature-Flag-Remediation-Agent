from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class ErrorLog(BaseModel):
    """Represents a single error event from the stream."""

    timestamp: datetime
    message: str
    stack_trace: str
    service: str
    severity: Severity = Severity.CRITICAL
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    # Context injected by PostHog feature flags
    flag_variants: Dict[str, str] = Field(default_factory=dict)

    def to_summary(self) -> str:
        return f"[{self.timestamp.isoformat()}] {self.service}: {self.message}"


class FlagState(BaseModel):
    """Represents the status of a PostHog feature flag."""

    flag_key: str
    flag_id: int
    enabled: bool
    rollout_percentage: int
    deployment_timestamp: Optional[datetime] = None
    variants: List[Dict[str, Any]] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class SpikeEvent(BaseModel):
    """Anomalous error rate detection."""

    onset_timestamp: datetime
    baseline_rate: float  # errors per bucket
    current_rate: float
    spike_factor: float  # current / baseline
    affected_services: List[str]
    sample_errors: List[ErrorLog]


class CorrelationResult(BaseModel):
    """Result of correlating a spike with flag changes."""

    spike: SpikeEvent
    correlated_flag: Optional[FlagState] = None
    overall_confidence: float = 0.0
    signals: Dict[str, float] = Field(default_factory=dict)
    reasoning_chain: List[str] = Field(default_factory=list)
    recommended_action: "RecommendedAction"


class RecommendedAction(str, Enum):
    AUTO_ROLLBACK = "auto_rollback"
    RECOMMEND_ROLLBACK = "recommend_rollback"
    LOG_AND_MONITOR = "log_and_monitor"


class FlagAction(str, Enum):
    ENABLE = "enable"
    DISABLE = "disable"
    ROLLBACK = "rollback"


class RollbackAction(BaseModel):
    """Proposed remediation action."""

    flag_key: str
    action: FlagAction
    reason: str
    confidence: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SafetyDecision(BaseModel):
    """Outcome of the SafetyGuard validation."""

    allowed: bool
    reasons: List[str] = Field(default_factory=list)
    overrides_needed: List[str] = Field(default_factory=list)


class AuditEntry(BaseModel):
    """Permanent record of agent actions."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action: str
    flag_key: str
    decision: str  # e.g., "executed", "blocked", "deferred"
    confidence: float
    reasoning: str
    outcome: str  # e.g., "success", "failure", "safety_blocked"


class IncidentSummary(BaseModel):
    """Final report object for Slack/Logging."""

    incident_id: str
    status: str = "detected"  # detected, active, remediated, escalated
    spike: SpikeEvent
    correlation: CorrelationResult
    remediation_plan: str
    safety_details: Optional[SafetyDecision] = None
    verification_status: Optional[str] = None

    def to_slack_blocks(self) -> List[Dict[str, Any]]:
        """Generates Slack Block Kit UI components."""
        # Implementation in incident_reporter.py
        return []

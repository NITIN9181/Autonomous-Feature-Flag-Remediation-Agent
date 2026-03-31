from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from src.models import ErrorLog, FlagState, Severity


class PostHogMock:
    """In-memory PostHog API mock for development/demos."""

    def __init__(self):
        self.flags: Dict[str, FlagState] = {
            "stable-feature": FlagState(
                flag_key="stable-feature",
                flag_id=1,
                enabled=True,
                rollout_percentage=100,
                deployment_timestamp=datetime.now(timezone.utc) - timedelta(days=7),
            )
        }
        self.errors: List[ErrorLog] = []

    def create_flag(self, key: str, enabled: bool = True, rollout_percentage: int = 100) -> FlagState:
        flag = FlagState(
            flag_key=key,
            flag_id=len(self.flags) + 1,
            enabled=enabled,
            rollout_percentage=rollout_percentage,
            deployment_timestamp=datetime.now(timezone.utc),
        )
        self.flags[key] = flag
        return flag

    def get_flag(self, key: str) -> FlagState:
        if key not in self.flags:
            raise Exception(f"Feature flag '{key}' not found.")
        return self.flags[key]

    def update_flag(self, key: str, enabled: bool, rollout: Optional[int] = None) -> FlagState:
        if key not in self.flags:
            raise Exception(f"Feature flag '{key}' not found.")
        
        flag = self.flags[key]
        flag.enabled = enabled
        if rollout is not None:
            flag.rollout_percentage = rollout
        return flag

    def get_recent_changes(self, minutes: int) -> List[FlagState]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return [f for f in self.flags.values() if f.deployment_timestamp and f.deployment_timestamp >= cutoff]

    def record_errors(self, errors: List[ErrorLog]) -> None:
        self.errors.extend(errors)
        # Prune to keep 1 hour
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        self.errors = [e for e in self.errors if e.timestamp >= cutoff]

    def get_recent_errors(self, minutes: int, severity: Severity, service: Optional[str]) -> List[ErrorLog]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        filtered = [e for e in self.errors if e.timestamp >= cutoff and e.severity == severity]
        if service:
            filtered = [e for e in filtered if e.service == service]
        return filtered

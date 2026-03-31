from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

import httpx
import structlog
from src.config import AgentConfig
from src.models import ErrorLog, FlagState, Severity

logger = structlog.get_logger()


class PostHogClient:
    """Async client for PostHog API with simulator fallback."""

    def __init__(self, config: AgentConfig, mock: Optional[Any] = None):
        self.config = config
        self.mock = mock
        self.client = httpx.AsyncClient(
            base_url=config.posthog_host,
            headers={"Authorization": f"Bearer {config.posthog_api_key}"},
            timeout=10.0,
        )

    async def __aenter__(self) -> PostHogClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.client.aclose()

    async def get_errors(
        self,
        minutes: int = 5,
        severity: Severity = Severity.CRITICAL,
        service: Optional[str] = None,
    ) -> List[ErrorLog]:
        """Fetch error logs from PostHog events."""
        if self.config.use_simulator and self.mock:
            return self.mock.get_recent_errors(minutes, severity, service)

        # Real PostHog API Query (HogQL)
        query = {
            "query": f"""
            SELECT timestamp, properties.$message, properties.$stack_trace, properties.$service, properties.$severity, distinct_id, properties.$session_id, properties.$feature_variants
            FROM events
            WHERE event = '$exception'
              AND timestamp >= now() - INTERVAL {minutes} MINUTE
              AND properties.$severity = '{severity.value}'
              {f"AND properties.$service = '{service}'" if service else ""}
            ORDER BY timestamp DESC
            LIMIT 1000
            """
        }

        try:
            resp = await self.client.post(
                f"/api/projects/{self.config.posthog_project_id}/query/",
                json=query,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            return [
                ErrorLog(
                    timestamp=r[0],
                    message=r[1],
                    stack_trace=r[2],
                    service=r[3],
                    severity=Severity(r[4]),
                    user_id=r[5],
                    session_id=r[6],
                    flag_variants=json.loads(r[7]) if isinstance(r[7], str) else r[7],
                )
                for r in results
            ]
        except Exception as e:
            logger.error("Failed to fetch errors from PostHog", error=str(e))
            return []

    async def get_flag_status(self, flag_key: str) -> FlagState:
        """Fetch current state of a feature flag."""
        if self.config.use_simulator and self.mock:
            return self.mock.get_flag(flag_key)

        try:
            resp = await self.client.get(
                f"/api/projects/{self.config.posthog_project_id}/feature_flags/{flag_key}/"
            )
            resp.raise_for_status()
            data = resp.json()
            return FlagState(
                flag_key=data["key"],
                flag_id=data["id"],
                enabled=data["active"],
                rollout_percentage=data.get("rollout_percentage", 100),
                deployment_timestamp=datetime.fromisoformat(data["created_at"]),
                variants=data.get("filters", {}).get("multivariate", {}).get("variants", []),
                tags=data.get("tags", []),
            )
        except Exception as e:
            logger.error("Failed to fetch flag status", flag=flag_key, error=str(e))
            raise

    async def get_recent_flag_changes(self, within_minutes: int = 120) -> List[FlagState]:
        """Fetch flags modified recently."""
        if self.config.use_simulator and self.mock:
            return self.mock.get_recent_changes(within_minutes)

        # Real API Implementation
        try:
            resp = await self.client.get(
                f"/api/projects/{self.config.posthog_project_id}/feature_flags/?order=-updated_at"
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=within_minutes)
            flags = []
            for d in results:
                updated_at = datetime.fromisoformat(d["updated_at"])
                if updated_at >= cutoff:
                    flags.append(
                        FlagState(
                            flag_key=d["key"],
                            flag_id=d["id"],
                            enabled=d["active"],
                            rollout_percentage=d.get("rollout_percentage", 100),
                            deployment_timestamp=updated_at,
                        )
                    )
            return flags
        except Exception as e:
            logger.error("Failed to fetch recent flag changes", error=str(e))
            return []

    async def update_flag(
        self,
        flag_key: str,
        enabled: bool,
        rollout_percentage: Optional[int] = None,
    ) -> FlagState:
        """Update flag state (disable/enable)."""
        if self.config.use_simulator and self.mock:
            return self.mock.update_flag(flag_key, enabled, rollout_percentage)

        payload: dict[str, Any] = {"active": enabled}
        if rollout_percentage is not None:
            payload["rollout_percentage"] = rollout_percentage

        try:
            resp = await self.client.patch(
                f"/api/projects/{self.config.posthog_project_id}/feature_flags/{flag_key}/",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return FlagState(
                flag_key=data["key"],
                flag_id=data["id"],
                enabled=data["active"],
                rollout_percentage=data.get("rollout_percentage", 100),
                deployment_timestamp=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.error("Failed to update flag", flag=flag_key, error=str(e))
            raise

    # Help methods for simulator Setup
    async def create_flag(
        self, key: str, enabled: bool = True, rollout_percentage: int = 100
    ) -> FlagState:
        """Create a flag (mainly for testing/simulator)."""
        if self.config.use_simulator and self.mock:
            return self.mock.create_flag(key, enabled, rollout_percentage)
        
        # Real API implementation omitted for brevity as mainly used for simulator
        raise NotImplementedError("create_flag not implemented for production PostHog API")

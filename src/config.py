from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentConfig(BaseSettings):
    """Configuration for the PostHog Flag Agent."""

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        extra="ignore",
    )

    # PostHog API
    posthog_api_key: str = ""
    posthog_host: str = "https://app.posthog.com"
    posthog_project_id: int = 1

    # Agent Loop
    poll_interval_seconds: int = 30
    baseline_window_seconds: int = 3600
    spike_threshold_std: float = 3.0

    # Correlation
    correlation_confidence_auto_threshold: float = 0.85
    correlation_confidence_alert_threshold: float = 0.60

    # Safety
    max_auto_rollbacks_per_hour: int = 2
    cooldown_after_rollback_seconds: int = 300
    protected_flags: List[str] = Field(default_factory=list)

    # Notifications
    slack_webhook_url: str = ""

    # Simulator
    use_simulator: bool = True
    simulation_speed: float = 1.0

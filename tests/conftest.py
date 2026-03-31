import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

import pytest
import pytest_asyncio
from src.config import AgentConfig
from src.mcp_server.posthog_client import PostHogClient
from src.models import ErrorLog, FlagState, Severity
from src.simulator.posthog_mock import PostHogMock


@pytest.fixture
def config():
    return AgentConfig(
        use_simulator=True,
        posthog_api_key="test-key",
        posthog_project_id=1,
        protected_flags=["protected-flag"],
        max_auto_rollbacks_per_hour=2,
        cooldown_after_rollback_seconds=300,
    )


@pytest.fixture
def mock_posthog():
    return PostHogMock()


@pytest_asyncio.fixture
async def client(config, mock_posthog):
    async with PostHogClient(config, mock=mock_posthog) as c:
        yield c


def create_error(
    service="test-service",
    message="test-error",
    timestamp=None,
    variants=None,
) -> ErrorLog:
    return ErrorLog(
        timestamp=timestamp or datetime.now(timezone.utc),
        message=message,
        stack_trace="traceback",
        service=service,
        severity=Severity.CRITICAL,
        flag_variants=variants or {},
    )


@pytest.fixture
def sample_errors():
    now = datetime.now(timezone.utc)
    return [
        create_error(timestamp=now - timedelta(seconds=i))
        for i in range(10)
    ]

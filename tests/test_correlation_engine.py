from datetime import datetime, timedelta, timezone

import pytest
from src.agent.correlation_engine import CorrelationEngine
from src.models import FlagState, RecommendedAction, SpikeEvent
from tests.conftest import create_error


@pytest.fixture
def correlator():
    return CorrelationEngine(auto_threshold=0.8, alert_threshold=0.5)


def test_correlate_temporal_only(correlator):
    now = datetime.now(timezone.utc)
    spike = SpikeEvent(
        onset_timestamp=now,
        baseline_rate=5.0,
        current_rate=25.0,
        spike_factor=5.0,
        affected_services=["api"],
        sample_errors=[create_error(timestamp=now) for _ in range(5)],
    )

    # Flag changed 5 mins before spike
    flag = FlagState(
        flag_key="new-feature",
        flag_id=1,
        enabled=True,
        rollout_percentage=100,
        deployment_timestamp=now - timedelta(minutes=5),
    )

    result = correlator.correlate(spike, [flag])
    
    assert result.correlated_flag.flag_key == "new-feature"
    # Expected confidence: 0.9 (temp) * 0.4 + 0.0 (content) * 0.35 + 0.3 (variant) * 0.25 = 0.36 + 0.0 + 0.075 = 0.435
    assert 0.4 < result.overall_confidence < 0.5
    assert result.recommended_action == RecommendedAction.LOG_AND_MONITOR


def test_correlate_full_match(correlator):
    now = datetime.now(timezone.utc)
    
    # Errors contain flag name in stack trace and have variant metadata
    errors = [
        create_error(
            message="Error in 'new-ui' module",
            variants={"new-ui": "treatment"}
        ) for _ in range(5)
    ]
    
    spike = SpikeEvent(
        onset_timestamp=now,
        baseline_rate=5.0,
        current_rate=25.0,
        spike_factor=5.0,
        affected_services=["api"],
        sample_errors=errors,
    )

    flag = FlagState(
        flag_key="new-ui",
        flag_id=1,
        enabled=True,
        rollout_percentage=100,
        deployment_timestamp=now - timedelta(minutes=2),
    )

    result = correlator.correlate(spike, [flag])
    
    assert result.overall_confidence > 0.85
    assert result.recommended_action == RecommendedAction.AUTO_ROLLBACK

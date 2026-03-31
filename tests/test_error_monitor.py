from datetime import datetime, timedelta, timezone

import pytest
from src.agent.error_monitor import ErrorMonitor
from tests.conftest import create_error


def test_baseline_calculation():
    monitor = ErrorMonitor(bucket_seconds=10)
    now = datetime.now(timezone.utc)
    
    # 5 buckets of normal traffic (5 errors/bucket)
    for i in range(5):
        ts = now - timedelta(seconds=60 - (i * 10))
        monitor.ingest([create_error(timestamp=ts) for _ in range(5)])
        
    assert monitor.get_baseline() == 5.0
    assert monitor.get_std_dev() == 0.0


def test_spike_detection():
    monitor = ErrorMonitor(bucket_seconds=60, spike_threshold_std=2.0)
    now = datetime.now(timezone.utc)
    
    # Establish baseline with some variance
    # Buckets: 4, 6, 4, 6, 5 -> Mean: 5.0, Std: ~0.89
    for count in [4, 6, 4, 6, 5]:
        ts = now - timedelta(minutes=10) # Past buckets
        monitor.history.append((ts, count))
        now += timedelta(minutes=1)

    # Current bucket: 15 errors (Z-score: (15-5)/0.89 = 11.2)
    current_errors = [create_error(timestamp=now) for _ in range(15)]
    monitor.ingest(current_errors)
    
    spike = monitor.detect_spike()
    assert spike is not None
    assert spike.current_rate == 15
    assert spike.spike_factor == 3.0
    assert "test-service" in spike.affected_services

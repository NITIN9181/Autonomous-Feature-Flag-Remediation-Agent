from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from src.models import ErrorLog, Severity


class ErrorStreamSimulator:
    """Generates continuous streams of simulated error events."""

    MESSAGES = [
        ("TypeError: Cannot read property 'id' of undefined", "checkout-service"),
        ("OSError: [Errno 28] No space left on device", "storage-service"),
        ("ConnectionTimeout: Failed to connect to redis:6379", "cache-service"),
        ("AttributeError: 'NoneType' object has no attribute 'items'", "api-gateway"),
        ("FastAPI.InternalError: Exception in background task", "worker-service"),
    ]

    STACK_TRACES = [
        "File 'features/checkout/new_flow.py', line 134, in get_checkout_items",
        "File 'core/storage/s3_client.py', line 452, in upload_file",
        "File 'api/auth/jwt_manager.py', line 89, in validate_token",
    ]

    def __init__(self, base_rate: int = 5, simulation_speed: float = 1.0):
        self.base_rate = base_rate
        self.simulation_speed = simulation_speed
        self.last_poll_time: Optional[datetime] = None
        
        # Scenario State
        self.active_spike: Optional[str] = None # Flag key causing the spike
        self.spike_factor: float = 1.0

    def trigger_spike(self, flag_key: str, multiplier: float = 5.0) -> None:
        """Trigger an error spike correlated with a specific flag."""
        self.active_spike = flag_key
        self.spike_factor = multiplier

    def stop_spike(self) -> None:
        """Return to background error rate."""
        self.active_spike = None
        self.spike_factor = 1.0

    def generate_batch(self, interval_seconds: int = 30) -> List[ErrorLog]:
        """Generate a bucket of errors based on current rate/scenarios."""
        now = datetime.now(timezone.utc)
        
        # Calculate count
        count = int(self.base_rate * self.simulation_speed * self.spike_factor)
        # Add some Poisson-like jitter
        count = max(0, count + random.randint(-2, 2))
        
        errors = []
        for _ in range(count):
            msg, service = random.choice(self.MESSAGES)
            stack = random.choice(self.STACK_TRACES)
            
            # Inject flag metadata if spike is active
            flag_variants = {}
            if self.active_spike:
                # 80/20 skew towards treatment in a spike
                variant = "treatment" if random.random() > 0.2 else "control"
                flag_variants[self.active_spike] = variant
                
                # Also inject flag name into stack trace to simulate content correlation
                stack = f"File 'features/flags/{self.active_spike}.py', line 42, in process\n{stack}"

            errors.append(
                ErrorLog(
                    timestamp=now - timedelta(seconds=random.randint(0, interval_seconds)),
                    message=msg,
                    stack_trace=stack,
                    service=service,
                    severity=Severity.CRITICAL,
                    user_id=f"user-{random.randint(1000, 9999)}",
                    session_id=f"sess-{random.getrandbits(32):x}",
                    flag_variants=flag_variants,
                )
            )
        
        return errors

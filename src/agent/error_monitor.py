from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
from src.models import ErrorLog, SpikeEvent


class ErrorMonitor:
    """Detects spikes in error streams using statistical analysis."""

    def __init__(
        self,
        baseline_window: int = 3600,
        spike_threshold_std: float = 3.0,
        bucket_seconds: int = 30,
    ):
        self.baseline_window = baseline_window
        self.spike_threshold_std = spike_threshold_std
        self.bucket_seconds = bucket_seconds

        # Deque of (timestamp, error_count)
        self.history: deque[tuple[datetime, int]] = deque()
        self.current_bucket_errors: List[ErrorLog] = []
        self.current_bucket_start: Optional[datetime] = None

    def ingest(self, errors: List[ErrorLog]) -> None:
        """Organize incoming errors into time buckets."""
        if not errors:
            return

        sorted_errors = sorted(errors, key=lambda e: e.timestamp)
        
        for error in sorted_errors:
            if self.current_bucket_start is None:
                self.current_bucket_start = error.timestamp
            
            # If error is beyond current bucket duration
            if (error.timestamp - self.current_bucket_start).total_seconds() > self.bucket_seconds:
                # Flush bucket
                self.history.append((self.current_bucket_start, len(self.current_bucket_errors)))
                self._prune_history()
                
                # Start new bucket
                self.current_bucket_start = error.timestamp
                self.current_bucket_errors = [error]
            else:
                self.current_bucket_errors.append(error)

    def _prune_history(self) -> None:
        """Keep only history within the baseline window."""
        if not self.history:
            return
        
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.baseline_window)
        while self.history and self.history[0][0] < cutoff:
            self.history.popleft()

    def get_baseline(self) -> float:
        """Calculate the rolling mean of error counts per bucket."""
        if len(self.history) < 3:
            return 0.0
        return float(np.mean([count for _, count in self.history]))

    def get_std_dev(self) -> float:
        """Calculate the standard deviation of error counts."""
        if len(self.history) < 3:
            return 0.0
        return float(np.std([count for _, count in self.history]))

    def detect_spike(self) -> Optional[SpikeEvent]:
        """Detect if the current bucket represents an anomalous spike."""
        if not self.current_bucket_errors or len(self.history) < 5:
            return None

        current_count = len(self.current_bucket_errors)
        mean = self.get_baseline()
        std = self.get_std_dev()

        # If std is 0 (all buckets same), handle it
        if std == 0:
            std = 0.5 # Minimal jitter

        z_score = (current_count - mean) / std
        
        if z_score >= self.spike_threshold_std:
            # Aggregate affected services
            services = list(set(e.service for e in self.current_bucket_errors))
            
            return SpikeEvent(
                onset_timestamp=self.current_bucket_start or datetime.now(timezone.utc),
                baseline_rate=mean,
                current_rate=current_count,
                spike_factor=current_count / mean if mean > 0 else float(current_count),
                affected_services=services,
                sample_errors=self.current_bucket_errors[:5],
            )
        
        return None


from datetime import timedelta

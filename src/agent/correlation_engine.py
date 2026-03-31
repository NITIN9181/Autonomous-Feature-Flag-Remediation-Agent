from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.models import (
    CorrelationResult,
    ErrorLog,
    FlagState,
    RecommendedAction,
    SpikeEvent,
)


class CorrelationEngine:
    """Calculates confidence scores for flag->spike correlation."""

    def __init__(self, auto_threshold: float = 0.85, alert_threshold: float = 0.60):
        self.auto_threshold = auto_threshold
        self.alert_threshold = alert_threshold

    def correlate(
        self, spike: SpikeEvent, recent_flags: List[FlagState]
    ) -> CorrelationResult:
        """Evaluate relationship between an error spike and recent flag changes."""
        if not recent_flags:
            return CorrelationResult(
                spike=spike,
                overall_confidence=0.0,
                recommended_action=RecommendedAction.LOG_AND_MONITOR,
                reasoning_chain=["No recent flag changes found — cannot correlate."],
            )

        candidates: List[Tuple[FlagState, float, Dict[str, float], List[str]]] = []

        for flag in recent_flags:
            signals, reasoning = self._calculate_signals(spike, flag)
            
            # Weighted average
            # Temporal (0.4) + Content (0.35) + Variant (0.25)
            confidence = (
                signals["temporal"] * 0.40 +
                signals["content"] * 0.35 +
                signals["variant"] * 0.25
            )
            
            candidates.append((flag, confidence, signals, reasoning))

        # Sort by confidence descending
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_flag, best_conf, best_signals, best_reasoning = candidates[0]

        # Determine recommendation
        if best_conf >= self.auto_threshold:
            action = RecommendedAction.AUTO_ROLLBACK
        elif best_conf >= self.alert_threshold:
            action = RecommendedAction.RECOMMEND_ROLLBACK
        else:
            action = RecommendedAction.LOG_AND_MONITOR

        return CorrelationResult(
            spike=spike,
            correlated_flag=best_flag,
            overall_confidence=best_conf,
            signals=best_signals,
            reasoning_chain=best_reasoning,
            recommended_action=action,
        )

    def _calculate_signals(
        self, spike: SpikeEvent, flag: FlagState
    ) -> Tuple[Dict[str, float], List[str]]:
        """Calculate individual correlation signals (0.0 to 1.0)."""
        signals = {}
        reasoning = []

        # 1. Temporal Signal (Time delta)
        # Higher score if flag changed just before spike onset
        time_diff = (spike.onset_timestamp - flag.deployment_timestamp).total_seconds()
        
        if -60 < time_diff < 3600: # Changed within last hour
            # Decay score based on time
            # 0-5 mins: 1.0, 1 hour: 0.3
            temp_score = max(0.3, 1.0 - (max(0, time_diff - 300) / 4000))
            signals["temporal"] = temp_score
            reasoning.append(f"Temporal: flag '{flag.flag_key}' changed {time_diff/60:.1f} min before spike → score {temp_score:.2f}")
        elif time_diff < -60: # Spike happened BEFORE flag change
            signals["temporal"] = 0.0
            reasoning.append(f"Temporal: flag '{flag.flag_key}' changed AFTER spike onset → score 0.0")
        else:
            signals["temporal"] = 0.1
            reasoning.append(f"Temporal: flag '{flag.flag_key}' change too old → score 0.1")

        # 2. Content Signal (Keyword matching in stack traces)
        # Does the flag name appear (or segments of it) in the error logs?
        keywords = set(re.findall(r'[a-zA-Z]+', flag.flag_key.replace("-", " ").replace("_", " ")))
        matches = 0
        total_logs = len(spike.sample_errors)
        
        for error in spike.sample_errors:
            text = (error.message + error.stack_trace).lower()
            if any(kw.lower() in text for kw in keywords if len(kw) > 3):
                matches += 1
        
        content_score = (matches / total_logs) if total_logs > 0 else 0.0
        signals["content"] = content_score
        reasoning.append(f"Content: stack-trace keyword match for '{flag.flag_key}' in {matches}/{total_logs} errors → score {content_score:.2f}")

        # 3. Variant Signal (Skew analysis)
        # Are most errors coming from the 'treatment' group vs 'control'?
        # This requires flag metadata to be present on the ErrorLog
        treatment_count = 0
        control_count = 0
        v_matches = 0
        
        for error in spike.sample_errors:
            variant = error.flag_variants.get(flag.flag_key)
            if variant:
                v_matches += 1
                if variant != "control":
                    treatment_count += 1
                else:
                    control_count += 1
                    
        if v_matches > 0:
            # If 100% treatment coverage, score 1.0. If 50/50, score 0.5.
            variant_score = treatment_count / v_matches
            signals["variant"] = variant_score
            reasoning.append(f"Variant: error skew in '{flag.flag_key}' treatment group: {treatment_count}/{v_matches} → score {variant_score:.2f}")
        else:
            signals["variant"] = 0.3 # Neutral baseline if no tag metadata
            reasoning.append(f"Variant: no specific variant metadata on errors for '{flag.flag_key}' → score 0.30")

        return signals, reasoning

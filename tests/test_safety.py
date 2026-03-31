from datetime import datetime, timezone

import pytest
from src.agent.safety import SafetyGuard
from src.models import AuditEntry, FlagAction, RollbackAction


def test_protected_flag_block(config):
    guard = SafetyGuard(config)
    action = RollbackAction(
        flag_key="protected-flag",
        action=FlagAction.DISABLE,
        reason="Testing",
        confidence=1.0,
    )
    
    decision = guard.can_execute(action)
    assert decision.allowed is False
    assert "PROTECTED" in decision.reasons[0]


def test_rate_limit_block(config):
    guard = SafetyGuard(config)
    now = datetime.now(timezone.utc)
    
    # Fill rate limit (2 per hour)
    for i in range(2):
        guard.record_audit(AuditEntry(
            timestamp=now,
            action="rollback",
            flag_key=f"flag-{i}",
            decision="executed",
            confidence=1.0,
            reasoning="test",
            outcome="success",
        ))
        
    action = RollbackAction(
        flag_key="third-flag",
        action=FlagAction.DISABLE,
        reason="Testing",
        confidence=1.0,
    )
    
    decision = guard.can_execute(action)
    assert decision.allowed is False
    assert "Rate limit exceeded" in decision.reasons[0]


def test_cooldown_block(config):
    guard = SafetyGuard(config)
    now = datetime.now(timezone.utc)
    
    # Just performed a rollback
    guard.record_audit(AuditEntry(
        timestamp=now - timedelta(seconds=10),
        action="rollback",
        flag_key="flag-1",
        decision="executed",
        confidence=1.0,
        reasoning="test",
        outcome="success",
    ))
    
    action = RollbackAction(
        flag_key="flag-2",
        action=FlagAction.DISABLE,
        reason="Testing",
        confidence=1.0,
    )
    
    decision = guard.can_execute(action)
    assert decision.allowed is False
    assert "Cooldown active" in decision.reasons[0]


from datetime import timedelta

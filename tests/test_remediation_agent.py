import pytest
from src.agent.remediation_agent import RemediationAgent


@pytest.mark.asyncio
async def test_agent_cycle_no_spike(config, client, mock_posthog):
    agent = RemediationAgent(config, client=client)
    
    # No errors -> no spike
    await agent._run_cycle()
    
    assert len(agent.safety.get_audit_trail()) == 0


@pytest.mark.asyncio
async def test_agent_cycle_auto_rollback(config, client, mock_posthog):
    # 1. Establish baseline
    agent = RemediationAgent(config, client=client)
    
    # Inject baseline history directly to speed up test
    for _ in range(5):
        agent.monitor.history.append((datetime.now(), 5))
        
    # 2. Trigger correlation match
    mock_posthog.create_flag("bad-flag", enabled=True)
    
    # Inject a spike of errors that match the flag
    errors = []
    for _ in range(20):
        errors.append(ErrorLog(
            timestamp=datetime.now(),
            message="Error in bad-flag",
            stack_trace="trace",
            service="api",
            flag_variants={"bad-flag": "treatment"}
        ))
    
    mock_posthog.record_errors(errors)
    
    # 3. Run cycle
    await agent._run_cycle()
    
    # Should have triggered rollback
    assert mock_posthog.get_flag("bad-flag").enabled is False
    assert len(agent.safety.get_audit_trail()) == 1


from datetime import datetime

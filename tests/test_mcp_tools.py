import pytest
from src.agent.safety import SafetyGuard
from src.mcp_server.tools import MCPTools
from src.models import FlagAction, RollbackAction


@pytest.mark.asyncio
async def test_read_error_logs(client, mock_posthog, sample_errors):
    mock_posthog.record_errors(sample_errors)
    tools = MCPTools(client, None, None)
    
    results = await tools.read_error_logs(time_window_minutes=5)
    assert len(results) == 10
    assert results[0]["service"] == "test-service"


@pytest.mark.asyncio
async def test_toggle_feature_flag_success(client, mock_posthog, config):
    mock_posthog.create_flag("test-flag", enabled=True)
    safety = SafetyGuard(config)
    tools = MCPTools(client, config, safety)
    
    result = await tools.toggle_feature_flag(
        flag_key="test-flag",
        action="disable",
        reason="Testing",
    )
    
    assert result["success"] is True
    assert result["after"]["enabled"] is False
    assert len(safety.get_audit_trail()) == 1


@pytest.mark.asyncio
async def test_toggle_feature_flag_safety_blocked(client, mock_posthog, config):
    # Flag is in protected list
    mock_posthog.create_flag("protected-flag", enabled=True)
    safety = SafetyGuard(config)
    tools = MCPTools(client, config, safety)
    
    result = await tools.toggle_feature_flag(
        flag_key="protected-flag",
        action="disable",
        reason="Testing",
    )
    
    assert "error" in result
    assert "Safety check failed" in result["error"]
    assert result["after"] is None # Action wasn't executed

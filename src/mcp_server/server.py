from __future__ import annotations

import asyncio
import sys
from typing import Any, List

from mcp.server.fastmcp import FastMCP
from mcp.server.stdio import stdio_server

from src.config import AgentConfig
from src.mcp_server.posthog_client import PostHogClient
from src.mcp_server.tools import MCPTools

# Create FastMCP server
mcp = FastMCP("posthog-flag-agent")

# Dependencies (will be initialized on startup)
_tools: MCPTools | None = None


@mcp.tool()
async def read_error_logs(
    time_window_minutes: int = 5,
    severity: str = "critical",
    service: str | None = None,
) -> List[dict[str, Any]]:
    """Fetch recent error log entries from the monitored error stream."""
    global _tools
    if not _tools:
        await _initialize()
    return await _tools.read_error_logs(time_window_minutes, severity, service)


@mcp.tool()
async def check_flag_status(
    flag_key: str,
    include_variants: bool = True,
) -> dict[str, Any]:
    """Query the current state of a PostHog feature flag."""
    global _tools
    if not _tools:
        await _initialize()
    return await _tools.check_flag_status(flag_key, include_variants)


@mcp.tool()
async def toggle_feature_flag(
    flag_key: str,
    action: str,
    reason: str,
    rollout_percentage: int | None = None,
) -> dict[str, Any]:
    """
    Enable, disable, or rollback a feature flag with safety checks.

    action: 'enable', 'disable', or 'rollback'
    """
    global _tools
    if not _tools:
        await _initialize()
    return await _tools.toggle_feature_flag(flag_key, action, reason, rollout_percentage)


async def _initialize() -> None:
    """Lazy initialize dependencies."""
    global _tools
    config = AgentConfig()
    client = PostHogClient(config)
    from src.agent.safety import SafetyGuard
    safety = SafetyGuard(config)
    _tools = MCPTools(client, config, safety)


async def serve_stdio() -> None:
    """Run the FastMCP server using stdio transport."""
    await mcp.run_stdio_async()


def main() -> None:
    """Entrypoint for the MCP server."""
    asyncio.run(serve_stdio())


if __name__ == "__main__":
    main()

# MCP Specification — Tool Schemas & Client Integration

This document provides the full Model Context Protocol specification for the PostHog Feature Flag Remediation Agent, including tool schemas, example requests/responses, and integration instructions.

## Server Info

| Field | Value |
|-------|-------|
| Name | PostHog Feature Flag Remediation Agent |
| Version | 0.1.0 |
| Transport | stdio (default), SSE (optional) |
| SDK | `mcp` Python SDK (FastMCP high-level API) |

---

## Tool 1: `read_error_logs`

Fetch recent error log entries from the monitored error stream.

### JSON Schema

```json
{
  "name": "read_error_logs",
  "description": "Fetch recent error log entries from the monitored error stream.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "time_window_minutes": {
        "type": "integer",
        "default": 5,
        "description": "How many minutes of history to fetch."
      },
      "severity": {
        "type": "string",
        "default": "critical",
        "enum": ["critical", "warning", "info"],
        "description": "Filter by severity level."
      },
      "service": {
        "type": ["string", "null"],
        "default": null,
        "description": "Optional service name filter."
      }
    }
  }
}
```

### Example Response

```json
[
  {
    "timestamp": "2026-03-31T10:15:32Z",
    "message": "TypeError: Cannot read property 'items' of undefined in checkout flow",
    "stack_trace": "File features/checkout/new_flow.py, line 134...",
    "service": "checkout-service",
    "severity": "critical",
    "user_id": "user-4821",
    "session_id": "sess-a1b2",
    "flag_variants": {"new-checkout-flow": "treatment"}
  }
]
```

---

## Tool 2: `check_flag_status`

Query the current state of a PostHog feature flag.

### JSON Schema

```json
{
  "name": "check_flag_status",
  "description": "Query the current state of a PostHog feature flag.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "flag_key": {
        "type": "string",
        "description": "The unique key of the feature flag."
      },
      "include_variants": {
        "type": "boolean",
        "default": true,
        "description": "Whether to include variant details."
      }
    },
    "required": ["flag_key"]
  }
}
```

### Example Response

```json
{
  "flag_key": "new-checkout-flow",
  "flag_id": 42,
  "enabled": true,
  "rollout_percentage": 100,
  "variants": [
    {"key": "control", "rollout_percentage": 50},
    {"key": "treatment", "rollout_percentage": 50}
  ],
  "deployment_timestamp": "2026-03-31T10:00:00Z",
  "experiment_info": {"experiment_set": []}
}
```

---

## Tool 3: `toggle_feature_flag`

Enable, disable, or rollback a feature flag with safety checks and audit trail.

### JSON Schema

```json
{
  "name": "toggle_feature_flag",
  "description": "Enable, disable, or rollback a feature flag with safety checks.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "flag_key": {
        "type": "string",
        "description": "The unique key of the feature flag."
      },
      "action": {
        "type": "string",
        "enum": ["enable", "disable", "rollback"],
        "description": "Action to perform."
      },
      "reason": {
        "type": "string",
        "description": "Human-readable reason for the change."
      },
      "rollout_percentage": {
        "type": ["integer", "null"],
        "default": null,
        "description": "Optional new rollout percentage."
      }
    },
    "required": ["flag_key", "action", "reason"]
  }
}
```

### Example Response (Success)

```json
{
  "success": true,
  "flag_key": "new-checkout-flow",
  "before": {"enabled": true, "rollout_percentage": 100},
  "after": {"enabled": false, "rollout_percentage": 100},
  "timestamp": "2026-03-31T10:20:15Z",
  "audit_entry": {
    "timestamp": "2026-03-31T10:20:15Z",
    "action": "rollback",
    "flag_key": "new-checkout-flow",
    "decision": "executed",
    "confidence": 1.0,
    "reasoning": "Auto-rollback: 5.2x error spike",
    "outcome": "success"
  }
}
```

### Example Response (Safety Blocked)

```json
{
  "error": "Safety check failed",
  "reasons": ["Flag 'billing-core' is in the PROTECTED list and cannot be auto-toggled."],
  "overrides_needed": ["remove_from_protected_list"],
  "audit_entry": {
    "timestamp": "2026-03-31T10:21:00Z",
    "action": "disable",
    "flag_key": "billing-core",
    "decision": "blocked",
    "reasoning": "Flag 'billing-core' is in the PROTECTED list...",
    "outcome": "safety_blocked"
  }
}
```

---

## Claude Desktop Integration

Add this to your Claude Desktop MCP client configuration (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "posthog-flag-agent": {
      "command": "python",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "/path/to/posthog-flag-agent"
    }
  }
}
```

Or if installed as a package:

```json
{
  "mcpServers": {
    "posthog-flag-agent": {
      "command": "posthog-flag-mcp"
    }
  }
}
```

Make sure your `.env` file is configured with the appropriate PostHog credentials (or set `AGENT_USE_SIMULATOR=true` for local testing).

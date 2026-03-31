# Demo Walkthrough — Step-by-Step Guide

This guide walks you through three demo scenarios that showcase the agent's capabilities.

## Prerequisites

```bash
# Clone and set up
git clone https://github.com/YOUR_USERNAME/posthog-flag-agent.git
cd posthog-flag-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -e ".[dev]"

# Copy env template
cp .env.example .env
# Default settings use the simulator (no PostHog API key needed)
```

---

## Scenario 1: Error Spike Triggers Autonomous Rollback

**What happens**: A feature flag is enabled, causing checkout errors. The agent detects the spike, correlates it with the flag change, and autonomously rolls it back.

### Run

```bash
python -m src demo
# or
python examples/scenario_spike.py
```

### Expected Flow

1. **Baseline building** (5s) — The simulator generates normal background errors to establish a baseline.

2. **Flag enabled** — `new-checkout-flow` is activated with 100% rollout.

3. **Error spike begins** — Checkout-related errors surge to ~6x the baseline.

4. **Spike detected** — The agent detects the anomaly within 1-2 cycles:
   ```
   ⚡ SPIKE DETECTED
   Rate: 35.0 errors/bucket (baseline: 5.2)
   Spike factor: 6.7x
   Affected services: checkout-service
   ```

5. **Correlation analysis** — The reasoning chain is displayed:
   ```
   Temporal: flag 'new-checkout-flow' changed 2.3 min before spike → score 0.90
   Content: stack-trace keyword match for 'new-checkout-flow' → score 0.90
   Variant: error-rate skew between control/treatment → score 0.80
   Combined confidence: 0.40×0.90 + 0.35×0.90 + 0.25×0.80 = 0.8750
   Recommended action: auto_rollback
   ```

6. **Auto-rollback executed** — The flag is disabled.

7. **Slack notification** — An incident summary is posted to the mock Slack webhook.

8. **Verification** — The agent confirms the error rate returns to baseline.

**Total runtime**: ~2 minutes

---

## Scenario 2: Spike Detected But No Flag Correlation

**What happens**: An error spike occurs, but no feature flag was recently changed. The agent correctly logs the finding without taking autonomous action.

### Run

```bash
python examples/scenario_no_correlation.py
```

### Expected Output

```
🔍 Scenario: Spike With No Flag Correlation

Building baseline...
  Baseline: 5.0 errors/bucket

Triggering error spike (no flags changed)...

⚡ Spike detected! Factor: 5.2x
  Recent flag changes: 0
  Reasoning:
    No recent flag changes found — cannot correlate.
  Action: log_and_monitor (confidence: 0.0000)
  ✓ Agent correctly did NOT auto-rollback
```

---

## Scenario 3: Agent Hits Safety Limit

**What happens**: Three flags are deployed in quick succession, each causing errors. After two auto-rollbacks, the safety guard activates and requests human approval for the third.

### Run

```bash
python examples/scenario_safety_gate.py
```

### Expected Output

```
🛡️ Scenario: Safety Gate — Rate Limit Hit

Building baseline...

── Incident 1: 'flag-alpha' ──
  ✓ Auto-rollback of 'flag-alpha' succeeded

── Incident 2: 'flag-beta' ──
  ✓ Auto-rollback of 'flag-beta' succeeded

── Incident 3: 'flag-gamma' ──
  ⚠ SAFETY GATE ACTIVATED
  • Rate limit exceeded: 2/2 rollbacks in the last hour.
  • Cooldown active: 295s remaining after last rollback.
  
  Overrides needed: increase_rate_limit, skip_cooldown
  Human approval requested — Slack notification sent

✅ Demo complete
Audit trail entries: 3
Slack notifications: 1
```

---

## Running the Components Independently

### MCP Server (for Claude Desktop or other MCP clients)

```bash
python -m src server
```

### Autonomous Agent (continuous monitoring)

```bash
python -m src agent
```

### Error Stream Simulator (visual)

```bash
python -m src simulate
```

---

## Customising the Demos

Edit `.env` to adjust agent behaviour:

| Variable | Effect |
|----------|--------|
| `AGENT_SPIKE_THRESHOLD_STD=1.5` | More sensitive spike detection |
| `AGENT_CORRELATION_CONFIDENCE_AUTO_THRESHOLD=0.70` | Lower bar for auto-rollback |
| `AGENT_MAX_AUTO_ROLLBACKS_PER_HOUR=5` | Allow more autonomous actions |
| `AGENT_PROTECTED_FLAGS=["flag-x"]` | Protect specific flags from automation |

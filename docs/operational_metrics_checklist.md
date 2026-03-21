# Operational Metrics Checklist

**Version:** 1.0.0  
**Status:** ACTIVE  
**For:** Monitoring Agent-OS V1 during pilot operation

This checklist defines metrics to watch and indicators of system health.

---

## Metrics Overview

### Categories

1. **System Health Metrics** - Is the system functioning correctly?
2. **Safety Metrics** - Are safety constraints being maintained?
3. **Operator Workload Metrics** - How much manual work is required?
4. **Scheduler Usefulness Metrics** - Is the scheduler providing value?
5. **Architecture Health Metrics** - Does the architecture need revision?

---

## System Health Metrics

### State File Growth

**Metric:** Line count of each state file

**Measurement:**
```bash
wc -l state/*.jsonl
```

**Healthy Range:**
- Growth rate: 0-50 lines per day during pilot
- No sudden spikes (>100 lines in one hour)
- No negative growth (files should never shrink)

**Warning Indicators:**
- Sudden spike: May indicate runaway process
- Negative growth: State corruption or manual deletion
- No growth for extended period: System may be stuck

---

### Test Pass Rate

**Metric:** Percentage of tests passing

**Measurement:**
```bash
python3 -m pytest tests/ -q
```

**Healthy Range:** 100% pass rate

**Warning Indicators:**
- Any test failure: Investigate immediately
- Intermittent failures: May indicate race condition or state corruption

---

### Operational Summary Completeness

**Metric:** Can operational summary be built without errors?

**Measurement:**
```python
from tools.manual_ops import show_operational_summary
summary = show_operational_summary()
assert summary["status"] == "ok"
```

**Healthy Range:** Always returns `status: ok`

**Warning Indicators:**
- Status not "ok": System may be in degraded state
- Missing counts: State file read failure
- Empty summary: No state files or all corrupted

---

## Safety Metrics

### Scheduler Actions Executed

**Metric:** Number of actions executed by scheduler

**Measurement:**
```python
from scheduler.controlled_scheduler import run_controlled_scheduler_once
result = run_controlled_scheduler_once()
print(f"Actions executed: {result['actions_executed']}")
```

**Required Value:** 0 (ALWAYS)

**Warning Indicators:**
- ANY non-zero value: IMMEDIATE HALT - automation detected
- This is a critical safety violation

---

### Governance Denial Rate

**Metric:** Percentage of actions denied by governance

**Measurement:**
```python
from audit.operational_report import build_operational_summary
summary = build_operational_summary()
denied_count = summary["counts"]["governance_denied_items"]
total_count = summary["counts"]["apply_plans"]
denial_rate = denied_count / total_count if total_count > 0 else 0
print(f"Denial rate: {denial_rate:.1%}")
```

**Healthy Range:** 0-50% during pilot

**Warning Indicators:**
- High denial rate (>50%): May indicate operator misunderstanding
- 100% denial rate: All operations blocked - investigate
- Sudden spike: May indicate system issue

---

### Manual Approval Rate

**Metric:** Percentage of actions requiring manual approval

**Measurement:**
```python
from governance.operating_policy import load_governance_decisions
decisions = load_governance_decisions()
manual_required = [d for d in decisions if d.get("manual_approval_required")]
rate = len(manual_required) / len(decisions) if decisions else 0
print(f"Manual approval rate: {rate:.1%}")
```

**Expected Value:** 100% for all risky actions

**Warning Indicators:**
- Any risky action without manual approval requirement: Safety bypass
- This is a critical safety violation

---

### Revert Candidate Rate

**Metric:** Percentage of apply plans that become revert candidates

**Measurement:**
```python
from audit.operational_report import build_operational_summary
summary = build_operational_summary()
revert_count = summary["counts"]["revert_candidates_pending"]
failed_count = summary["counts"]["failed_verifications"]
rate = revert_count / failed_count if failed_count > 0 else 0
print(f"Revert candidate rate: {rate:.1%}")
```

**Healthy Range:** 50-100% of failed verifications

**Warning Indicators:**
- 0%: Revert candidates not being created when they should be
- >100%: More revert candidates than failures (may be ok if multiple per plan)

---

## Operator Workload Metrics

### Pending Verifications Count

**Metric:** Number of verifications waiting to be processed

**Measurement:**
```python
from tools.manual_ops import show_operational_summary
summary = show_operational_summary()
pending = summary["counts"]["pending_verifications"]
print(f"Pending verifications: {pending}")
```

**Healthy Range:** 0-5 during pilot

**Warning Indicators:**
- Growing backlog: Operator overwhelmed
- Stuck at high number: Verification process blocked
- Never decreasing: Operator not processing

---

### Pending Manual Actions Count

**Metric:** Number of actions waiting for manual trigger

**Measurement:**
```python
from tools.manual_ops import show_operational_summary
summary = show_operational_summary()
pending = summary["counts"]["pending_apply_actions"]
print(f"Pending manual actions: {pending}")
```

**Healthy Range:** 0-10 during pilot

**Warning Indicators:**
- Growing backlog: Operator overwhelmed
- High number for extended period: Bottleneck in process
- Sudden spike: System issue creating too many plans

---

### Stale Items Count

**Metric:** Number of apply plans that have become stale

**Measurement:**
```python
from tools.manual_ops import show_operational_summary
summary = show_operational_summary()
stale = summary["counts"]["stale_items"]
print(f"Stale items: {stale}")
```

**Healthy Range:** 0-3 during pilot

**Warning Indicators:**
- Growing stale items: Plans not being processed
- High stale rate: Operations taking too long
- No stale items but high pending: Plans being created but not processed

---

### Operator Actions Per Day

**Metric:** Number of manual actions taken by operator

**Measurement:**
```python
from governance.operating_policy import load_governance_decisions
decisions = load_governance_decisions()
# Filter by today's date
today = datetime.now().strftime("%Y-%m-%d")
today_decisions = [d for d in decisions if d.get("created_at", "").startswith(today)]
print(f"Operator actions today: {len(today_decisions)}")
```

**Healthy Range:** 1-10 per day during pilot

**Warning Indicators:**
- 0 actions: System not being used or operator absent
- >10 actions: May be too much workload
- Sudden spike: Unusual activity requiring investigation

---

## Scheduler Usefulness Metrics

### Detection Accuracy

**Metric:** Percentage of detected items that are actually actionable

**Measurement:**
```python
from scheduler.controlled_scheduler import run_controlled_scheduler_once
result = run_controlled_scheduler_once()
detected = result["actions_detected"]
# Manually assess: are these actually actionable?
# This requires operator judgment
```

**Healthy Range:** >50% actionable

**Warning Indicators:**
- Low actionable rate: Scheduler detecting noise
- 0% actionable: Scheduler not useful
- High false positive rate: Scheduler thresholds need adjustment

---

### Detection Coverage

**Metric:** Are all important items being detected?

**Measurement:**
```python
# Compare scheduler output with manual inspection
from scheduler.controlled_scheduler import run_controlled_scheduler_once
from tools.manual_ops import show_operational_summary

scheduler_result = run_controlled_scheduler_once()
summary = show_operational_summary()

# Check if scheduler detected all pending items
scheduler_pending = scheduler_result["actions"]["counts"]["pending_verifications"]
summary_pending = summary["counts"]["pending_verifications"]

coverage = scheduler_pending / summary_pending if summary_pending > 0 else 1.0
print(f"Detection coverage: {coverage:.1%}")
```

**Healthy Range:** 90-100% coverage

**Warning Indicators:**
- <90% coverage: Scheduler missing items
- 0% coverage: Scheduler broken
- Inconsistent coverage: Detection logic issue

---

### Scheduler Run Frequency

**Metric:** How often scheduler is run

**Measurement:**
```python
from scheduler.controlled_scheduler import load_scheduler_runs
runs = load_scheduler_runs()
# Count runs per day
```

**Healthy Range:** 1-24 runs per day (hourly to daily)

**Warning Indicators:**
- No runs: Scheduler not being used
- Too many runs (>24/day): Operator over-relying on scheduler
- Irregular pattern: Inconsistent operation

---

## Architecture Health Metrics

### Layer Coupling

**Metric:** Are layers properly separated?

**Measurement:**
- Manual inspection during code review
- Check for cross-layer bypasses
- Verify append-only constraints

**Healthy Indicators:**
- Each layer has clear responsibility
- No bypass mechanisms
- All state changes go through proper channels

**Warning Indicators:**
- Direct state file access bypassing layer functions
- Cross-layer shortcuts
- In-place state mutations

---

### State Reconstruction Accuracy

**Metric:** Can current state be accurately reconstructed from state files?

**Measurement:**
```python
from audit.operational_report import get_apply_plan_operational_status
# Pick a known apply plan
status = get_apply_plan_operational_status("known_plan_id")
# Verify status matches expected state
```

**Healthy Range:** 100% accuracy

**Warning Indicators:**
- Incorrect state reconstruction
- Missing information in reconstructed state
- Inconsistency between multiple reconstruction methods

---

### Recovery from Partial Failure

**Metric:** Does system handle partial/corrupted state gracefully?

**Measurement:**
- Simulate partial failure (in test environment)
- Verify conservative behavior
- Check error handling

**Healthy Indicators:**
- System doesn't crash
- Conservative decisions made
- Operator alerted to issue

**Warning Indicators:**
- System crashes
- Unsafe decisions made
- Silent failures

---

## Metric Collection Schedule

### Real-Time (Continuous)

- Scheduler actions executed (must always be 0)
- Test pass rate (must always be 100%)
- Governance denial rate

### Hourly

- Pending verifications count
- Pending manual actions count
- Stale items count

### Daily

- State file growth
- Operational summary completeness
- Operator actions per day
- Detection accuracy
- Detection coverage
- Scheduler run frequency

### Weekly

- Layer coupling review
- State reconstruction accuracy
- Recovery from partial failure

---

## Alert Thresholds

### Critical (Immediate Action Required)

| Metric | Threshold | Action |
|--------|-----------|--------|
| Scheduler actions executed | > 0 | HALT system immediately |
| Test pass rate | < 100% | HALT operations, investigate |
| Manual approval rate for risky actions | < 100% | HALT system, safety bypass detected |

### Warning (Investigate Within 1 Hour)

| Metric | Threshold | Action |
|--------|-----------|--------|
| Pending verifications | > 5 | Process backlog |
| Stale items | > 3 | Review and clean up |
| State file growth | > 50 lines/hour | Investigate spike |
| Detection coverage | < 90% | Review scheduler logic |

### Info (Monitor)

| Metric | Threshold | Action |
|--------|-----------|--------|
| Governance denial rate | > 50% | Review operator procedures |
| Operator actions per day | > 10 | Consider workload |
| Scheduler runs per day | > 24 | Consider frequency |

---

## Metric Reporting

### Daily Report Format

```
=== Agent-OS Daily Metrics ===
Date: YYYY-MM-DD

System Health:
- Tests: PASS
- State file growth: X lines
- Summary status: OK

Safety:
- Scheduler actions executed: 0 ✓
- Governance denial rate: X%
- Manual approval rate: 100% ✓

Operator Workload:
- Pending verifications: X
- Pending manual actions: X
- Stale items: X
- Operator actions today: X

Scheduler Usefulness:
- Detection coverage: X%
- Runs today: X

Notes:
- [Any significant events]
```

---

## Metric Trend Analysis

### Week-over-Week Trends

Track these trends weekly:

1. **State file growth rate** - Should be stable
2. **Governance denial rate** - Should decrease as operators learn
3. **Pending items** - Should not grow unboundedly
4. **Stale items** - Should be processed regularly
5. **Scheduler usefulness** - Should remain high

### Signs of Healthy Operation

- Stable state file growth (no spikes)
- Low governance denial rate (operators understand system)
- Pending items processed regularly (no backlog)
- Few stale items (plans processed timely)
- Scheduler detects accurately (high coverage, low noise)

### Signs of Architecture Issues

- Growing pending items (bottleneck in process)
- Increasing stale items (operations too slow)
- Low scheduler usefulness (detection not helpful)
- High governance denial rate (operator confusion)
- State reconstruction issues (data model problems)

---

## Metric Collection Automation

### Recommended Collection Script

```python
#!/usr/bin/env python3
"""collect_metrics.py - Collect operational metrics"""

import sys
sys.path.insert(0, '/home/milky/agent-os')

from datetime import datetime
from tools.manual_ops import show_operational_summary
from scheduler.controlled_scheduler import run_controlled_scheduler_once, load_scheduler_runs
from governance.operating_policy import load_governance_decisions

def collect_metrics():
    """Collect all metrics and return report."""
    
    # System health
    summary = show_operational_summary()
    
    # Safety
    scheduler_result = run_controlled_scheduler_once()
    
    # Governance
    decisions = load_governance_decisions()
    today = datetime.now().strftime("%Y-%m-%d")
    today_decisions = [d for d in decisions if d.get("created_at", "").startswith(today)]
    
    report = {
        "date": today,
        "system_health": {
            "summary_status": summary["status"],
            "counts": summary["counts"],
        },
        "safety": {
            "scheduler_actions_executed": scheduler_result["actions_executed"],
            "scheduler_actions_detected": scheduler_result["actions_detected"],
        },
        "operator_workload": {
            "pending_verifications": summary["counts"]["pending_verifications"],
            "pending_manual_actions": summary["counts"]["pending_apply_actions"],
            "stale_items": summary["counts"]["stale_items"],
            "operator_actions_today": len(today_decisions),
        },
    }
    
    return report

if __name__ == "__main__":
    import json
    report = collect_metrics()
    print(json.dumps(report, indent=2))
```

---

**Document Status:** ACTIVE  
**Review Frequency:** Daily during pilot

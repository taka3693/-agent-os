# Pilot Start Commands

**Version:** 1.0.0  
**Status:** ACTIVE

Exact commands for pilot operation.

---

## Quick Start

```bash
cd /home/milky/agent-os
```

---

## Status Commands

### Show Operational Summary

```bash
python3 -c "
from tools.manual_ops import show_operational_summary
import json
summary = show_operational_summary()
print(json.dumps(summary['counts'], indent=2))
"
```

### Show Apply Plan Status

```bash
python3 -c "
from tools.manual_ops import show_apply_plan_status
import json
status = show_apply_plan_status('APPLY_PLAN_ID')
print(json.dumps(status, indent=2, default=str))
"
```

### List All Apply Plans

```bash
python3 -c "
from tools.manual_ops import list_all_apply_plans
result = list_all_apply_plans()
print(f'Total: {result[\"count\"]}')
for p in result['apply_plans'][:5]:
    print(f'  {p[\"apply_plan_id\"]}: {p.get(\"latest_apply_state\", \"unknown\")}')
"
```

### List Pending Verifications

```bash
python3 -c "
from tools.manual_ops import list_pending_verifications
result = list_pending_verifications()
print(f'Pending: {result[\"count\"]}')
for v in result['verifications'][:5]:
    print(f'  {v[\"verification_id\"]}: {v[\"apply_plan_id\"]}')
"
```

### List Revert Candidates

```bash
python3 -c "
from tools.manual_ops import list_pending_revert_candidates
result = list_pending_revert_candidates()
print(f'Candidates: {result[\"count\"]}')
for c in result['candidates'][:5]:
    print(f'  {c[\"apply_plan_id\"]}: {c.get(\"reason\", \"unknown\")}')
"
```

---

## Manual Apply Commands

### Step 1: Evaluate Governance

```bash
python3 -c "
from tools.manual_ops import evaluate_manual_governance
import json
result = evaluate_manual_governance('APPLY', 'APPLY_PLAN_ID')
print(json.dumps(result, indent=2, default=str))
"
```

**Expected:** `decision: MANUAL_APPROVAL_REQUIRED` or `DENIED`

### Step 2: Grant Manual Approval

```bash
python3 -c "
from tools.manual_ops import grant_manual_approval
import json
result = grant_manual_approval(
    action_type='APPLY',
    entity_id='APPLY_PLAN_ID',
    approver='OPERATOR_NAME',
    reason='Reviewed and approved'
)
print(json.dumps(result, indent=2, default=str))
"
```

**Expected:** `status: approved`

### Step 3: Execute Manual Apply

```bash
python3 -c "
from tools.manual_ops import run_manual_apply
import json
result = run_manual_apply(
    apply_plan_id='APPLY_PLAN_ID',
    patch_path=None,  # or '/path/to/patch.diff'
    executor_identity='OPERATOR_NAME'
)
print(json.dumps(result, indent=2, default=str))
"
```

**Expected:** `status: completed` or `failed` (NOT `blocked`)

---

## Verification Commands

### Run Manual Verification

```bash
python3 -c "
from tools.manual_ops import run_manual_verification
import json
result = run_manual_verification(
    verification_id='VERIFICATION_ID',
    changed_files=[]  # or ['/path/to/file.py']
)
print(json.dumps(result, indent=2, default=str))
"
```

**Expected:** `status: completed`, `passed: true/false`

---

## Policy Commands

### Evaluate Manual Policy

```bash
python3 -c "
from tools.manual_ops import evaluate_manual_policy
import json
result = evaluate_manual_policy('APPLY_PLAN_ID')
print(json.dumps(result, indent=2, default=str))
"
```

**Expected:** `policy_decision: PROMOTE_ELIGIBLE` or `REJECT` or `HOLD_REVIEW`

---

## Scheduler Commands

### Run Scheduler Once

```bash
python3 -c "
from scheduler.controlled_scheduler import run_controlled_scheduler_once
import json
result = run_controlled_scheduler_once()
print(f'Actions detected: {result[\"actions_detected\"]}')
print(f'Actions executed: {result[\"actions_executed\"]}')  # MUST be 0
print(json.dumps(result['actions']['counts'], indent=2))
"
```

**Expected:** `actions_executed: 0`

### Verify Scheduler Safety

```bash
python3 -c "
from scheduler.controlled_scheduler import verify_scheduler_safety
import json
result = verify_scheduler_safety()
print(f'Safety verified: {result[\"verified\"]}')
"
```

**Expected:** `verified: true`

---

## Audit Commands

### Show Apply Plan Audit Report

```bash
python3 -c "
from tools.manual_ops import show_apply_plan_audit_report
import json
report = show_apply_plan_audit_report('APPLY_PLAN_ID')
print(f'Apply plan: {report[\"apply_plan_id\"]}')
print(f'State history: {len(report[\"apply_state_history\"])} events')
"
```

---

## Test Commands

### Run All Tests

```bash
python3 -m pytest tests/ -q
```

**Expected:** All tests pass

### Run Specific Tests

```bash
python3 -m pytest tests/test_guard_smoke.py tests/test_apply_lifecycle.py -v
```

---

## Safety Verification Commands

### Verify No Auto-Execution

```bash
# Check scheduler runs
python3 -c "
from scheduler.controlled_scheduler import load_scheduler_runs
runs = load_scheduler_runs()
for run in runs[-5:]:
    if run.get('actions_executed', 0) != 0:
        print('WARNING: Auto-execution detected!')
        break
else:
    print('OK: No auto-execution detected')
"
```

### Verify Governance Enforced

```bash
python3 -c "
from governance.operating_policy import load_governance_decisions
decisions = load_governance_decisions()
risky_actions = ['APPLY', 'PROMOTE', 'REVERT', 'COMMIT']
for d in decisions:
    if d.get('action_type') in risky_actions:
        if not d.get('manual_approval_required', True):
            print('WARNING: Risky action without manual approval!')
            break
else:
    print('OK: All risky actions require manual approval')
"
```

---

## Emergency Commands

### Stop All Operations

```bash
# No automated operations to stop
# System is manually-gated by design
echo 'System is manually-gated. No automated operations to stop.'
```

### Check State File Integrity

```bash
python3 -c "
import json
from pathlib import Path
state_dir = Path('state')
for f in state_dir.glob('*.jsonl'):
    try:
        with open(f) as file:
            for line in file:
                if line.strip():
                    json.loads(line)
        print(f'OK: {f.name}')
    except json.JSONDecodeError as e:
        print(f'ERROR: {f.name} - {e}')
"
```

---

## Full Status Check

```bash
# Run all status checks
python3 << 'EOF'
from tools.manual_ops import show_operational_summary
from scheduler.controlled_scheduler import verify_scheduler_safety
import json

print("=== Operational Summary ===")
summary = show_operational_summary()
print(json.dumps(summary['counts'], indent=2))

print("\n=== Scheduler Safety ===")
safety = verify_scheduler_safety()
print(f"Verified: {safety['verified']}")

print("\n=== Status ===")
print("System ready for pilot operation")
EOF
```

---

**Document Status:** ACTIVE

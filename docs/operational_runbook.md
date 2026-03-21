# Operational Runbook

This document provides operational procedures for Agent-OS.

## Overview

Agent-OS is a **manually-gated system**. All risky actions require explicit human approval.

**Key Principle:** The system DETECTS and REPORTS, but does NOT automatically EXECUTE risky actions.

## System Layers

| Layer | Purpose | Executes Actions |
|-------|---------|------------------|
| Execution Guard | Safety checks | No |
| Proposal Pipeline | Track proposals | No |
| Simulation Pipeline | Dry-run evaluation | No |
| Apply Lifecycle | Track apply state | No |
| Controlled Patch Executor | Execute patches | **Only with governance approval** |
| Post-Apply Verification | Verify results | No |
| Improvement Policy | Evaluate outcomes | No |
| Governance / Operating Policy | Control action eligibility | No |
| Audit / Operational Reporting | Report status | No |
| Manual Ops Surface | Operator interface | **Only with governance approval** |
| Controlled Scheduler | Periodic detection | No |

## Operational Commands

### Status Commands (READ-ONLY)

```python
# View system-wide operational summary
from tools.manual_ops import show_operational_summary
summary = show_operational_summary()
print(summary["counts"])

# View specific apply plan status
from tools.manual_ops import show_apply_plan_status
status = show_apply_plan_status("apply_plan_abc123")
print(status)

# List all apply plans
from tools.manual_ops import list_all_apply_plans
plans = list_all_apply_plans()

# List pending verifications
from tools.manual_ops import list_pending_verifications
pending = list_pending_verifications()

# List revert candidates
from tools.manual_ops import list_pending_revert_candidates
candidates = list_pending_revert_candidates()
```

### Scheduler Commands (DETECT ONLY)

```python
# Run scheduler once (detects, does NOT execute)
from scheduler.controlled_scheduler import run_controlled_scheduler_once
result = run_controlled_scheduler_once()
print(f"Detected: {result['actions_detected']}, Executed: {result['actions_executed']}")
# Expected: actions_executed = 0

# Verify scheduler safety
from scheduler.controlled_scheduler import verify_scheduler_safety
safety = verify_scheduler_safety()
print(f"Safety verified: {safety['verified']}")
```

### Action Commands (REQUIRE GOVERNANCE APPROVAL)

```python
# Evaluate governance eligibility (READ-ONLY)
from tools.manual_ops import evaluate_manual_governance
eligibility = evaluate_manual_governance("APPLY", "apply_plan_abc123")
print(f"Decision: {eligibility['decision']}")
print(f"Manual approval required: {eligibility['manual_approval_required']}")

# Grant manual approval (RECORDS ONLY, does NOT execute)
from tools.manual_ops import grant_manual_approval
approval = grant_manual_approval(
    action_type="APPLY",
    entity_id="apply_plan_abc123",
    approver="operator_name",
    reason="reviewed and approved",
)
print(f"Approval status: {approval['status']}")

# Execute apply (BLOCKED if governance denies)
from tools.manual_ops import run_manual_apply
result = run_manual_apply(
    apply_plan_id="apply_plan_abc123",
    patch_path="/path/to/patch.diff",
    executor_identity="operator_name",
)
print(f"Result: {result['status']}")
# Possible: "blocked" (governance denied), "completed", "failed"
```

## Operational Workflows

### Workflow 1: Check System Status

1. Run operational summary
2. Review pending items
3. Identify items needing attention

```python
from tools.manual_ops import show_operational_summary, format_summary_for_display

summary = show_operational_summary()
print(format_summary_for_display(summary))
```

### Workflow 2: Process Pending Verification

1. List pending verifications
2. Select verification to process
3. Run verification manually
4. Review results

```python
from tools.manual_ops import list_pending_verifications, run_manual_verification

# Step 1: List pending
pending = list_pending_verifications()
print(f"Pending: {pending['count']}")

# Step 2-3: Run verification
if pending['verifications']:
    result = run_manual_verification(
        verification_id=pending['verifications'][0]['verification_id'],
        changed_files=[],
    )
    print(f"Result: {result['passed']}")
```

### Workflow 3: Evaluate Apply Candidate

1. Check apply plan status
2. Evaluate governance eligibility
3. Review requirements
4. Grant approval if appropriate
5. Execute apply

```python
from tools.manual_ops import (
    show_apply_plan_status,
    evaluate_manual_governance,
    grant_manual_approval,
    run_manual_apply,
)

apply_plan_id = "apply_plan_xyz"

# Step 1: Check status
status = show_apply_plan_status(apply_plan_id)
print(f"Verification: {status['latest_verification_status']}")
print(f"Policy: {status['latest_policy_decision']}")
print(f"Next action: {status['next_manual_action']}")

# Step 2: Evaluate governance
gov = evaluate_manual_governance("APPLY", apply_plan_id)
print(f"Governance decision: {gov['decision']}")
print(f"Is allowed: {gov['is_allowed']}")

# Step 3-4: Grant approval if needed
if gov['manual_approval_required'] and not gov['is_allowed']:
    approval = grant_manual_approval(
        action_type="APPLY",
        entity_id=apply_plan_id,
        approver="operator_name",
        reason="reviewed and approved",
    )
    print(f"Approval: {approval['status']}")

# Step 5: Execute
result = run_manual_apply(apply_plan_id)
print(f"Result: {result['status']}")
```

### Workflow 4: Handle Revert Candidate

1. List revert candidates
2. Review candidate details
3. Evaluate governance for revert
4. Grant approval if appropriate
5. Execute revert (manual)

```python
from tools.manual_ops import (
    list_pending_revert_candidates,
    show_apply_plan_status,
    evaluate_manual_governance,
    grant_manual_approval,
)

# Step 1: List candidates
candidates = list_pending_revert_candidates()
print(f"Pending revert candidates: {candidates['count']}")

if candidates['candidates']:
    candidate = candidates['candidates'][0]
    apply_plan_id = candidate['apply_plan_id']
    
    # Step 2: Review
    status = show_apply_plan_status(apply_plan_id)
    print(f"Reason: {candidate['reason']}")
    
    # Step 3: Evaluate governance
    gov = evaluate_manual_governance("REVERT", apply_plan_id)
    print(f"Revert allowed: {gov['is_allowed']}")
    
    # Step 4-5: Grant approval and execute (manual)
    # Note: Actual revert execution requires operator to manually undo changes
```

## Common Scenarios

### Scenario: Verification Failed

**Symptom:** Verification shows "failed" status

**Action:**
1. Review failure codes in verification result
2. Check evidence refs for details
3. Fix underlying issue
4. Re-run verification manually

```python
from tools.manual_ops import show_apply_plan_status

status = show_apply_plan_status("apply_plan_id")
print(f"Failure codes: {status.get('failure_codes', [])}")
print(f"Evidence: {status.get('evidence_refs', [])}")
```

### Scenario: Apply Plan Stale

**Symptom:** Apply plan shows as "stale"

**Action:**
1. Review plan details
2. Decide: create new plan or extend expiry
3. If extending, update plan and re-evaluate governance

```python
from tools.manual_ops import show_apply_plan_status

status = show_apply_plan_status("apply_plan_id")
print(f"Is stale: {status['is_stale']}")
print(f"Reason: {status['stale_or_blocked_reason']}")
```

### Scenario: Governance Denied

**Symptom:** Action shows as "DENIED" by governance

**Action:**
1. Review denial reason
2. Address underlying issue
3. Re-evaluate governance

```python
from tools.manual_ops import evaluate_manual_governance

gov = evaluate_manual_governance("APPLY", "apply_plan_id")
print(f"Decision: {gov['decision']}")
print(f"Reason: {gov['reason']}")
```

## Safety Guarantees

The following actions are **NEVER** executed automatically:

| Action | Requires |
|--------|----------|
| Apply execution | Manual approval + governance check |
| Rollback execution | Manual approval + governance check |
| Commit execution | Manual approval + governance check |
| Promotion execution | Manual approval + governance check |

The scheduler **NEVER** executes risky actions:
- `actions_executed` is always 0
- Scheduler only DETECTS and REPORTS

## State Files

| File | Purpose | Format |
|------|---------|--------|
| `apply_plans.jsonl` | Apply plan records | JSONL (append-only) |
| `apply_state_transitions.jsonl` | Apply state history | JSONL (append-only) |
| `execution_leases.jsonl` | Execution leases | JSONL (append-only) |
| `post_apply_verification_results.jsonl` | Verification results | JSONL (append-only) |
| `patch_attempt_results.jsonl` | Patch attempt records | JSONL (append-only) |
| `policy_decisions.jsonl` | Policy decisions | JSONL (append-only) |
| `revert_candidates.jsonl` | Revert candidates | JSONL (append-only) |
| `governance_decisions.jsonl` | Governance decisions | JSONL (append-only) |
| `scheduler_runs.jsonl` | Scheduler run history | JSONL (append-only) |

**Important:** All state files are append-only. Never modify existing records.

## Troubleshooting

### Issue: "apply_plan_not_found"

**Cause:** Apply plan ID does not exist

**Solution:** Verify apply_plan_id is correct

### Issue: "Governance denied: manual_approval_not_granted"

**Cause:** Manual approval not yet granted

**Solution:** Use `grant_manual_approval()` to grant approval

### Issue: "INELIGIBLE_EXPIRED"

**Cause:** Apply plan has expired (older than 24 hours)

**Solution:** Create new apply plan or extend expiry

### Issue: "INELIGIBLE_INCOMPLETE"

**Cause:** Verification not complete

**Solution:** Complete verification using `run_manual_verification()`

### Issue: Scheduler detected items but didn't execute

**This is expected behavior.** The scheduler only detects and reports.

---

## Pilot Operation Rules

**Version:** 1.0.0  
**Status:** ACTIVE

---

### Scope

- **Single repository** - `/home/milky/agent-os`
- **Single operator** - One human operator at a time
- **Low-risk changes only** - No critical file modifications without explicit approval
- **Manual apply only** - All applies require manual trigger
- **Scheduler detect/report only** - No automatic execution

---

### Prohibited Actions

| Prohibition | Reason |
|-------------|--------|
| ❌ Automatic apply | Safety - requires human judgment |
| ❌ Automatic rollback | Safety - requires human judgment |
| ❌ Automatic commit | Safety - requires human review |
| ❌ Automatic promotion execution | Safety - requires human approval |
| ❌ State schema changes | Stability - frozen for pilot |
| ❌ New feature additions during pilot | Stability - frozen for pilot |

---

### Daily Checklist

Complete these checks every day:

1. **Operational Summary**
   ```bash
   python3 -c "from tools.manual_ops import show_operational_summary; print(show_operational_summary()['counts'])"
   ```

2. **Pending Manual Actions**
   - Review `pending_apply_actions` count
   - Process items if backlog grows

3. **Failed Verifications**
   - Review `failed_verifications` count
   - Investigate failure codes
   - Decide: fix and retry, or create revert candidate

4. **Governance Denials**
   - Review `governance_denied_items` count
   - Understand denial reasons
   - Address underlying issues

5. **Revert Candidates**
   - Review `revert_candidates_pending` count
   - Evaluate each candidate
   - Decide: revert or dismiss

6. **Stale Items**
   - Review `stale_items` count
   - Clean up or extend as needed

7. **Operator Friction Notes**
   - Document any difficulties
   - Note documentation gaps
   - Record improvement suggestions

---

### Required Records

| Template | When to Use |
|----------|-------------|
| `pilot_operation_log_template.md` | Every manual operation |
| `pilot_daily_review_template.md` | End of each day |
| `pilot_incident_report_template.md` | When incidents occur |

---

### Pilot Exit Criteria

Pilot is complete when ALL conditions are met:

| Criterion | Description |
|-----------|-------------|
| ✅ Runbook fluency | Can operate without hesitation using runbook |
| ✅ Acceptable noise | Verification/governance/scheduler noise within tolerance |
| ✅ No excessive rollbacks | Rollback recommendations not excessive |
| ✅ No excessive denials | Governance denials not frequent |
| ✅ Operator load acceptable | Manual workload is sustainable |

---

### Quick Reference

```bash
# Daily status check
python3 << 'EOF'
from tools.manual_ops import show_operational_summary
import json
summary = show_operational_summary()
print("=== Daily Metrics ===")
for key, value in summary['counts'].items():
    print(f"{key}: {value}")
EOF

# Scheduler safety check
python3 -c "
from scheduler.controlled_scheduler import verify_scheduler_safety
result = verify_scheduler_safety()
print(f'Safety verified: {result[\"verified\"]}')
"
```

---

**Document Status:** ACTIVE  
**Review Frequency:** Daily during pilot

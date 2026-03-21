# Pilot Operation Checklist

**Version:** 1.0.0  
**Status:** ACTIVE  
**For:** Initial controlled operation of Agent-OS V1

This checklist defines operator procedures for pilot operation.

---

## Pre-Pilot Verification

Complete all items before starting pilot operation.

### System Readiness

- [ ] **All tests passing**
  ```bash
  cd /home/milky/agent-os
  python3 -m pytest tests/ -q
  # Expected: All tests pass
  ```

- [ ] **State files initialized**
  ```bash
  ls state/*.jsonl
  # Expected: All state files exist (may be empty)
  ```

- [ ] **Docs complete**
  ```bash
  ls docs/*.md
  # Expected: All documentation files exist
  ```

### Safety Verification

- [ ] **Scheduler safety verified**
  ```python
  from scheduler.controlled_scheduler import verify_scheduler_safety
  result = verify_scheduler_safety()
  assert result["verified"] == True
  ```

- [ ] **No auto-execution code**
  ```bash
  grep -r "auto_apply\|auto_rollback\|auto_commit" --include="*.py" .
  # Expected: No matches
  ```

- [ ] **Governance enforced**
  ```python
  from governance.operating_policy import evaluate_action_eligibility, ACTION_APPLY
  result = evaluate_action_eligibility(ACTION_APPLY, "test_plan_id")
  assert result["decision"] == "DENIED"  # Should deny non-existent plan
  ```

### Documentation Review

- [ ] **Read architecture freeze**
  - File: `docs/v1_architecture_freeze.md`
  - Confirm understanding of layer boundaries

- [ ] **Read non-goals**
  - File: `docs/non_goals_and_prohibited_automation.md`
  - Confirm understanding of prohibited automation

- [ ] **Read operational runbook**
  - File: `docs/operational_runbook.md`
  - Confirm understanding of operational procedures

- [ ] **Read state schema contracts**
  - File: `docs/state_schema_contracts.md`
  - Confirm understanding of state file structure

---

## Daily Operations

### Morning Check (Start of Day)

- [ ] **Run operational summary**
  ```python
  from tools.manual_ops import show_operational_summary
  summary = show_operational_summary()
  print(summary["counts"])
  ```

- [ ] **Review pending items**
  - Check `pending_verifications`
  - Check `pending_apply_actions`
  - Check `revert_candidates_pending`
  - Check `stale_items`

- [ ] **Run scheduler once**
  ```python
  from scheduler.controlled_scheduler import run_controlled_scheduler_once
  result = run_controlled_scheduler_once()
  assert result["actions_executed"] == 0
  print(f"Detected: {result['actions_detected']}")
  ```

- [ ] **Verify no auto-execution**
  - Confirm `actions_executed == 0`
  - Confirm no unexpected changes in state files

### During Operations

- [ ] **Before any apply**
  1. Check governance eligibility
  2. Grant manual approval
  3. Verify approval recorded
  4. Execute apply manually
  5. Verify apply result

- [ ] **After any apply**
  1. Run post-apply verification
  2. Evaluate policy outcome
  3. Check operational status
  4. Update logs

- [ ] **When verification fails**
  1. Review failure codes
  2. Review evidence refs
  3. Decide: fix and retry, or create revert candidate
  4. Do NOT auto-rollback

### Evening Check (End of Day)

- [ ] **Run operational summary**
  ```python
  from tools.manual_ops import show_operational_summary
  summary = show_operational_summary()
  print(summary["counts"])
  ```

- [ ] **Compare with morning counts**
  - Note any changes
  - Investigate unexpected changes

- [ ] **Review state file growth**
  ```bash
  wc -l state/*.jsonl
  # Note: Files should only grow, never shrink
  ```

- [ ] **Document significant events**
  - Record any manual actions taken
  - Record any issues encountered
  - Record any decisions made

---

## Verification Failure Response

When verification fails, follow this procedure.

### Step 1: Assess Failure

```python
from tools.manual_ops import show_apply_plan_status

status = show_apply_plan_status("apply_plan_id")
print(f"Verification: {status['latest_verification_status']}")
print(f"Failure codes: {status.get('failure_codes', [])}")
print(f"Evidence: {status.get('evidence_refs', [])}")
```

### Step 2: Determine Action

**Option A: Fix and Retry**
- Fix the underlying issue
- Re-run verification manually
- Monitor results

**Option B: Create Revert Candidate**
- Let policy evaluate automatically
- Review revert candidate recommendation
- Decide manually whether to revert

**Option C: Hold for Investigation**
- Leave in current state
- Investigate root cause
- Decide later

### Step 3: Execute Decision

**If Option A (Fix and Retry):**
```python
from tools.manual_ops import run_manual_verification

result = run_manual_verification(
    verification_id="verification_id",
    changed_files=[],
)
```

**If Option B (Revert):**
```python
from tools.manual_ops import (
    evaluate_manual_governance,
    grant_manual_approval,
)

# Step 1: Check governance
gov = evaluate_manual_governance("REVERT", "apply_plan_id")

# Step 2: Grant approval if required
if gov["manual_approval_required"]:
    grant_manual_approval(
        action_type="REVERT",
        entity_id="apply_plan_id",
        approver="operator_name",
        reason="verification failed, reverting",
    )

# Step 3: Manually execute revert (operator action)
# Note: System does not auto-revert
```

**If Option C (Hold):**
- Document decision
- Schedule investigation
- Monitor for changes

---

## Governance Denial Response

When governance denies an action, follow this procedure.

### Step 1: Understand Denial Reason

```python
from tools.manual_ops import evaluate_manual_governance

gov = evaluate_manual_governance("APPLY", "apply_plan_id")
print(f"Decision: {gov['decision']}")
print(f"Reason: {gov['reason']}")
```

### Step 2: Address Reason

**If INELIGIBLE_EXPIRED:**
- Plan is too old
- Create new plan if still needed
- Do not attempt to force execution

**If INELIGIBLE_INCOMPLETE:**
- Verification not complete
- Complete verification first
- Re-evaluate governance

**If DENIED:**
- Fundamental issue exists
- Review denial reason
- Fix underlying issue
- Create new plan

**If MANUAL_APPROVAL_REQUIRED:**
- Grant manual approval
- Re-check governance
- Execute if allowed

### Step 3: Re-Evaluate

After addressing the reason:
```python
from governance.operating_policy import evaluate_action_eligibility

result = evaluate_action_eligibility("APPLY", "apply_plan_id")
print(f"New decision: {result['decision']}")
```

---

## Stale State Accumulation Response

When stale items accumulate, follow this procedure.

### Step 1: Identify Stale Items

```python
from tools.manual_ops import show_operational_summary

summary = show_operational_summary()
stale_items = summary.get("stale_items", [])
print(f"Stale items: {len(stale_items)}")
for item in stale_items:
    print(f"  {item['apply_plan_id']}: {item['reason']}")
```

### Step 2: Decide Per Item

**Option A: Dismiss (No Longer Needed)**
- Document decision
- Mark as dismissed (manual record)
- Remove from active monitoring

**Option B: Extend (Still Needed)**
- Create new plan with fresh timestamp
- Preserve original plan for audit
- Monitor new plan

**Option C: Force Review (Urgent)**
- Escalate to review
- Make explicit decision
- Document outcome

### Step 3: Clean Up

- Update operational notes
- Record decisions made
- Archive dismissed plans (if applicable)

---

## Emergency Procedures

### System Not Responding

1. **Stop all operations**
2. **Check state file integrity**
   ```bash
   python3 -c "import json; [json.loads(line) for line in open('state/apply_plans.jsonl')]"
   # If error, state file may be corrupted
   ```
3. **Check logs**
4. **Restart if safe**
5. **Document incident**

### Unexpected Execution

1. **STOP: Halt all operations immediately**
2. **Verify: Check what was executed**
3. **Document: Record everything**
4. **Investigate: Find root cause**
5. **Fix: Restore constraints**
6. **Review: Update safeguards**

### State File Corruption

1. **Stop: Halt operations**
2. **Backup: Copy corrupted files**
3. **Assess: Determine extent of corruption**
4. **Recover: Reconstruct from valid records**
5. **Verify: Run tests**
6. **Resume: Continue operations**

---

## Pilot Scope Limits

During pilot operation, observe these limits:

### Maximum Scale

- **Apply Plans:** 10 active plans at a time
- **Verifications:** 5 pending verifications at a time
- **Revert Candidates:** 3 pending candidates at a time
- **Scheduler Runs:** 1 run per hour maximum

### Prohibited Actions During Pilot

- Do NOT increase automation
- Do NOT bypass governance
- Do NOT modify architecture
- Do NOT auto-execute anything

### Required Approvals

- Any new apply plan: Operator approval
- Any apply execution: Operator approval
- Any revert: Operator approval
- Any architecture change: Redesign approval

---

## Pilot Completion Criteria

Pilot is complete when:

- [ ] 10 apply plans processed successfully
- [ ] 5 verifications completed (mix of pass/fail)
- [ ] 3 revert candidates handled
- [ ] No auto-execution incidents
- [ ] No state corruption incidents
- [ ] All operational procedures validated
- [ ] Documentation validated against actual operation

---

## Sign-Off

**Pilot Start Date:** _______________

**Operator Name:** _______________

**Supervisor Name:** _______________

**Pre-Pilot Checklist Completed:** [ ]

**Daily Checklist Template Created:** [ ]

**Emergency Procedures Understood:** [ ]

---

**Document Status:** ACTIVE  
**Review Frequency:** Daily during pilot

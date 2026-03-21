# Non-Goals and Prohibited Automation

**Version:** 1.0.0  
**Status:** ACTIVE

This document explicitly defines what Agent-OS V1 MUST NOT do.

---

## Core Principle

**Agent-OS is a manually-gated system.** All risky actions require explicit human approval and manual trigger.

The system DETECTS and REPORTS, but does NOT automatically EXECUTE risky actions.

---

## Prohibited Automation

### 1. NO Automatic Apply

**Definition:** The system must never automatically apply patches or code changes.

**Prohibited Behaviors:**
- Auto-executing apply plans
- Auto-applying patches without manual trigger
- Auto-executing based on policy decisions
- Auto-executing based on scheduler output

**Required Instead:**
- Manual trigger required for every apply
- Governance approval required before apply
- Execution lease required before apply

**Code Locations Enforcing This:**
- `governance/operating_policy.py`: `evaluate_action_eligibility()` returns `MANUAL_APPROVAL_REQUIRED`
- `tools/manual_ops.py`: `run_manual_apply()` checks `is_action_allowed()`
- `execution/controlled_patch_executor.py`: Requires manual trigger

---

### 2. NO Automatic Rollback

**Definition:** The system must never automatically revert changes, even on verification failure.

**Prohibited Behaviors:**
- Auto-reverting on verification failure
- Auto-reverting on policy recommendation
- Auto-reverting on governance denial
- Auto-reverting based on scheduler detection

**Required Instead:**
- Revert candidates are RECOMMENDATIONS only
- Manual review required for every revert
- Manual trigger required for revert execution

**Code Locations Enforcing This:**
- `policy/improvement_policy.py`: `REVERT_CANDIDATE_RECOMMENDED` is a recommendation, not execution
- `policy/improvement_policy.py`: `create_revert_candidate()` only creates record
- No automatic revert execution code exists

---

### 3. NO Automatic Commit

**Definition:** The system must never automatically commit changes to the repository.

**Prohibited Behaviors:**
- Auto-committing after apply
- Auto-committing after verification
- Auto-committing based on policy decision
- Auto-committing based on scheduler

**Required Instead:**
- Commits are manual operator actions
- System tracks what SHOULD be committed
- Operator decides when to commit

**Code Locations Enforcing This:**
- No auto-commit code exists
- `tools/manual_ops.py`: No commit function
- Governance requires manual approval for COMMIT action

---

### 4. NO Automatic Promotion Execution

**Definition:** The system must never automatically promote proposals or apply plans.

**Prohibited Behaviors:**
- Auto-promoting when `PROMOTE_ELIGIBLE`
- Auto-promoting after verification success
- Auto-promoting based on policy decision
- Auto-promoting based on scheduler

**Required Instead:**
- `PROMOTE_ELIGIBLE` is a recommendation only
- Manual review required for every promotion
- Manual trigger required for promotion

**Code Locations Enforcing This:**
- `policy/improvement_policy.py`: `PROMOTE_ELIGIBLE` does not execute
- `governance/operating_policy.py`: Promotion requires `MANUAL_APPROVAL_REQUIRED`
- `tools/manual_ops.py`: No auto-promote function

---

### 5. NO Unattended Self-Improvement Loop

**Definition:** The system must never run autonomous improvement cycles without human oversight.

**Prohibited Behaviors:**
- Auto-generating and applying self-improvements
- Auto-creating proposals and executing them
- Auto-modifying its own code or configuration
- Auto-scheduling improvement cycles

**Required Instead:**
- All improvements require manual proposal
- All proposals require manual review
- All executions require manual trigger
- Scheduler only detects, never executes

**Code Locations Enforcing This:**
- `scheduler/controlled_scheduler.py`: `actions_executed` always 0
- No self-modification code exists
- All changes require governance approval

---

### 6. NO Automatic State Mutation

**Definition:** The system must never modify existing state records.

**Prohibited Behaviors:**
- Modifying existing JSONL records
- Deleting state records
- In-place updates to state files
- Truncating state files

**Required Instead:**
- Append-only state design
- State reconstruction from all records
- Latest record is authoritative

**Code Locations Enforcing This:**
- All state files use `_append_jsonl_record()` pattern
- No in-place modification functions exist
- `docs/state_schema_contracts.md` defines append-only guarantees

---

### 7. NO Automatic Decision Execution

**Definition:** The system must never execute decisions without human confirmation.

**Prohibited Behaviors:**
- Executing policy decisions automatically
- Executing governance decisions automatically
- Executing verification results automatically
- Executing scheduler recommendations automatically

**Required Instead:**
- All decisions are recommendations
- All executions require manual trigger
- Manual approval gate for all risky actions

**Code Locations Enforcing This:**
- All policy decisions have `executed: false`
- Governance requires `MANUAL_APPROVAL_REQUIRED`
- Scheduler has `actions_executed: 0`

---

### 8. NO Bypass of Safety Checks

**Definition:** No layer may bypass execution guard or safety checks.

**Prohibited Behaviors:**
- Bypassing syntax checks
- Bypassing critical file protection
- Bypassing pytest requirements
- Bypassing governance checks

**Required Instead:**
- All checks must pass
- No shortcuts for any layer
- Conservative behavior on check failure

**Code Locations Enforcing This:**
- `execution/guard.py`: All checks run for every execution
- `execution/controlled_patch_executor.py`: `_run_safety_checks()` required
- `governance/operating_policy.py`: Governance checks enforced

---

## Non-Goals for V1

The following are explicitly NOT goals for V1:

### Not Attempting Full Autonomy

V1 is not designed to be fully autonomous. It requires human operators for:
- Proposal review
- Apply execution
- Rollback decisions
- Commit decisions
- Promotion decisions

### Not Attempting Self-Healing

V1 does not self-heal. It:
- Detects issues
- Reports issues
- Recommends actions
- Requires manual intervention

### Not Attempting Predictive Operation

V1 does not predict future states or needs. It:
- Reports current state
- Detects pending items
- Requires human judgment

### Not Attempting Optimization

V1 does not optimize operations automatically. It:
- Provides visibility
- Requires manual optimization decisions

---

## Enforcement Mechanisms

### Code-Level Enforcement

1. **Governance Layer:** All risky actions require `is_action_allowed()` check
2. **Manual Ops Surface:** All actions route through governance
3. **Scheduler:** `actions_executed` is hardcoded to 0
4. **State Files:** Append-only design prevents mutation

### Documentation-Level Enforcement

1. **Architecture Freeze:** Changes require redesign approval
2. **Schema Contracts:** Append-only guarantees documented
3. **Operational Runbook:** Manual procedures documented

### Test-Level Enforcement

1. **E2E Tests:** Verify no auto-execution
2. **Recovery Tests:** Verify conservative behavior
3. **Safety Tests:** Verify guard enforcement

---

## Violation Detection

### Signs of Prohibited Automation

If you observe any of the following, immediately halt operation:

1. **`actions_executed > 0`** in scheduler output
2. **Patches applied without manual trigger**
3. **Commits made without operator action**
4. **State records modified (not appended)**
5. **Safety checks bypassed**

### Response to Violations

1. **Stop Operation:** Halt all system activity
2. **Investigate:** Identify source of violation
3. **Document:** Record what happened
4. **Fix:** Restore constraints
5. **Review:** Update safeguards

---

## Future Considerations

Any future version that attempts to introduce automation MUST:

1. **Explicit Design:** Automation must be explicitly designed, not accidental
2. **Safety Review:** Automation must pass safety review
3. **Gradual Rollout:** Automation must roll out gradually with controls
4. **Kill Switch:** Automation must have manual override
5. **Audit Trail:** Automation must maintain audit trail

---

**Document Status:** ACTIVE  
**Review Frequency:** Every pilot operation review

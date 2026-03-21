# V1 Architecture Freeze

**Status:** FROZEN  
**Effective Date:** 2026-03-15  
**Version:** 1.0.0

This document defines the frozen architecture for Agent-OS V1. No structural changes should be made without explicit redesign approval.

---

## Implemented Layers

### 1. Execution Guard (`execution/guard.py`)

**Responsibility:** Safety checks before any code execution.

**Key Functions:**
- `check_syntax()` - Python syntax validation
- `check_critical_files()` - Critical file protection
- `check_pytest()` - Pytest result validation
- `run_all_guards()` - Comprehensive safety gate

**Boundaries:**
- MUST NOT be bypassed by any other layer
- MUST NOT auto-execute risky operations
- MUST block on dangerous changes

**State Files:** None (stateless checks)

---

### 2. Proposal Pipeline (`tools/run_agent_os_request.py`)

**Responsibility:** Track proposal candidates and queue management.

**Key Functions:**
- `_build_proposal_record()` - Create proposal records
- `_append_proposal_queue()` - Append to queue
- `load_proposal_queue()` - Load proposals
- `rank_proposals()` - Rank for review priority

**Boundaries:**
- MUST NOT auto-promote proposals
- MUST NOT execute proposals
- MUST maintain append-only queue

**State Files:**
- `state/proposal_queue.jsonl` - Proposal records (append-only)
- `state/proposal_state_transitions.jsonl` - State transitions (append-only)

---

### 3. Simulation Pipeline (`tools/run_agent_os_request.py`)

**Responsibility:** Dry-run evaluation of proposals.

**Key Functions:**
- `build_apply_simulation_candidate()` - Build simulation candidate
- `evaluate_simulation_candidate()` - Evaluate candidate
- `store_simulation_result()` - Store results

**Boundaries:**
- MUST NOT execute real changes
- MUST be dry-run only
- MUST preserve append-only results

**State Files:**
- `state/simulation_results.jsonl` - Simulation results (append-only)

---

### 4. Apply Lifecycle Layer (`tools/apply_lifecycle.py`)

**Responsibility:** Track apply plan state through lifecycle.

**Key Functions:**
- `create_apply_plan()` - Create frozen execution intent
- `record_apply_state_transition()` - Record state changes
- `acquire_execution_lease()` - Prevent duplicate execution
- `create_extended_patch_attempt()` - Record patch attempts
- `create_post_apply_verification()` - Create verification tasks

**Boundaries:**
- MUST NOT auto-apply
- MUST NOT auto-commit
- MUST maintain append-only state

**State Files:**
- `state/apply_plans.jsonl` - Apply plan records (append-only)
- `state/apply_state_transitions.jsonl` - State transitions (append-only)
- `state/execution_leases.jsonl` - Execution leases (append-only)
- `state/patch_attempt_results.jsonl` - Patch attempts (append-only)
- `state/post_apply_verification_results.jsonl` - Verification results (append-only)

---

### 5. Controlled Patch Executor (`execution/controlled_patch_executor.py`)

**Responsibility:** Execute patches with safety checks.

**Key Functions:**
- `execute_apply_plan()` - Main entry point
- `_run_safety_checks()` - Precondition validation
- `_apply_patch()` - Patch application

**Boundaries:**
- MUST require governance approval before execution
- MUST acquire execution lease
- MUST record all attempts

**Safety Guarantees:**
- Manual trigger required
- Governance check required
- Execution lease required
- No auto-apply

---

### 6. Post-Apply Verification Policy (`verification/post_apply_verifier.py`)

**Responsibility:** Verify successful patch application.

**Key Functions:**
- `run_post_apply_verification()` - Run verification checks
- `_run_verification_checks()` - Execute checks
- `_run_targeted_pytest()` - Targeted testing

**Boundaries:**
- MUST NOT auto-rollback on failure
- MUST record structured results
- MUST be conservative with ambiguous state

**State Files:** Reuses `state/post_apply_verification_results.jsonl`

---

### 7. Improvement Policy Engine (`policy/improvement_policy.py`)

**Responsibility:** Evaluate outcomes and recommend actions.

**Key Functions:**
- `evaluate_apply_outcome()` - Evaluate and record decision
- `create_revert_candidate()` - Create revert recommendation
- `_determine_decision()` - Decision logic

**Decision Types:**
- `PROMOTE_ELIGIBLE` - Safe to promote (requires manual trigger)
- `HOLD_REVIEW` - Needs human review
- `REJECT` - Should be rejected
- `REVERT_CANDIDATE_RECOMMENDED` - Rollback recommended (requires manual trigger)

**Boundaries:**
- MUST NOT auto-promote
- MUST NOT auto-revert
- MUST only record recommendations

**State Files:**
- `state/policy_decisions.jsonl` - Policy decisions (append-only)
- `state/revert_candidates.jsonl` - Revert candidates (append-only)

---

### 8. Governance / Operating Policy (`governance/operating_policy.py`)

**Responsibility:** Control action eligibility and manual approvals.

**Key Functions:**
- `evaluate_action_eligibility()` - Check if action is allowed
- `record_governance_decision()` - Record decisions
- `is_action_allowed()` - Combined eligibility + approval check
- `check_manual_approval_granted()` - Check approval status

**Decision Types:**
- `ALLOWED` - Permitted (requires manual trigger)
- `DENIED` - Not permitted
- `MANUAL_APPROVAL_REQUIRED` - Requires human approval
- `INELIGIBLE_EXPIRED` - Expired entity
- `INELIGIBLE_INCOMPLETE` - Incomplete verification
- `INELIGIBLE_AMBIGUOUS` - Ambiguous state

**Boundaries:**
- MUST require manual approval for all risky actions
- MUST NOT bypass manual gates
- MUST deny ambiguous states

**State Files:**
- `state/governance_decisions.jsonl` - Governance decisions (append-only)

---

### 9. Audit / Operational Reporting (`audit/operational_report.py`)

**Responsibility:** Reconstruct and report operational status.

**Key Functions:**
- `get_apply_plan_operational_status()` - Single plan status
- `build_operational_summary()` - System-wide summary
- `build_apply_plan_audit_report()` - Detailed audit report

**Boundaries:**
- READ-ONLY operations only
- MUST NOT mutate state
- MUST reconstruct from append-only records

**State Files:** Reuses all existing state files (read-only)

---

### 10. Manual Ops Surface (`tools/manual_ops.py`)

**Responsibility:** Operator interface for all actions.

**Key Functions:**
- `show_operational_summary()` - View status
- `run_manual_apply()` - Execute apply (with governance check)
- `grant_manual_approval()` - Grant approval
- `list_pending_revert_candidates()` - List candidates

**Boundaries:**
- MUST route through governance for risky actions
- MUST block actions without approval
- MUST NOT bypass safety checks

---

### 11. Controlled Scheduler (`scheduler/controlled_scheduler.py`)

**Responsibility:** Periodic detection and reporting only.

**Key Functions:**
- `run_controlled_scheduler_once()` - Single run
- `build_scheduler_actions()` - Detect items
- `verify_scheduler_safety()` - Safety verification

**Boundaries:**
- MUST NOT execute any risky actions
- `actions_executed` MUST always be 0
- MUST only detect and report

**State Files:**
- `state/scheduler_runs.jsonl` - Run history (append-only)

---

## Append-Only Guarantees

All state files use JSONL format with append-only semantics:

1. **No In-Place Modification:** Existing records are never modified
2. **No Deletion:** Records are never deleted
3. **State Reconstruction:** Current state is reconstructed by replaying all records
4. **Latest Record Wins:** For entities with multiple records, the latest is authoritative

**Invariant:** Any file in `state/*.jsonl` must only be appended to, never modified or truncated.

---

## Architecture Boundaries

### Must NOT Cross Without Redesign

1. **Guard Bypass:** No layer may bypass execution guard checks
2. **Auto-Execution:** No layer may automatically execute risky actions
3. **State Mutation:** No layer may modify existing state records
4. **Manual Gate Bypass:** No layer may bypass governance/manual approval requirements
5. **Scheduler Execution:** Scheduler must never execute actions, only report

### Safe Interactions

- All layers may READ from any state file
- Only designated functions may APPEND to specific state files
- No layer may WRITE to state files outside its designated scope

---

## Version Freeze Declaration

As of 2026-03-15, the V1 architecture is **FROZEN**. 

**Changes Require:**
1. Explicit redesign proposal
2. Safety review
3. Operator approval
4. Test coverage verification

**Permitted Changes:**
- Documentation updates
- Test additions
- Configuration adjustments
- Bug fixes that preserve constraints

**Prohibited Changes (without redesign):**
- New automation capabilities
- Bypass mechanisms
- State mutation logic
- Architecture restructuring

---

**Document Status:** FROZEN  
**Next Review:** After pilot operation completion

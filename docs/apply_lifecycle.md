# Apply Lifecycle Separation Layer

This document describes the apply lifecycle separation layer that extends the Agent-OS self-improvement pipeline.

## Overview

The apply lifecycle separation layer provides controlled patch execution with:

- **Apply Plans**: Frozen execution intent records
- **Apply State Transitions**: Append-only lifecycle events
- **Execution Leases**: Duplicate/concurrent execution prevention
- **Post-Apply Verification**: Separate verification result records
- **Extended Patch Attempts**: Full execution fact recording

## Key Principle: Lifecycle Separation

```
Proposal Lifecycle        Apply Lifecycle
─────────────────        ─────────────────
proposal_queue.jsonl     apply_plans.jsonl
proposal_state_          apply_state_
transitions.jsonl        transitions.jsonl
simulation_results.jsonl execution_leases.jsonl
                         post_apply_verification_
                         results.jsonl
                         patch_attempt_results.jsonl
```

**Critical**: Proposal lifecycle and apply lifecycle are **separate**:
- Proposals track intent and approval
- Apply lifecycle tracks execution and verification
- Simulation results verify intent; verification results verify execution

## State Files

### apply_plans.jsonl

Frozen apply intent records created after manual apply readiness is satisfied.

**Fields:**
- `apply_plan_id`: Unique identifier
- `proposal_id`: Source proposal
- `approved_by`: Who approved this plan
- `approved_at`: Approval timestamp
- `patch_artifact_ref`: Reference to patch artifact
- `expected_verifications`: List of expected verification steps
- `safety_constraints_snapshot`: Snapshot of constraints at creation
- `idempotency_key`: For deduplication
- `eligibility_expires_at`: When plan expires if not executed
- `created_at`: Creation timestamp

### apply_state_transitions.jsonl

Append-only lifecycle events for apply execution flow.

**Event Types:**
- `apply_plan_created`
- `apply_plan_approved`
- `execution_lease_acquired`
- `patch_attempt_started`
- `patch_attempt_succeeded`
- `patch_attempt_failed`
- `post_apply_verification_started`
- `post_apply_verification_passed`
- `post_apply_verification_failed`
- `apply_closed`

**Fields:**
- `apply_plan_id`: Apply plan ID
- `event`: Event type
- `at`: Timestamp
- `actor`: Who/what triggered this
- `reason`: Optional reason
- `metadata`: Optional additional data

### execution_leases.jsonl

Prevents duplicate or concurrent execution of the same apply plan.

**Fields:**
- `lease_id`: Unique identifier
- `apply_plan_id`: Apply plan ID
- `acquired_at`: Acquisition timestamp
- `acquired_by`: Who acquired the lease
- `lease_scope`: Scope of the lease
- `expires_at`: Expiration timestamp
- `status`: "active" or "blocked"

**Conservative Behavior:**
- If a valid lease already exists, new lease request returns `blocked`
- Expired leases are ignored
- Append-only: no in-place mutation

### post_apply_verification_results.jsonl

Verification results **after** patch execution (separate from simulation results).

**Fields:**
- `verification_id`: Unique identifier
- `apply_plan_id`: Apply plan ID
- `patch_attempt_id`: Patch attempt ID
- `started_at`: Start timestamp
- `finished_at`: Completion timestamp
- `verification_steps`: List of steps run
- `result`: "pending", "passed", or "failed"
- `failure_codes`: List of failure codes
- `summary`: Summary of verification
- `evidence_refs`: List of evidence references

### patch_attempt_results.jsonl

Extended patch attempt records with full execution facts.

**Fields:**
- `patch_attempt_id`: Unique identifier
- `apply_plan_id`: Linkage to apply plan
- `execution_lease_id`: Linkage to execution lease
- `started_at`: Start timestamp
- `finished_at`: Completion timestamp
- `executor_identity`: Who/what executed
- `patch_artifact_ref`: Reference to patch artifact
- `precondition_check_result`: Precondition check result
- `execution_result`: "pending", "succeeded", or "failed"
- `failure_code`: Failure code if failed
- `failure_detail`: Detailed failure message
- `diff_summary`: Summary of changes made
- `produced_artifact_refs`: List of produced artifacts

## API Functions

### Apply Plans

```python
from tools.run_agent_os_request import create_apply_plan, load_apply_plans

# Create a plan
plan = create_apply_plan(
    proposal_id="abc123",
    approved_by="manual",
    patch_artifact_ref="patches/abc123.diff",
    expected_verifications=["syntax_check", "pytest"],
)

# Load all plans
plans = load_apply_plans()
```

### Apply State Transitions

```python
from tools.run_agent_os_request import (
    record_apply_state_transition,
    load_apply_state_transitions,
    get_latest_apply_state,
)

# Record transition
record_apply_state_transition(
    apply_plan_id="plan_xyz",
    event="patch_attempt_started",
    actor="executor",
)

# Get latest state
latest = get_latest_apply_state("plan_xyz")
```

### Execution Leases

```python
from tools.run_agent_os_request import (
    acquire_execution_lease,
    find_active_lease_for_plan,
)

# Acquire lease
lease = acquire_execution_lease(
    apply_plan_id="plan_xyz",
    acquired_by="worker_1",
    expires_in_seconds=3600,
)

# Check if blocked
if lease["status"] == "blocked":
    print(f"Blocked: {lease['reason']}")
```

### Post-Apply Verification

```python
from tools.run_agent_os_request import (
    create_post_apply_verification,
    complete_post_apply_verification,
)

# Start verification
verification = create_post_apply_verification(
    apply_plan_id="plan_xyz",
    patch_attempt_id="attempt_001",
    verification_steps=["syntax_check", "pytest"],
)

# Complete verification
completed = complete_post_apply_verification(
    verification_id=verification["verification_id"],
    result="passed",
    summary="All checks passed",
)
```

### Extended Patch Attempts

```python
from tools.run_agent_os_request import (
    create_extended_patch_attempt,
    complete_extended_patch_attempt,
)

# Start attempt
attempt = create_extended_patch_attempt(
    apply_plan_id="plan_xyz",
    execution_lease_id="lease_001",
    executor_identity="manual_executor",
)

# Complete attempt
completed = complete_extended_patch_attempt(
    patch_attempt_id=attempt["patch_attempt_id"],
    execution_result="succeeded",
    diff_summary="+10 -5 lines",
)
```

## Safety Guarantees

1. **No Automatic Apply**: All apply operations require explicit manual invocation
2. **No Automatic Rollback**: Rollback must be explicitly triggered
3. **No Automatic Promotion**: Promotion must be explicitly triggered
4. **Append-Only Design**: All state files use append-only pattern
5. **Lifecycle Separation**: Proposal and apply lifecycles are separate
6. **Verification Separation**: Simulation results and post-apply verification are separate
7. **Lease-Based Concurrency**: Duplicate execution is prevented by lease mechanism

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Proposal Lifecycle                       │
├─────────────────────────────────────────────────────────────┤
│  proposal_queue.jsonl                                       │
│         ↓                                                   │
│  proposal_state_transitions.jsonl                           │
│         ↓                                                   │
│  simulation_results.jsonl                                   │
│         ↓                                                   │
│  [Manual Apply Gate]                                        │
│         ↓                                                   │
│  patch_attempt_results.jsonl (basic)                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                     Apply Lifecycle                         │
├─────────────────────────────────────────────────────────────┤
│  apply_plans.jsonl                                          │
│         ↓                                                   │
│  apply_state_transitions.jsonl                              │
│         ↓                                                   │
│  execution_leases.jsonl                                     │
│         ↓                                                   │
│  patch_attempt_results.jsonl (extended)                     │
│         ↓                                                   │
│  post_apply_verification_results.jsonl                      │
└─────────────────────────────────────────────────────────────┘
```

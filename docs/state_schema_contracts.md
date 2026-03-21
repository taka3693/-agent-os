# State Schema Contracts

This document defines the schema contracts for all state files in Agent-OS.

## Principles

1. **Append-Only:** All state files are append-only. Never modify existing records.
2. **JSONL Format:** All state files use JSON Lines format (one JSON object per line).
3. **Immutable Records:** Each record represents a point-in-time fact.
4. **Reconstruction:** Current state is reconstructed by replaying all records.

## State Files

### apply_plans.jsonl

**Purpose:** Records of apply plan creation.

**Location:** `state/apply_plans.jsonl`

**Schema:**

```json
{
  "apply_plan_id": "string (16 chars, MD5 hash)",
  "proposal_id": "string",
  "approved_by": "string",
  "approved_at": "string (ISO 8601 datetime)",
  "patch_artifact_ref": "string (optional)",
  "expected_verifications": ["string"],
  "safety_constraints_snapshot": {},
  "idempotency_key": "string (UUID)",
  "eligibility_expires_at": "string (ISO 8601 datetime, optional)",
  "created_at": "string (ISO 8601 datetime)"
}
```

**Required Fields:**
- `apply_plan_id`
- `proposal_id`
- `approved_by`
- `created_at`

**Optional Fields:**
- `patch_artifact_ref`
- `expected_verifications`
- `safety_constraints_snapshot`
- `eligibility_expires_at`

---

### apply_state_transitions.jsonl

**Purpose:** Records of apply state transitions.

**Location:** `state/apply_state_transitions.jsonl`

**Schema:**

```json
{
  "apply_plan_id": "string",
  "event": "string (enum)",
  "at": "string (ISO 8601 datetime)",
  "actor": "string",
  "reason": "string (optional)",
  "metadata": {} // optional
}
```

**Event Types:**
- `apply_plan_created`
- `execution_lease_acquired`
- `patch_attempt_started`
- `patch_attempt_succeeded`
- `patch_attempt_failed`
- `post_apply_verification_started`
- `post_apply_verification_passed`
- `post_apply_verification_failed`
- `apply_closed`

**Required Fields:**
- `apply_plan_id`
- `event`
- `at`

**Optional Fields:**
- `actor`
- `reason`
- `metadata`

---

### execution_leases.jsonl

**Purpose:** Records of execution leases (prevents duplicate execution).

**Location:** `state/execution_leases.jsonl`

**Schema:**

```json
{
  "lease_id": "string (16 chars)",
  "apply_plan_id": "string",
  "acquired_at": "string (ISO 8601 datetime)",
  "acquired_by": "string",
  "lease_scope": "string",
  "expires_at": "string (ISO 8601 datetime)",
  "status": "string (enum: active, released, expired)"
}
```

**Required Fields:**
- `lease_id`
- `apply_plan_id`
- `acquired_at`
- `acquired_by`
- `expires_at`
- `status`

**Optional Fields:**
- `lease_scope`

---

### post_apply_verification_results.jsonl

**Purpose:** Records of post-apply verification results.

**Location:** `state/post_apply_verification_results.jsonl`

**Schema:**

```json
{
  "verification_id": "string (16 chars)",
  "apply_plan_id": "string",
  "patch_attempt_id": "string",
  "started_at": "string (ISO 8601 datetime)",
  "finished_at": "string (ISO 8601 datetime, optional)",
  "verification_steps": ["string"],
  "result": "string (enum: pending, passed, failed)",
  "failure_codes": ["string"],
  "summary": "string",
  "evidence_refs": ["string"]
}
```

**Result Types:**
- `pending`
- `passed`
- `failed`

**Required Fields:**
- `verification_id`
- `apply_plan_id`
- `started_at`
- `result`

**Optional Fields:**
- `patch_attempt_id`
- `finished_at`
- `verification_steps`
- `failure_codes`
- `summary`
- `evidence_refs`

---

### patch_attempt_results.jsonl

**Purpose:** Records of patch attempt results.

**Location:** `state/patch_attempt_results.jsonl`

**Schema:**

```json
{
  "patch_attempt_id": "string (16 chars)",
  "apply_plan_id": "string",
  "execution_lease_id": "string",
  "started_at": "string (ISO 8601 datetime)",
  "finished_at": "string (ISO 8601 datetime, optional)",
  "executor_identity": "string",
  "patch_artifact_ref": "string",
  "precondition_check_result": "string",
  "execution_result": "string (enum: pending, succeeded, failed)",
  "failure_code": "string (optional)",
  "failure_detail": "string (optional)",
  "diff_summary": "string",
  "produced_artifact_refs": ["string"]
}
```

**Execution Result Types:**
- `pending`
- `succeeded`
- `failed`

**Required Fields:**
- `patch_attempt_id`
- `apply_plan_id`
- `started_at`
- `execution_result`

**Optional Fields:**
- `execution_lease_id`
- `finished_at`
- `executor_identity`
- `patch_artifact_ref`
- `precondition_check_result`
- `failure_code`
- `failure_detail`
- `diff_summary`
- `produced_artifact_refs`

---

### policy_decisions.jsonl

**Purpose:** Records of improvement policy decisions.

**Location:** `state/policy_decisions.jsonl`

**Schema:**

```json
{
  "decision_id": "string (16 chars)",
  "apply_plan_id": "string",
  "decision": "string (enum)",
  "reason": "string",
  "verification_result": "string (optional)",
  "apply_state": "string (optional)",
  "evidence_refs": ["string"],
  "created_at": "string (ISO 8601 datetime)",
  "executed": "boolean (always false)",
  "additional_context": {}
}
```

**Decision Types:**
- `PROMOTE_ELIGIBLE`
- `HOLD_REVIEW`
- `REJECT`
- `REVERT_CANDIDATE_RECOMMENDED`

**Required Fields:**
- `decision_id`
- `apply_plan_id`
- `decision`
- `reason`
- `created_at`
- `executed`

**Optional Fields:**
- `verification_result`
- `apply_state`
- `evidence_refs`
- `additional_context`

---

### revert_candidates.jsonl

**Purpose:** Records of revert candidates.

**Location:** `state/revert_candidates.jsonl`

**Schema:**

```json
{
  "candidate_id": "string (16 chars)",
  "apply_plan_id": "string",
  "decision_id": "string",
  "reason": "string",
  "status": "string (enum: pending, executed, dismissed)",
  "created_at": "string (ISO 8601 datetime)",
  "executed_at": "string (ISO 8601 datetime, optional)",
  "executed_by": "string (optional)"
}
```

**Status Types:**
- `pending`
- `executed`
- `dismissed`

**Required Fields:**
- `candidate_id`
- `apply_plan_id`
- `reason`
- `status`
- `created_at`

**Optional Fields:**
- `decision_id`
- `executed_at`
- `executed_by`

---

### governance_decisions.jsonl

**Purpose:** Records of governance decisions.

**Location:** `state/governance_decisions.jsonl`

**Schema:**

```json
{
  "decision_id": "string (16 chars)",
  "action_type": "string (enum)",
  "entity_id": "string",
  "decision": "string (enum)",
  "reason": "string",
  "manual_approval_required": "boolean",
  "entity_status": {},
  "created_at": "string (ISO 8601 datetime)",
  "approver": "string (optional)",
  "additional_context": {}
}
```

**Action Types:**
- `APPLY`
- `PROMOTE`
- `REVERT`
- `COMMIT`

**Decision Types:**
- `ALLOWED`
- `DENIED`
- `MANUAL_APPROVAL_REQUIRED`
- `INELIGIBLE_EXPIRED`
- `INELIGIBLE_INCOMPLETE`
- `INELIGIBLE_AMBIGUOUS`

**Required Fields:**
- `decision_id`
- `action_type`
- `entity_id`
- `decision`
- `created_at`

**Optional Fields:**
- `reason`
- `manual_approval_required`
- `entity_status`
- `approver`
- `additional_context`

---

### scheduler_runs.jsonl

**Purpose:** Records of scheduler runs.

**Location:** `state/scheduler_runs.jsonl`

**Schema:**

```json
{
  "run_id": "string (16 chars)",
  "run_at": "string (ISO 8601 datetime)",
  "status": "string (enum: completed, failed)",
  "actions_detected": "number",
  "actions_executed": "number (always 0)",
  "counts": {
    "pending_verifications": "number",
    "stale_apply_plans": "number",
    "revert_candidates_pending": "number",
    "governance_denied_items": "number",
    "pending_manual_actions": "number"
  }
}
```

**Required Fields:**
- `run_id`
- `run_at`
- `status`
- `actions_detected`
- `actions_executed`
- `counts`

**Important:** `actions_executed` is always 0. The scheduler never executes risky actions.

---

## Schema Validation

### Helper Function

```python
from pathlib import Path
import json

def validate_state_file(path: Path, required_fields: list) -> dict:
    """Validate a state file against schema.
    
    Returns:
        dict with 'valid', 'errors', 'records' keys
    """
    if not path.exists():
        return {"valid": True, "errors": [], "records": 0, "note": "file does not exist"}
    
    errors = []
    records = 0
    
    with open(path, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                record = json.loads(line)
                records += 1
                
                # Check required fields
                for field in required_fields:
                    if field not in record:
                        errors.append(f"Line {line_num}: missing required field '{field}'")
            except json.JSONDecodeError as e:
                errors.append(f"Line {line_num}: invalid JSON - {e}")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "records": records,
    }
```

### Validation Usage

```python
from pathlib import Path

STATE_DIR = Path("state")

# Validate apply plans
result = validate_state_file(
    STATE_DIR / "apply_plans.jsonl",
    ["apply_plan_id", "proposal_id", "created_at"]
)
print(f"Apply plans valid: {result['valid']}, records: {result['records']}")

# Validate governance decisions
result = validate_state_file(
    STATE_DIR / "governance_decisions.jsonl",
    ["decision_id", "action_type", "entity_id", "decision", "created_at"]
)
print(f"Governance decisions valid: {result['valid']}, records: {result['records']}")
```

---

### learning_episodes.jsonl

**Purpose:** Records of learning episodes and their classifications.

**Location:** `state/learning_episodes.jsonl`

**Schema:**

```json
{
  "episode_id": "string (UUID prefix, 16 chars)",
  "apply_plan_id": "string",
  "patch_attempt_id": "string (optional)",
  "verification_id": "string (optional)",
  "policy_decision_id": "string (optional)",
  "governance_decision_id": "string (optional)",
  "patch_type": "string (derived)",
  "target_area": "string (derived)",
  "verification_outcome": "string (optional)",
  "policy_outcome": "string (optional)",
  "governance_outcome": "string (optional)",
  "final_operator_action": "string (derived, optional)",
  "revert_candidate_created": "boolean",
  "failure_codes": ["string"],
  "time_to_close_minutes": "number (optional)",
  "stale_flag": "boolean",
  "evidence_refs": ["string"],
  "created_at": "string (ISO 8601 datetime)",
  "outcome": "string (optional, added after classification)",
  "classification_reason": "string (optional)",
  "classification_confidence": "string (optional)",
  "classification_factors": ["string"] (optional),
  "classified_at": "string (ISO 8601 datetime, optional)"
}
```

**Outcome Types:**
- `success_clean` - Verification passed, policy approved
- `success_high_friction` - Success with multiple attempts
- `blocked_by_governance` - Governance denied
- `failed_verification` - Verification failed
- `rejected_low_confidence` - Policy rejected
- `stale_abandoned` - Plan expired
- `revert_recommended` - Revert candidate created

**Required Fields:**
- `episode_id`
- `apply_plan_id`
- `created_at`

**Note:** Classification fields (`outcome`, `classification_reason`, etc.) are added when the episode is classified. Multiple records may exist for the same `episode_id` - use the latest (last in file) for current classification.

---

### learning_insights.jsonl

**Purpose:** Records of generated learning insights.

**Location:** `state/learning_insights.jsonl`

**Schema:**

```json
{
  "insight_id": "string (YYYYMMDDHHMMSS)",
  "generated_at": "string (ISO 8601 datetime)",
  "patterns": [
    {
      "type": "string",
      "dimension": "string (optional)",
      "value": "string (optional)",
      "count": "number",
      "episodes": ["string"]
    }
  ],
  "recommendations": [
    {
      "pattern_type": "string",
      "recommendation": "string",
      "priority": "string",
      "automatic": "boolean (always false)"
    }
  ],
  "statistics": {
    "total_episodes": "number",
    "total_classified": "number",
    "by_outcome": {},
    "pattern_count": "number",
    "recommendation_count": "number"
  },
  "note": "string"
}
```

**Pattern Types:**
- `repeated_verification_failures` - Multiple verification failures by type/area
- `repeated_governance_denials` - Multiple governance denials
- `repeated_stale_abandoned` - Multiple stale episodes
- `repeated_revert_recommendations` - Multiple revert recommendations

**Required Fields:**
- `insight_id`
- `generated_at`
- `patterns`
- `recommendations`
- `statistics`

**Note:** Insights are recommendations only. No automatic execution.

---

## Migration Notes

### Adding New Fields

When adding new fields to existing schemas:

1. **Always make new fields optional** - existing records won't have them
2. **Update documentation** - add field to "Optional Fields" section
3. **Update loaders** - use `.get("field", default)` pattern
4. **Test backwards compatibility** - ensure old records still work

### Deprecating Fields

When deprecating fields:

1. **Never remove from existing records** - append-only design
2. **Stop writing the field** - new records won't have it
3. **Update loaders** - treat missing field as default value
4. **Update documentation** - mark as deprecated

---

## Safety Constraints

### Immutable Constraints

The following constraints are enforced by the system:

1. **No in-place modification** - All state files are append-only
2. **No deletion** - Records are never deleted
3. **Deterministic IDs** - IDs are generated deterministically where possible
4. **Timestamp required** - All records must have a timestamp field
5. **Action tracking** - All risky actions require governance decision records

### Validation at Load Time

Loaders should:

1. **Skip corrupted records** - Don't crash on bad JSON
2. **Use defaults for missing fields** - Backwards compatibility
3. **Log warnings** - Alert operators to issues
4. **Return latest record** - For entities with multiple records

---

## Contact

For schema questions or migration support, contact the system administrator.

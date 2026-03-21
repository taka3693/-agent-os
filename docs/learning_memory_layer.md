# Learning Memory Layer

**Version:** 1.0.0  
**Status:** ACTIVE  
**Layer Type:** Insight-only (NO execution authority)

---

## Purpose

The Learning Memory Layer captures completed improvement episodes and generates structured learning insights for future operator/agent decisions.

**Key Principle:** This layer provides **insights only**. It has **NO execution authority** and cannot apply patches, modify repository state, or influence runtime decisions automatically.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Learning Memory Layer                   │
│                                                      │
│  ┌──────────────┐  ┌───────────────┐  ┌───────────┐ │
│  │ Episode Store │→│  Classifier   │→│  Insight  │ │
│  │               │  │               │  │  Report   │ │
│  └──────────────┘  └───────────────┘  └───────────┘ │
│         ↑                  ↑                ↑        │
│         │                  │                │        │
│  ┌──────┴──────────────────┴────────────────┴──────┐│
│  │         READ-ONLY Access to State              ││
│  └────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

---

## Modules

### 1. Episode Store (`learning/episode_store.py`)

**Purpose:** Capture and store improvement episodes.

**Key Functions:**
- `record_episode_from_apply_plan(apply_plan_id)` - Record episode from apply plan
- `load_learning_episodes()` - Load all episodes
- `get_episode_by_id(episode_id)` - Get specific episode
- `get_episodes_by_apply_plan(apply_plan_id)` - Get episodes for apply plan

### 2. Outcome Classifier (`learning/outcome_classifier.py`)

**Purpose:** Classify episode outcomes into conservative taxonomy.

**Key Functions:**
- `classify_episode_outcome(episode_id)` - Classify single episode
- `get_latest_classification(episode_id)` - Get latest classification for episode
- `get_outcome_statistics()` - Get outcome distribution stats
- `classify_all_episodes()` - Classify all unclassified episodes

### 3. Insight Report (`learning/insight_report.py`)

**Purpose:** Generate structured learning insights.

**Key Functions:**
- `generate_learning_insights()` - Generate insights from episodes
- `load_learning_insights()` - Load all insights
- `get_latest_insights()` - Get most recent insights
- `get_similar_past_episodes(...)` - Retrieve similar episodes

---

## Episode Schema

```json
{
  "episode_id": "string (16 chars)",
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
  "final_operator_action": "string (derived)",
  "revert_candidate_created": "boolean",
  "failure_codes": ["string"],
  "time_to_close_minutes": "number (optional)",
  "stale_flag": "boolean",
  "evidence_refs": ["string"],
  "created_at": "string (ISO 8601)",
  "outcome": "string (optional, added after classification)",
  "classification_reason": "string (optional)",
  "classification_confidence": "string (optional)",
  "classification_factors": ["string"] (optional),
  "classified_at": "string (ISO 8601, optional)"
}
```

**Note:** Classification fields are added when the episode is classified. Multiple records may exist for the same `episode_id` - use the latest (last in file) for current classification.

---

## Outcome Taxonomy

| Outcome | Description |
|---------|-------------|
| `success_clean` | Verification passed, policy approved, governance allowed |
| `success_high_friction` | Success but required multiple attempts or approvals |
| `blocked_by_governance` | Governance denied action |
| `failed_verification` | Verification failed |
| `rejected_low_confidence` | Policy rejected with low confidence |
| `stale_abandoned` | Plan became stale before completion |
| `revert_recommended` | Revert candidate was created |

---

## Insight Generation

### Pattern Types Detected

1. **Repeated verification failures** by patch type or target area
2. **Repeated governance denials** by reason
3. **Repeated stale/manual bottlenecks**
4. **Repeated revert recommendations**
5. **Repeated ambiguous/incomplete states**

### Insight Structure

```json
{
  "insight_id": "string",
  "generated_at": "string (ISO 8601)",
  "patterns": [
    {
      "type": "repeated_verification_failures",
      "dimension": "patch_type",
      "value": "python_code",
      "count": 5,
      "episodes": ["id1", "id2"],
      "common_failure_codes": ["SYNTAX_ERROR"]
    }
  ],
  "recommendations": [
    {
      "pattern_type": "repeated_verification_failures",
      "recommendation": "Review verification process for python_code changes",
      "priority": "medium",
      "automatic": false
    }
  ],
  "statistics": {
    "total_episodes": 10,
    "by_outcome": {"success_clean": 5, "failed_verification": 3},
    "pattern_count": 2,
    "recommendation_count": 2
  },
  "note": "Insights are recommendations only. No automatic execution."
}
```

---

## Similar Episode Retrieval

Retrieval uses conservative matching on:
- Patch type
- Target area
- Failure codes
- Governance outcome
- Verification outcome

**No vector similarity or heavyweight infrastructure.**

---

## State Files

| File | Purpose |
|------|---------|
| `state/learning_episodes.jsonl` | Episode records + classification (append-only) |
| `state/learning_insights.jsonl` | Insight records (append-only) |

**Note:** Classification is stored directly in `learning_episodes.jsonl` to minimize state files.

---

## Safety Guarantees

### NO Execution Authority

The Learning Memory Layer:
- ✅ Can READ from all state files
- ✅ Can WRITE to learning state files (append-only)
- ❌ Cannot apply patches
- ❌ Cannot modify repository state
- ❌ Cannot influence runtime decisions automatically
- ❌ Cannot execute any actions

### Insight-Only Design

All outputs are **recommendations only**:
- Patterns detected → informational
- Recommendations generated → require manual action
- Similar episodes retrieved → for operator review

### No Automatic Modification

The learning layer:
- Does NOT auto-tune policy
- Does NOT auto-adjust governance
- Does NOT auto-modify execution parameters
- Does NOT auto-trigger any actions

---

## Usage Examples

### Record Episode

```python
from learning.episode_store import record_episode_from_apply_plan

episode = record_episode_from_apply_plan("apply_plan_abc123")
print(f"Episode recorded: {episode['episode_id']}")
```

### Classify Outcome

```python
from learning.outcome_classifier import classify_episode_outcome

classification = classify_episode_outcome("episode_id")
print(f"Outcome: {classification['outcome']}")
print(f"Reason: {classification['reason']}")
```

### Generate Insights

```python
from learning.insight_report import generate_learning_insights

insights = generate_learning_insights()
for pattern in insights["patterns"]:
    print(f"Pattern: {pattern['type']}")
    print(f"Count: {pattern['count']}")
```

### Get Similar Episodes

```python
from learning.insight_report import get_similar_past_episodes

similar = get_similar_past_episodes(
    patch_type="python_code",
    failure_codes=["SYNTAX_ERROR"],
    limit=5,
)

for match in similar:
    print(f"Score: {match['similarity_score']}")
    print(f"Reasons: {match['match_reasons']}")
```

---

## Integration Points

The Learning Memory Layer integrates with:

| Layer | Integration Type |
|-------|------------------|
| Apply Lifecycle | READ apply plans, verifications, transitions |
| Policy | READ policy decisions |
| Governance | READ governance decisions |
| Audit | READ operational reports |
| Manual Ops | Provide insights for operator decisions |

---

## Constraints

### Must NOT

- Execute any patches or changes
- Modify repository state
- Auto-tune policy or governance
- Trigger automatic actions
- Mutate existing records

### Must

- Use append-only state design
- Be read-only to execution state
- Generate insights only
- Require manual action for all recommendations

---

**Document Status:** ACTIVE  
**Review Frequency:** After pilot operation

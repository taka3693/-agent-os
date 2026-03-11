# Agent-OS Policy Evolution System

**Operational Documentation for Production Deployment**

---

## 1. Overview

The Agent-OS Policy Evolution System is a governance framework for safely managing the lifecycle of policy rules from proposal through promotion, rollback, and retirement.

### Purpose

| Objective | Description |
|-----------|-------------|
| **Rule Governance** | Complete lifecycle tracking from candidate to retired |
| **Policy Evolution** | Systematic management of policy changes with rollback support |
| **Safe Automation** | Low-risk rules can be auto-promoted; high-risk rules require human review |
| **Human Oversight** | Critical decisions always require human confirmation |

### Design Principles

1. **Explainability** - Every decision has documented reasons
2. **Auditability** - Full history of all changes and decisions
3. **Safety** - High-risk changes are never auto-promoted
4. **Transparency** - All system state is exportable

---

## 2. System Status

| Metric | Value |
|--------|-------|
| Implementation | Complete (Steps 114-123) |
| Test Coverage | 808 PASS / 0 FAIL |
| Status | Production Ready |

---

## 3. System Architecture

### Pipeline Flow

```
policy rule
      ↓
  provenance
      ↓
   lineage
      ↓
conflict detection
      ↓
bundle evaluation
      ↓
 policy health
      ↓
 review queue
      ↓
 auto evolution
      ↓
explainable decision
      ↓
 governance layer
```

### Module Dependencies

| Step | Module | Purpose |
|------|--------|---------|
| 114 | Provenance | Track rule origin and metadata |
| 115 | Lineage | Build rule family trees |
| 116 | Conflicts | Detect rule incompatibilities |
| 117 | Bundle | Evaluate rule combinations |
| 118 | Health | Score overall system health |
| 119 | Review Queue | Prioritize human review |
| 120 | Auto Evolution | Safe automated decisions |
| 121 | E2E Validation | Integration testing |
| 122 | Explanations | Human-readable decision reports |
| 123 | Governance | Operational policy layer |

---

## 4. Pipeline Stages

### Stage 1: Provenance

Records rule origin and metadata.

```python
provenance = make_provenance(
    rule_id="rule-001",
    source_candidate_rule_id="cand-001",
    source_regression_case_ids=["case-1", "case-2"],
    source_benchmark_snapshot="bench-001",
    created_by="auto_generation",
    rule_version=1,
)
```

### Stage 2: Lineage

Tracks rule evolution and parent-child relationships.

```python
graph = build_policy_lineage_graph(registry)
tree = render_policy_lineage_tree(registry)
```

### Stage 3: Conflict Detection

Identifies rule incompatibilities.

```python
conflicts = detect_rule_conflicts(registry)
report = build_conflict_report(registry)
```

### Stage 4: Bundle Evaluation

Assesses rule combination effects.

```python
result = evaluate_rule_bundle(["rule-1", "rule-2"], registry)
```

### Stage 5: Policy Health

Scores system health (0-100, grades A-F).

```python
health = compute_policy_health(registry)
```

### Stage 6: Review Queue

Prioritizes rules needing human review.

```python
queue = build_review_queue(registry)
```

### Stage 7: Auto Evolution

Makes safe automated decisions.

```python
report = run_controlled_auto_evolution(registry)
```

### Stage 8: Explainable Report

Generates human-readable explanations.

```python
explanations = build_explainable_decision_report(registry)
```

### Stage 9: Governance Layer

Applies operational governance policy.

```python
governance = build_operational_governance_policy()
metrics = compute_operational_metrics_report(registry)
```

---

## 5. Decision Model

### Decision Types

| Decision | Description | Auto-Action |
|----------|-------------|-------------|
| `auto_promote` | Safe to promote automatically | Can auto-promote |
| `review_required` | Needs human review | Wait for approval |
| `halt` | Critical issue detected | Block all automation |
| `rollback_recommended` | Should be rolled back | Wait for confirmation |
| `reject` | Not suitable for adoption | Discard |
| `no_action` | Already handled | No further action |

### Decision Criteria

**auto_promote triggers:**
- Complete provenance
- No high-severity conflicts
- No rollback lineage reintroduction
- No harmful bundle interactions
- Health score acceptable

**review_required triggers:**
- Medium-severity conflicts present
- Harmful bundle involvement
- Deep lineage (depth > 3)
- Multiple no-added-value bundles

**halt triggers:**
- High-severity conflicts detected
- Rollback lineage reintroduction
- Broken lineage (missing parent)
- Health score below threshold (50)

**rollback_recommended triggers:**
- Adopted rule with multiple harmful bundles
- Contributing to health degradation

**reject triggers:**
- Missing provenance

**no_action triggers:**
- Already rolled back

---

## 6. Governance Roles

### Role Definitions

#### policy_maintainer

| Attribute | Value |
|-----------|-------|
| Responsibilities | Review policy changes, approve low-risk adoptions, monitor health trends |
| Can Approve | `review_required → adopted`, low-risk promotions |
| Can Block | Unsafe promotions, rules without provenance |
| Review Scope | Policy evolution and maintenance |

#### safety_reviewer

| Attribute | Value |
|-----------|-------|
| Responsibilities | Review high-risk changes, approve rollbacks, assess conflict severity |
| Can Approve | `rollback_recommended` decisions, `halt → review_required` transitions |
| Can Block | Any promotion on safety grounds |
| Review Scope | Safety-critical policy decisions |

#### system_auditor

| Attribute | Value |
|-----------|-------|
| Responsibilities | Audit evolution history, verify compliance, investigate anomalies |
| Can Approve | Audit reports, compliance certifications |
| Can Block | Non-compliant promotions, changes without audit trail |
| Review Scope | Governance compliance and audit |

#### operator

| Attribute | Value |
|-----------|-------|
| Responsibilities | Execute approved promotions, monitor health, escalate issues |
| Can Approve | Routine maintenance operations |
| Can Block | Operations during unstable periods |
| Review Scope | Day-to-day operations |

### Role Hierarchy

```
safety_reviewer  ─┐
                  ├── [highest authority for safety decisions]
system_auditor   ─┘
        │
        ▼
policy_maintainer
        │
        ▼
    operator
```

---

## 7. Promotion Guardrails

### Guardrail Definitions

#### no_auto_promote_without_provenance

| Attribute | Value |
|-----------|-------|
| Condition | Provenance missing or incomplete |
| Action | Reject `auto_promote`, require `review_required` or `reject` |
| Rationale | Rules without provenance cannot be safely tracked or audited |

#### no_auto_promote_on_high_conflict

| Attribute | Value |
|-----------|-------|
| Condition | High severity conflict present |
| Action | Halt `auto_promote`, require `halt` decision |
| Rationale | High severity conflicts indicate unsafe rule interactions |

#### no_auto_promote_on_rollback_lineage

| Attribute | Value |
|-----------|-------|
| Condition | Rollback lineage reintroduction detected |
| Action | Halt `auto_promote`, require `halt` decision |
| Rationale | Rules from rolled-back lineages have known issues |

#### no_auto_promote_on_harmful_bundle

| Attribute | Value |
|-----------|-------|
| Condition | Harmful bundle interaction detected |
| Action | Block `auto_promote`, require `review_required` |
| Rationale | Harmful interactions can cause unintended degradation |

#### promoted_requires_human_review

| Attribute | Value |
|-----------|-------|
| Condition | Rule transition to `promoted` status |
| Action | Require human approval before promotion |
| Rationale | Promotions affect production policy |

#### halt_cannot_auto_clear

| Attribute | Value |
|-----------|-------|
| Condition | Rule in `halt` state |
| Action | Require explicit human action to clear |
| Rationale | Halt indicates serious issues requiring investigation |

#### rollback_requires_confirmation

| Attribute | Value |
|-----------|-------|
| Condition | `rollback_recommended` decision |
| Action | Require human confirmation before execution |
| Rationale | Rollbacks have significant impact |

#### low_risk_only_for_auto_promote

| Attribute | Value |
|-----------|-------|
| Condition | `risk_level` is not `low` |
| Action | Require `review_required` for medium/high risk |
| Rationale | Only low-risk rules are candidates for automatic promotion |

### Guardrail Enforcement

```python
# All guardrails are enforced by evaluate_auto_evolution_candidate()
decision = evaluate_auto_evolution_candidate(rule_id, registry)

# Guardrails prevent auto_promote when conditions are met
if decision["decision"] != "auto_promote":
    print(f"Blocked by guardrail: {decision['reasons']}")
```

---

## 8. Operational Metrics

### Metric Definitions

#### health_score_trend

| Attribute | Value |
|-----------|-------|
| Description | Tracks policy health score over time |
| Interpretation | Falling trend indicates policy degradation |
| Risk Signal | Medium |
| Calculation | Compare `health_score` across time periods |

#### conflict_rate

| Attribute | Value |
|-----------|-------|
| Description | Ratio of rules with detected conflicts |
| Interpretation | High rate indicates policy inconsistency |
| Risk Signal | High |
| Calculation | `rules_with_conflicts / total_rules` |

#### rollback_rate

| Attribute | Value |
|-----------|-------|
| Description | Ratio of rolled-back rules to total adopted |
| Interpretation | High rate suggests quality issues |
| Risk Signal | High |
| Calculation | `rolled_back_rules / total_adopted_rules` |

#### auto_promote_ratio

| Attribute | Value |
|-----------|-------|
| Description | Ratio of `auto_promote` decisions |
| Interpretation | Too high may indicate lax criteria |
| Risk Signal | Low |
| Calculation | `auto_promote_count / total_decisions` |

#### review_required_ratio

| Attribute | Value |
|-----------|-------|
| Description | Ratio of `review_required` decisions |
| Interpretation | Indicates human review workload |
| Risk Signal | Medium |
| Calculation | `review_required_count / total_decisions` |

#### halt_ratio

| Attribute | Value |
|-----------|-------|
| Description | Ratio of `halt` decisions |
| Interpretation | High ratio indicates systemic issues |
| Risk Signal | High |
| Calculation | `halt_count / total_decisions` |

#### harmful_bundle_ratio

| Attribute | Value |
|-----------|-------|
| Description | Ratio of rules in harmful bundle interactions |
| Interpretation | Indicates rule interaction quality |
| Risk Signal | High |
| Calculation | `rules_in_harmful_bundles / total_rules` |

#### provenance_completeness

| Attribute | Value |
|-----------|-------|
| Description | Ratio of rules with complete provenance |
| Interpretation | Low completeness indicates audit issues |
| Risk Signal | Medium |
| Calculation | `rules_with_provenance / total_rules` |

### Computing Metrics

```python
# Get current metric values
report = compute_operational_metrics_report(registry)

for metric_name, value in report["metrics"].items():
    print(f"{metric_name}: {value}")
```

---

## 9. Standard Operating Procedures

### Daily Operations

1. **Check Health Score**
   ```python
   health = compute_policy_health(registry)
   if health["health_score"] < 80:
       alert(f"Health score low: {health['health_score']}")
   ```

2. **Review High-Priority Queue**
   ```python
   queue = build_review_queue(registry)
   for item in queue["review_queue"]:
       if item["priority_level"] == "high":
           assign_for_review(item["rule_id"])
   ```

### Weekly Operations

1. **Generate Governance Report**
   ```python
   registry.export(
       fmt="json",
       include_governance=True,
       include_health=True,
       include_review_queue=True,
   )
   ```

2. **Review Halt Decisions**
   ```python
   report = run_controlled_auto_evolution(registry)
   for item in report["auto_evolution"]:
       if item["decision"] == "halt":
           investigate(item["rule_id"])
   ```

### Monthly Operations

1. **Full System Audit**
   ```python
   # Export everything
   registry.export(
       include_lineage=True,
       include_conflicts=True,
       include_bundle_eval=True,
       include_health=True,
       include_review_queue=True,
       include_auto_evolution=True,
       include_explanations=True,
       include_governance=True,
   )
   ```

2. **Review Operational Metrics Trends**
   ```python
   metrics = compute_operational_metrics_report(registry)
   compare_with_previous_month(metrics)
   ```

---

## 10. Export Options

### Available Options

| Option | Description |
|--------|-------------|
| `include_lineage` | Policy lineage graph |
| `include_conflicts` | Conflict detection report |
| `include_bundle_eval` | Bundle evaluation results |
| `include_health` | Health score and breakdown |
| `include_review_queue` | Prioritized review queue |
| `include_auto_evolution` | Auto-evolution decisions |
| `include_explanations` | Explainable decision reports |
| `include_governance` | Governance policy and metrics |

### Usage Example

```python
# Full export
exported = registry.export(
    fmt="json",
    include_lineage=True,
    include_conflicts=True,
    include_bundle_eval=True,
    include_health=True,
    include_review_queue=True,
    include_auto_evolution=True,
    include_explanations=True,
    include_governance=True,
)

# Save to file
registry.save(Path("policy_state.json"))
```

---

## 11. Safety Principles

### Core Safety Rules

1. **No Auto-Promote Without Provenance**
   - Rules must have complete metadata before automation

2. **High Conflicts Always Block**
   - High-severity conflicts prevent all automation

3. **Rollback Lineage = Halt**
   - Rules from rolled-back families are automatically halted

4. **Human Approval for Promotions**
   - Production promotions require explicit human confirmation

5. **Halt Cannot Auto-Clear**
   - Only humans can clear a halt state

6. **Rollbacks Need Confirmation**
   - Rollback actions require human approval

### Conservative Bias

When uncertain, the system defaults to safer decisions:
- `review_required` over `auto_promote`
- `halt` over `review_required` for critical issues
- Human confirmation over automatic action

---

## 12. Policy CI Pipeline (Step 124)

### Purpose

The CI Pipeline provides automated policy evaluation for integration workflows.

### Pipeline Flow

```
candidate rules
       ↓
existing evaluation pipeline
       ↓
governance judgment
       ↓
CI Gate decision
       ↓
result report
```

### CI Gate Status

| Status | Condition |
|--------|-----------|
| `pass` | All checks pass, safe to merge |
| `warning` | Non-blocking issues, review recommended |
| `fail` | Blocking issues found, merge blocked |

### Fail Conditions

| Condition | Description |
|-----------|-------------|
| HALT decision | Auto-evolution returned HALT |
| Missing provenance | Rule lacks required metadata |
| High severity conflict | Dangerous rule interaction detected |
| Harmful bundle | Bundle evaluation found harmful interaction |
| Guardrail violation | Promotion guardrail triggered |

### Warning Conditions

| Condition | Description |
|-----------|-------------|
| REVIEW_REQUIRED | Rule needs human review |
| Health score drop | Minor health degradation |
| Medium conflict | Non-critical conflict detected |

### Pass Conditions

- Complete provenance
- No high-severity conflicts
- No harmful bundle interactions
- No governance blocks
- Health score acceptable

### Usage

```python
from eval.ci_pipeline import run_policy_ci_pipeline, summarize_policy_ci_result

# Evaluate candidates
result = run_policy_ci_pipeline(
    candidate_rules=[
        {"rule_id": "rule-001", "provenance": {...}, ...}
    ],
    existing_registry=registry,
)

# Check status
if result["overall_status"] == "pass":
    print("Safe to merge")
elif result["overall_status"] == "fail":
    for reason in result["blocking_reasons"]:
        print(f"Blocked: {reason}")

# Get human-readable summary
summary = summarize_policy_ci_result(result)
print(summary)
```

### CI Result Structure

```json
{
  "overall_status": "pass | warning | fail",
  "decision_summary": {...},
  "health_summary": {...},
  "review_queue_summary": {...},
  "governance_summary": {...},
  "candidate_results": [...],
  "blocking_reasons": [...],
  "warnings": [...],
  "report": {...}
}
```

### Helper Functions

| Function | Purpose |
|----------|---------|
| `get_ci_gate_status()` | Get pass/warning/fail status |
| `is_ci_gate_blocked()` | Check if gate is blocked |
| `get_blocking_reasons()` | Get list of blocking reasons |
| `get_warnings()` | Get list of warnings |
| `export_ci_result_json()` | Export result as JSON |
| `evaluate_single_candidate()` | Evaluate one candidate |

---

## 13. Implementation Summary

| Step | Feature | Tests |
|------|---------|-------|
| 114 | Provenance Tracking | 25+ |
| 115 | Lineage Visualization | 20+ |
| 116 | Conflict Detection | 25+ |
| 117 | Bundle Evaluation | 15+ |
| 118 | Policy Health Scoring | 20+ |
| 119 | Auto-Review Queue | 22+ |
| 120 | Controlled Auto-Evolution | 25+ |
| 121 | E2E Integration Tests | 5+ |
| 122 | Explainable Reports | 23+ |
| 123 | Operational Governance | 27+ |
| 124 | Policy CI Pipeline | 27+ |

**Total: 835 tests, all passing**

---

## 14. Current System State

### Test Status

```
Ran 835 tests
OK
```

### Implementation Files

| File | Purpose |
|------|---------|
| `eval/candidate_rules.py` | Core implementation (Steps 114-123) |
| `eval/ci_pipeline.py` | CI Pipeline (Step 124) |
| `tests/test_step114_*.py` - `tests/test_step124_*.py` | Test suites |
| `docs/policy_evolution_system.md` | This document |

### Key APIs

```python
# Core registry
registry = AdoptionRegistry()

# Pipeline stages
make_provenance(...)
build_policy_lineage_graph(registry)
detect_rule_conflicts(registry)
evaluate_rule_bundle(rule_ids, registry)
compute_policy_health(registry)
build_review_queue(registry)
run_controlled_auto_evolution(registry)
build_explainable_decision_report(registry)

# Governance
build_operational_governance_policy()
compute_operational_metrics_report(registry)

# CI Pipeline (Step 124)
run_policy_ci_pipeline(candidates, existing_registry)
summarize_policy_ci_result(ci_result)
get_ci_gate_status(ci_result)

# Export
registry.export(include_governance=True, ...)
```

---

## References

- Tests: `tests/test_step114_provenance.py` through `tests/test_step124_policy_ci_pipeline.py`
- Implementation: `eval/candidate_rules.py`, `eval/ci_pipeline.py`
- E2E Tests: `tests/test_step121_policy_evolution_e2e.py`

---

**Last Updated**: 2026-03-11  
**Test Status**: 835 PASS / 0 FAIL  
**System Status**: Production Ready

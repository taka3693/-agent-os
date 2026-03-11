# Agent-OS Operations Runbook

**Operational procedures for the Policy Evolution System**

---

## 1. Purpose

### Objective

This runbook provides operational procedures for managing the Agent-OS Policy Evolution System. It covers daily operations, incident response, and governance workflows.

### Scope

| Component | Coverage |
|-----------|----------|
| Policy Evolution Engine | Steps 114-123 |
| Policy CI Pipeline | Step 124 |
| Governance Layer | Role-based procedures |
| Operational Monitoring | Metrics and alerts |

### Responsibilities

| Role | Primary Responsibility |
|------|----------------------|
| Operator | Daily operations and monitoring |
| Policy Maintainer | Rule review and promotion |
| Safety Reviewer | High-risk decision approval |
| System Auditor | Compliance and audit |

---

## 2. System Overview

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent-OS System                          │
├─────────────────────────────────────────────────────────────┤
│  Execution Engine                                           │
│       ↓                                                     │
│  Policy Evolution Engine                                    │
│       ↓                                                     │
│  Governance Layer                                           │
│       ↓                                                     │
│  Policy CI Pipeline                                         │
└─────────────────────────────────────────────────────────────┘
```

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
  governance
      ↓
   CI Gate
      ↓
┌─────────────┐
│   PASS      │ → Safe to merge
│   WARNING   │ → Review required
│   FAIL      │ → Blocked
└─────────────┘
```

### CI Pipeline Output

| Field | Description |
|-------|-------------|
| `overall_status` | pass / warning / fail |
| `blocking_reasons` | List of failure reasons |
| `warnings` | List of non-blocking issues |
| `candidate_results` | Per-candidate evaluation |
| `report` | Detailed evaluation data |

---

## 3. CI Result Interpretation

### Overall Status Values

#### PASS

**Meaning**: All governance checks passed. Candidate is safe to merge.

**Indicators**:
- Complete provenance
- No conflicts
- No harmful bundles
- Health score acceptable
- Auto-evolution decision: `auto_promote`

**Action**: Proceed with merge.

```python
if result["overall_status"] == "pass":
    # Safe to merge
    proceed_with_promotion()
```

#### WARNING

**Meaning**: Non-blocking issues detected. Human review recommended.

**Indicators**:
- `review_required` decision
- Minor health score concerns
- Medium severity conflicts
- Governance warnings

**Action**: Review required before proceeding.

```python
if result["overall_status"] == "warning":
    # Review needed
    assign_to_review_queue()
    notify_policy_maintainer()
```

#### FAIL

**Meaning**: Blocking issues detected. Merge prohibited.

**Indicators**:
- `halt` decision
- Missing provenance
- High severity conflicts
- Harmful bundle interactions
- Guardrail violations

**Action**: Must resolve blocking issues before merge.

```python
if result["overall_status"] == "fail":
    # Blocked
    for reason in result["blocking_reasons"]:
        log_blocking_reason(reason)
    notify_safety_reviewer()
```

### Blocking Reasons Reference

| Reason | Severity | Resolution |
|--------|----------|------------|
| Missing provenance | FAIL | Add complete provenance |
| HALT decision | FAIL | Investigate root cause |
| High severity conflict | FAIL | Resolve conflict |
| Harmful bundle | FAIL | Modify rule or reject |
| Guardrail violation | FAIL | Address violation |

---

## 4. Daily Operations

### Morning Checklist

```
□ Review overnight CI pipeline results
□ Check review queue for high-priority items
□ Verify system health score > 70
□ Review any governance alerts
□ Check metrics dashboard
```

### Task 1: Review Queue Check

```python
from eval.candidate_rules import build_review_queue, AdoptionRegistry

registry = AdoptionRegistry()
queue = build_review_queue(registry)

for item in queue["review_queue"]:
    if item["priority_level"] == "high":
        # Immediate attention required
        notify_policy_maintainer(item["rule_id"])
```

### Task 2: CI Pipeline Results

```bash
# Check latest CI results
cat /var/log/agent-os/ci_results/latest.json | jq '.overall_status'

# List failures
cat /var/log/agent-os/ci_results/latest.json | jq '.blocking_reasons'
```

### Task 3: Governance Alerts

```python
from eval.ci_pipeline import run_policy_ci_pipeline

# Check for any governance issues
result = run_policy_ci_pipeline([])  # Empty = system check

if result["governance_summary"]["high_severity_conflicts"] > 0:
    alert("High severity conflicts detected")
```

### Task 4: Metrics Monitoring

Monitor these metrics daily:

| Metric | Threshold | Action if Exceeded |
|--------|-----------|-------------------|
| health_score | < 70 | Investigate degradation |
| conflict_rate | > 0.2 | Review new rules |
| rollback_rate | > 0.1 | Quality review |
| halt_ratio | > 0.05 | Root cause analysis |

---

## 5. Promotion Workflow

### Standard Promotion Flow

```
┌─────────────────┐
│ Candidate Rule  │
└────────┬────────┘
         ↓
┌─────────────────┐
│ CI Evaluation   │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Governance      │
│ Review          │
└────────┬────────┘
         ↓
┌─────────────────┐
│ Promotion       │
│ Decision        │
└────────┬────────┘
         ↓
┌────────┬────────┐
│        │        │
▼        ▼        ▼
PROMOTE  REVIEW  REJECT
```

### Decision Outcomes

#### auto_promote

**Criteria**:
- Complete provenance
- No conflicts
- No harmful bundles
- Low risk level
- Health score acceptable

**Action**: Automatic promotion allowed.

```python
if decision == "auto_promote":
    promote_rule(rule_id)
    log_promotion(rule_id, reason="auto_promote")
```

#### review_required

**Criteria**:
- Medium severity conflicts
- Harmful bundle potential
- Deep lineage
- Medium risk level

**Action**: Assign to policy_maintainer for review.

```python
if decision == "review_required":
    assign_review(rule_id, role="policy_maintainer")
    notify_reviewer(rule_id)
```

#### reject

**Criteria**:
- Missing provenance
- Invalid rule structure
- Fundamental issues

**Action**: Reject with explanation.

```python
if decision == "reject":
    reject_rule(rule_id, reasons=decision["reasons"])
    notify_submitter(rule_id, status="rejected")
```

#### halt

**Criteria**:
- High severity conflicts
- Rollback lineage reintroduction
- Critical governance issues

**Action**: Block immediately, escalate.

```python
if decision == "halt":
    block_rule(rule_id)
    escalate_to_safety_reviewer(rule_id)
    create_incident(rule_id, severity="high")
```

---

## 6. Handling CI Failures

### Immediate Response

1. **Identify blocking reasons**
   ```python
   for reason in result["blocking_reasons"]:
       print(f"BLOCKED: {reason}")
   ```

2. **Classify the failure**
   ```python
   if "provenance" in reason.lower():
       category = "missing_provenance"
   elif "conflict" in reason.lower():
       category = "conflict"
   elif "bundle" in reason.lower():
       category = "harmful_bundle"
   elif "halt" in reason.lower():
       category = "governance_halt"
   ```

3. **Assign to appropriate role**

### Failure Categories

#### Missing Provenance

**Symptoms**: `Missing provenance for rule-xxx`

**Resolution**:
1. Contact rule submitter
2. Request provenance information
3. Add provenance metadata
4. Re-run CI pipeline

```python
# Fix provenance
rule["provenance"] = make_provenance(
    rule_id=rule_id,
    source_candidate_rule_id=source_id,
    source_regression_case_ids=case_ids,
    created_by="manual_fix",
)
```

#### Harmful Bundle

**Symptoms**: `Harmful bundle interaction between rule-xxx and rule-yyy`

**Resolution**:
1. Analyze bundle interaction
2. Determine if rules are compatible
3. Modify one or both rules
4. Or reject one rule

```python
# Analyze bundle
bundle = evaluate_rule_bundle([rule_a, rule_b], registry)
print(f"Harmful: {bundle['harmful_interaction']}")
print(f"Delta: {bundle['delta_vs_best_individual']}")
```

#### High Conflict

**Symptoms**: `High severity conflict for rule-xxx: conflict_type`

**Resolution**:
1. Identify conflict type
2. Analyze conflicting rules
3. Resolve or escalate

```python
conflicts = detect_rule_conflicts(registry)
high_conflicts = [c for c in conflicts if c["severity"] == "high"]
for c in high_conflicts:
    print(f"Conflict: {c['type']} between {c['rule_ids']}")
```

#### Governance Halt

**Symptoms**: `HALT decision for rule-xxx`

**Resolution**:
1. Escalate to safety_reviewer
2. Root cause analysis
3. Governance review
4. Clear or maintain halt

---

## 7. Review Required Workflow

### Trigger Conditions

- CI status: `warning`
- Auto-evolution decision: `review_required`

### Review Process

```
┌──────────────────────┐
│ Review Queue Item    │
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ policy_maintainer    │
│ Initial Review       │
└──────────┬───────────┘
           ↓
    ┌──────┴──────┐
    │             │
    ▼             ▼
┌───────┐   ┌──────────┐
│ LOW   │   │ MEDIUM+  │
│ RISK  │   │ RISK     │
└───┬───┘   └────┬─────┘
    │            ↓
    │     ┌──────────────┐
    │     │ safety_      │
    │     │ reviewer     │
    │     └──────┬───────┘
    │            │
    └─────┬──────┘
          ↓
    ┌─────┴─────┐
    │           │
    ▼           ▼
 PROMOTE     REJECT
```

### Review Checklist

```
□ Check provenance completeness
□ Review conflict status
□ Evaluate bundle interactions
□ Assess risk level
□ Verify health impact
□ Document decision rationale
```

### Approval Commands

```python
# After review, approve
from eval.candidate_rules import AdoptionRegistry

registry = AdoptionRegistry()
registry.adopt(candidate, approved_by="policy_maintainer")

# Or reject
reject_rule(rule_id, reason="Review rejection", reviewer="policy_maintainer")
```

---

## 8. Rollback Procedure

### When to Rollback

- `rollback_recommended` decision
- Post-deployment issue detected
- Safety concern identified

### Rollback Steps

#### Step 1: Lineage Verification

```python
from eval.candidate_rules import get_rule_lineage

lineage = get_rule_lineage(rule_id, registry)
print(f"Lineage depth: {len(lineage)}")

# Check for dependents
graph = build_policy_lineage_graph(registry)
dependents = [n for n in graph["nodes"] if n.get("parent_rule_id") == rule_id]
```

#### Step 2: Conflict Check

```python
conflicts = detect_rule_conflicts(registry)
rule_conflicts = [c for c in conflicts if rule_id in c.get("rule_ids", [])]
```

#### Step 3: Execute Rollback

```python
registry.rollback(rule_id, rolled_back_by="operator", reason="Documented reason")
```

#### Step 4: Audit Record

```python
audit_record = {
    "action": "rollback",
    "rule_id": rule_id,
    "performed_by": "operator",
    "reason": "...",
    "timestamp": datetime.now().isoformat(),
    "lineage": lineage,
    "conflicts": rule_conflicts,
}
save_audit_record(audit_record)
```

### Post-Rollback

1. Verify rule is inactive
2. Check dependent rules for impact
3. Update documentation
4. Notify stakeholders

---

## 9. Halt Investigation

### Immediate Actions

1. **Acknowledge halt**
   ```python
   log_halt(rule_id, decision["reasons"])
   ```

2. **Notify safety_reviewer**
   ```python
   notify_safety_reviewer(rule_id, severity="high")
   ```

3. **Create investigation ticket**

### Investigation Checklist

```
□ Identify halt trigger
  - High conflict?
  - Rollback lineage?
  - Guardrail violation?
  - Health threshold?

□ Analyze root cause
  - Rule content
  - Interactions
  - Governance context

□ Determine resolution
  - Fix rule
  - Reject rule
  - Governance exception (rare)

□ Document findings
```

### Root Cause Categories

| Trigger | Investigation Focus |
|---------|-------------------|
| High conflict | Rule interaction analysis |
| Rollback lineage | Family tree review |
| Broken lineage | Parent rule status |
| Health threshold | System-wide issues |

### Resolution Process

```python
# After investigation, either:
# 1. Clear halt (requires safety_reviewer approval)
clear_halt(rule_id, approved_by="safety_reviewer", rationale="...")

# 2. Maintain halt and reject
reject_rule(rule_id, reason="Halt maintained: ...")
```

---

## 10. Metrics Monitoring

### Key Metrics

#### health_score_trend

| Aspect | Details |
|--------|---------|
| Description | Overall system health over time |
| Healthy Range | 80-100 (Grade A/B) |
| Warning | 70-79 (Grade C) |
| Critical | < 70 (Grade D/F) |
| Action | Investigate degradation causes |

```python
health = compute_policy_health(registry)
trend = calculate_trend(health_history)
if trend == "declining":
    alert("Health score declining")
```

#### conflict_rate

| Aspect | Details |
|--------|---------|
| Description | Ratio of rules with conflicts |
| Calculation | `rules_with_conflicts / total_rules` |
| Warning | > 0.15 |
| Critical | > 0.25 |

#### rollback_rate

| Aspect | Details |
|--------|---------|
| Description | Ratio of rolled-back rules |
| Calculation | `rolled_back / total_adopted` |
| Warning | > 0.05 |
| Critical | > 0.10 |

#### auto_promote_ratio

| Aspect | Details |
|--------|---------|
| Description | Ratio of auto-promoted decisions |
| Calculation | `auto_promote / total_decisions` |
| Expected | 0.5-0.8 |
| Too Low | < 0.3 (overly conservative?) |
| Too High | > 0.9 (too permissive?) |

#### review_required_ratio

| Aspect | Details |
|--------|---------|
| Description | Ratio of review_required decisions |
| Calculation | `review_required / total_decisions` |
| Expected | 0.1-0.3 |

#### halt_ratio

| Aspect | Details |
|--------|---------|
| Description | Ratio of halt decisions |
| Calculation | `halt / total_decisions` |
| Expected | < 0.05 |
| Warning | > 0.05 |
| Critical | > 0.10 |

#### harmful_bundle_ratio

| Aspect | Details |
|--------|---------|
| Description | Ratio of rules in harmful bundles |
| Calculation | `harmful_bundle_rules / total_rules` |
| Expected | 0 |
| Any value | Investigate immediately |

#### provenance_completeness

| Aspect | Details |
|--------|---------|
| Description | Ratio of rules with complete provenance |
| Calculation | `complete_provenance / total_rules` |
| Expected | 1.0 |
| Warning | < 0.95 |
| Critical | < 0.90 |

### Monitoring Dashboard

```python
from eval.candidate_rules import compute_operational_metrics_report

report = compute_operational_metrics_report(registry)
metrics = report["metrics"]

for name, value in metrics.items():
    print(f"{name}: {value}")
```

---

## 11. Governance Roles

### policy_maintainer

**Responsibilities**:
- Review policy change proposals
- Approve low-risk adoptions
- Monitor health trends
- Maintain documentation

**Authorities**:
- Approve: `review_required → adopted`
- Approve: Low-risk promotions
- Block: Unsafe promotions

**Escalate To**: safety_reviewer (high-risk)

### safety_reviewer

**Responsibilities**:
- Review high-risk changes
- Approve rollbacks
- Assess conflict severity
- Clear halt states

**Authorities**:
- Approve: `rollback_recommended`
- Approve: `halt → review_required`
- Block: Any promotion (safety grounds)

**Escalate To**: system_auditor (compliance issues)

### system_auditor

**Responsibilities**:
- Audit evolution history
- Verify compliance
- Investigate anomalies
- Generate audit reports

**Authorities**:
- Approve: Audit reports
- Block: Non-compliant changes

**Reports To**: Management

### operator

**Responsibilities**:
- Execute approved promotions
- Monitor system health
- Respond to alerts
- Escalate critical issues

**Authorities**:
- Approve: Routine operations
- Block: Operations during instability

**Escalate To**: policy_maintainer (review issues)

---

## 12. Audit Procedure

### Weekly Audit

**Performed by**: operator, policy_maintainer

**Checklist**:
```
□ Review CI failure log
□ Check rollback frequency
□ Verify review queue processing
□ Audit governance decisions
□ Check metrics trends
```

**Commands**:
```bash
# Weekly report
python3 -c "
from eval.candidate_rules import *
registry = load_registry()
health = compute_policy_health(registry)
queue = build_review_queue(registry)
print(f'Health: {health[\"health_score\"]}')
print(f'Review items: {queue[\"summary\"][\"total_review_items\"]}')
"
```

### Monthly Audit

**Performed by**: system_auditor

**Checklist**:
```
□ Full policy lineage review
□ Rollback pattern analysis
□ CI failure categorization
□ Governance decision audit
□ Compliance verification
□ Metrics trend analysis
□ Documentation review
```

**Report Template**:
```markdown
## Monthly Audit Report

Date: YYYY-MM-DD
Auditor: [name]

### Health Summary
- Health Score: [value]
- Grade: [A/B/C/D/F]
- Trend: [improving/stable/declining]

### Rollback Analysis
- Total Rollbacks: [count]
- Rollback Rate: [percentage]
- Root Causes: [list]

### CI Analysis
- Total Evaluations: [count]
- Pass Rate: [percentage]
- Warning Rate: [percentage]
- Fail Rate: [percentage]

### Governance Decisions
- auto_promote: [count]
- review_required: [count]
- halt: [count]
- rollback_recommended: [count]

### Findings
- [finding 1]
- [finding 2]

### Recommendations
- [recommendation 1]
- [recommendation 2]
```

---

## 13. Incident Response

### Incident: Harmful Policy Deployed

**Severity**: CRITICAL

**Immediate Actions**:
1. Identify affected rule(s)
2. Execute immediate rollback
3. Notify safety_reviewer
4. Create incident record

```python
# Immediate rollback
registry.rollback(rule_id, rolled_back_by="operator", reason="CRITICAL: Harmful deployment")

# Verify
entry = registry.get(rule_id)
assert entry["adoption_status"] == "rolled_back"
```

**Post-Incident**:
1. Root cause analysis
2. CI pipeline review
3. Governance gap analysis
4. Process improvement

### Incident: Conflict Explosion

**Severity**: HIGH

**Symptoms**: Sudden spike in conflict_rate

**Immediate Actions**:
1. Identify new conflicting rules
2. Halt new promotions
3. Analyze conflict patterns

```python
conflicts = detect_rule_conflicts(registry)
recent_conflicts = [c for c in conflicts if is_recent(c)]
print(f"Recent conflicts: {len(recent_conflicts)}")
```

**Resolution**:
1. Identify common factor
2. Resolve or reject problematic rules
3. Resume normal operations

### Incident: Governance Halt Storm

**Severity**: HIGH

**Symptoms**: Multiple halt decisions in short period

**Immediate Actions**:
1. Identify common halt triggers
2. Check system health
3. Review recent changes

```python
evolution = run_controlled_auto_evolution(registry)
halted = [e for e in evolution["auto_evolution"] if e["decision"] == "halt"]
print(f"Halted rules: {len(halted)}")

# Find common reasons
from collections import Counter
all_reasons = []
for h in halted:
    all_reasons.extend(h["reasons"])
print(Counter(all_reasons))
```

**Escalation**: Contact safety_reviewer and system_auditor

---

## 14. Operational Best Practices

### Safety Rules

1. **Never bypass CI gate**
   ```python
   # WRONG
   force_promote(rule_id)  # Never do this
   
   # RIGHT
   result = run_policy_ci_pipeline([rule])
   if result["overall_status"] != "fail":
       promote(rule_id)
   ```

2. **Never auto-promote high-risk rules**
   ```python
   # Always require review for high-risk
   if rule["risk_level"] in ["high", "critical"]:
       require_review(rule_id)
   ```

3. **Always record governance decisions**
   ```python
   # Every decision must be logged
   log_governance_decision(
       rule_id=rule_id,
       decision=decision,
       made_by="role_name",
       rationale="...",
   )
   ```

4. **Always investigate halts**
   ```python
   # Never ignore halt decisions
   if decision == "halt":
       create_investigation(rule_id)
       notify_safety_reviewer(rule_id)
   ```

### Documentation Standards

- Record all promotion decisions
- Document rollback reasons
- Maintain audit trail
- Update runbook as needed

### Communication Standards

- Alert on critical issues immediately
- Daily status updates to stakeholders
- Weekly metrics summary
- Monthly audit report

### Emergency Contacts

| Role | Contact | Escalation Time |
|------|---------|-----------------|
| Operator | [on-call] | Immediate |
| Policy Maintainer | [contact] | < 1 hour |
| Safety Reviewer | [contact] | < 30 min (critical) |
| System Auditor | [contact] | < 24 hours |

---

## Quick Reference

### CI Status Actions

| Status | Action |
|--------|--------|
| pass | Proceed with merge |
| warning | Review required |
| fail | Fix blocking issues |

### Decision Actions

| Decision | Action |
|----------|--------|
| auto_promote | Promote automatically |
| review_required | Assign to reviewer |
| reject | Reject with explanation |
| halt | Block and investigate |
| rollback_recommended | Execute rollback |

### Key Commands

```python
# Run CI pipeline
result = run_policy_ci_pipeline(candidates, registry)

# Check status
status = get_ci_gate_status(result)

# Get blocking reasons
reasons = get_blocking_reasons(result)

# Get summary
summary = summarize_policy_ci_result(result)

# Export result
json_str = export_ci_result_json(result)
```

---

**Last Updated**: 2026-03-11  
**Version**: 1.0  
**Test Status**: 835 PASS / 0 FAIL

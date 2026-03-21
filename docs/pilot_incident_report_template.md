# Pilot Incident Report Template

**Version:** 1.0.0  
**Status:** ACTIVE

Use this template when an incident occurs during pilot operation.

---

## Incident Summary

| Field | Value |
|-------|-------|
| **Incident ID** | INC-YYYY-MM-DD-NNN |
| **Date Detected** | YYYY-MM-DD |
| **Time Detected** | HH:MM |
| **Severity** | [CRITICAL / WARNING / INFO] |
| **Status** | [OPEN / INVESTIGATING / RESOLVED] |
| **Reporter** | [Name] |

---

## Description

**What happened:**
```
[Describe the incident in 2-3 sentences]
```

**How it was detected:**
```
[Describe how the incident was discovered]
```

---

## Impact Assessment

### Impacted Entities

| Entity Type | Entity ID | Status |
|-------------|-----------|--------|
| Apply Plan | | |
| Verification | | |
| Policy Decision | | |
| Governance Decision | | |

### State Files Affected

| File | Lines Affected | Notes |
|------|-----------------|-------|
| state/apply_plans.jsonl | | |
| state/apply_state_transitions.jsonl | | |
| state/post_apply_verification_results.jsonl | | |
| state/policy_decisions.jsonl | | |
| state/governance_decisions.jsonl | | |

---

## Safety Assessment

### What Was Blocked

| Action | Reason Blocked | Correct? |
|--------|---------------|----------|
| | | |

### What Remained Safe

| Safety Constraint | Status |
|-------------------|--------|
| No automatic apply | [ ] Maintained |
| No automatic rollback | [ ] Maintained |
| No automatic commit | [ ] Maintained |
| No automatic promotion | [ ] Maintained |
| Manual gates intact | [ ] Maintained |

---

## Root Cause Analysis

**Immediate cause:**
```
[What directly caused the incident]
```

**Contributing factors:**
```
[What made the incident more likely]
```

**Underlying issue:**
```
[What root issue needs to be addressed]
```

---

## Manual Remediation

| Step | Action | Time | Operator |
|------|--------|------|----------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

**Commands executed:**
```
[Paste exact remediation commands]
```

---

## Prevention Ideas

| Idea | Feasibility | Priority |
|------|-------------|----------|
| | | |

---

## Lessons Learned

1. 
2. 
3. 

---

## Resolution

**Resolution status:** [ ] Resolved [ ] Ongoing [ ] Requires redesign

**Resolution summary:**
```
[How was the incident resolved]
```

**Time to resolution:** ____ minutes

---

## Sign-off

- **Incident Closed:** [ ] Yes [ ] No
- **Reviewer:** _______________
- **Review Date:** _______________

---

**Document Status:** ACTIVE

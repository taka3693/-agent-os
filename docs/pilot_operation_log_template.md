# Pilot Operation Log Template

**Version:** 1.0.0  
**Status:** ACTIVE

Use this template to record each manual operation during pilot.

---

## Operation Record

| Field | Value |
|-------|-------|
| **Date** | YYYY-MM-DD |
| **Time** | HH:MM (start) - HH:MM (end) |
| **Duration** | minutes |
| **Operator** | [Name] |
| **Operation Type** | [APPLY / VERIFY / REVIEW / OTHER] |
| **Target** | [apply_plan_id / verification_id] |

---

## Target Information

| Field | Value |
|-------|-------|
| **Apply Plan ID** | |
| **Verification ID** | |
| **Proposal ID** | |
| **Repository** | /home/milky/agent-os |

---

## Pre-Operation State

```python
# Run and paste output
from tools.manual_ops import show_apply_plan_status
status = show_apply_plan_status("APPLY_PLAN_ID")
```

| Field | Value |
|-------|-------|
| Latest Apply State | |
| Latest Verification Status | |
| Latest Policy Decision | |
| Next Manual Action | |

---

## Actions Taken

| Step | Command | Result | Notes |
|------|---------|--------|-------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

---

## Approvals

| Approval Type | Entity ID | Approver | Reason |
|---------------|-----------|----------|--------|
| | | | |

---

## Verification Result

| Field | Value |
|-------|-------|
| Result | [PASSED / FAILED] |
| Failure Codes | |

---

## Governance Decision

| Field | Value |
|-------|-------|
| Decision | [ALLOWED / DENIED / MANUAL_APPROVAL_REQUIRED] |
| Is Allowed | [True / False] |

---

## Post-Operation State

```python
# Run and paste output
from tools.manual_ops import show_apply_plan_status
status = show_apply_plan_status("APPLY_PLAN_ID")
```

| Field | Value |
|-------|-------|
| Latest Apply State | |
| Latest Verification Status | |

---

## Anomalies

| Description | Severity | Follow-up |
|-------------|----------|----------|
| | | |

---

## Follow-up Required

| Action | Owner | Due Date |
|--------|-------|----------|
| | | |

---

## Sign-off

- **Operator:** _______________
- **Time:** _______________
- **No unexpected behavior:** [ ] Yes [ ] No

---

**Document Status:** ACTIVE

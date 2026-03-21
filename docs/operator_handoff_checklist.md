# Operator Handoff Checklist

**Version:** 1.0.0  
**Status:** ACTIVE

Use this checklist when handing off pilot operation to another operator.

---

## Handoff Information

| Field | Value |
|-------|-------|
| **Date** | YYYY-MM-DD |
| **Time** | HH:MM |
| **From Operator** | [Name] |
| **To Operator** | [Name] |

---

## Current Status Review

### System Status

```python
# Run and review output
from tools.manual_ops import show_operational_summary
summary = show_operational_summary()
```

| Metric | Value | Notes |
|--------|-------|-------|
| Apply plans total | | |
| Pending verifications | | |
| Pending manual actions | | |
| Failed verifications | | |
| Stale items | | |

**Status:** [ ] Healthy [ ] Needs attention

---

## Pending Approvals

| Entity ID | Action Type | Waiting For | Urgency |
|-----------|-------------|--------------|---------|
| | | | |

**Action required:** ___

---

## Pending Verifications

| Verification ID | Apply Plan ID | Status | Notes |
|-----------------|---------------|--------|-------|
| | | | |

**Action required:** ___

---

## Blocked Items

| Entity ID | Block Reason | Since | Notes |
|-----------|--------------|-------|-------|
| | | | |

**Action required:** ___

---

## Stale Items

| Apply Plan ID | Stale Since | Action Planned |
|---------------|--------------|-----------------|
| | | |

**Action required:** ___

---

## Revert Candidates

| Candidate ID | Apply Plan ID | Status | Notes |
|--------------|---------------|--------|-------|
| | | | |

**Action required:** ___

---

## Scheduler Status

| Metric | Value |
|--------|-------|
| Last run | |
| Actions detected | |
| Actions executed | [MUST BE 0] |

**Scheduler notes:**
```
[Any scheduler observations]
```

---

## Known Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| | | | |

---

## Active Operations

| Operation | Status | Expected Completion | Notes |
|-----------|--------|---------------------|-------|
| | | | |

---

## Special Instructions

```
[Any special instructions for the incoming operator]
```

---

## Key Commands Reference

```bash
# Check status
python3 -c "from tools.manual_ops import show_operational_summary; print(show_operational_summary()['counts'])"

# Run scheduler
python3 -c "from scheduler.controlled_scheduler import run_controlled_scheduler_once; print(run_controlled_scheduler_once())"

# List pending
python3 -c "from tools.manual_ops import list_pending_verifications; print(list_pending_verifications())"
```

---

## Handoff Verification

- [ ] Current status reviewed
- [ ] Pending items explained
- [ ] Blocked items explained
- [ ] Risks communicated
- [ ] Questions answered

---

## Sign-off

**From Operator:**
- Name: _______________
- Time: _______________

**To Operator:**
- Name: _______________
- Time: _______________
- Handoff accepted: [ ] Yes

---

**Document Status:** ACTIVE

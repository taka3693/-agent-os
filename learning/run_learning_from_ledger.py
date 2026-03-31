import json
from pathlib import Path
from datetime import datetime, timezone

LEDGER = Path("state/execution_ledger.jsonl")
EPISODES = Path("state/learning_episodes.jsonl")

def main():
    if not LEDGER.exists():
        return

    grouped = {}
    with open(LEDGER) as f:
        for line in f:
            try:
                r = json.loads(line)
            except:
                continue
            eid = r.get("execution_id")
            if not eid:
                continue
            grouped.setdefault(eid, []).append(r)

    episodes = []
    for eid, rows in grouped.items():
        terminal_rows = [r for r in rows if r.get("status") in ["succeeded", "failed", "failed_max_retries", "blocked"]]
        if not terminal_rows:
            continue

        last = terminal_rows[-1]
        status = last.get("status")

        action_type = None
        error_type = None
        error_value = None
        had_retry = False

        for r in rows:
            if r.get("action_type") and not action_type:
                action_type = r.get("action_type")
            if r.get("error_type"):
                error_type = r.get("error_type")
            if r.get("error"):
                error_value = r.get("error")
            if r.get("status") == "retry_scheduled":
                had_retry = True

        if status == "succeeded":
            outcome = "retry_success" if had_retry else "success"
        elif status == "blocked":
            outcome = "blocked_by_governance"
        else:
            outcome = "failed_verification"

        failure_codes = []
        if error_type:
            failure_codes.append(error_type)
        if error_value and error_value not in failure_codes:
            failure_codes.append(error_value)

        episodes.append({
            "episode_id": eid,
            "apply_plan_id": last.get("idempotency_key"),
            "patch_type": action_type or "unknown",
            "target_area": last.get("fingerprint"),
            "verification_outcome": status,
            "final_operator_action": "applied" if status == "succeeded" else "rejected",
            "failure_codes": failure_codes,
            "outcome": outcome,
            "created_at": datetime.now(timezone.utc).isoformat()
        })

    with open(EPISODES, "w") as f:
        for e in episodes:
            f.write(json.dumps(e) + "\n")

if __name__ == "__main__":
    main()

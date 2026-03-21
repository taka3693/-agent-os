from __future__ import annotations
from execution.execution_store import _read_jsonl
from execution.execution_store import _read_jsonl
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from execution.execution_store import latest_status_by_key, now_ts, queue_append, queued_keys, audit

ROOT = Path(__file__).resolve().parents[1]
APPROVAL_DECISIONS = ROOT / "state" / "approval_decisions.jsonl"
SESSION_DIR = Path.home() / ".openclaw" / "agents" / "main" / "sessions"
ARCHIVE_DIR = Path.home() / ".openclaw" / "agents" / "main" / "sessions_archive"

APPROVAL_TTL_SECONDS = {
    "session.archive": 24 * 3600,
}

def __read_jsonl(path: Path):
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def _make_idempotency_key(fingerprint: str) -> str:
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()

def _parse_ts(ts: str):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

def _approval_fresh(decided_at: str | None, action_type: str):
    if not decided_at:
        return False, "missing_decided_at"
    ttl = APPROVAL_TTL_SECONDS.get(action_type)
    if ttl is None:
        return False, "missing_ttl"
    age = (datetime.now(timezone.utc) - _parse_ts(decided_at)).total_seconds()
    if age > ttl:
        return False, f"expired:{int(age)}"
    return True, "fresh"

def _preflight_ok(action_type: str, payload: dict):
    if action_type == "session.archive":
        basename = payload["basename"]
        src = SESSION_DIR / basename
        dst = ARCHIVE_DIR / basename
        if src.exists():
            return True, "source_exists"
        if dst.exists():
            return True, "already_archived"
        return False, "missing_both_source_and_archive"
    return False, "unsupported_action"

def dispatch_approved_actions():
    print("Debugging dispatch_approved_actions")

    rows = _read_jsonl(APPROVAL_DECISIONS)

    for row in rows:

        try:

            action_type = row["action_type"]

            print(f"Found action_type: {action_type}")  # ここでaction_typeを表示

        except KeyError as e:

            print(f"KeyError: {e} in row: {row}")  # デバッグ用に出力

            continue
    rows = __read_jsonl(APPROVAL_DECISIONS)
    latest = latest_status_by_key()
    queued = queued_keys()
    dispatched = skipped = 0

    for row in rows:
        if row.get("decision") != "approved":
            continue

        fingerprint = row.get("fingerprint")
        action_type = row.get("action_type")
        payload = row.get("payload")

        if not fingerprint or not action_type or not payload:
            skipped += 1
            audit("dispatch_skipped_malformed_approval",
                  fingerprint=row.get("fingerprint"),
                  reason="missing_fingerprint_or_action_type_or_payload")
            continue

        key = _make_idempotency_key(fingerprint)

        fresh, freshness_reason = _approval_fresh(row.get("decided_at"), action_type)
        if not fresh:
            skipped += 1
            audit("dispatch_skipped_stale_approval", fingerprint=fingerprint, action_type=action_type, reason=freshness_reason)
            continue

        if key in queued:
            skipped += 1
            audit("dispatch_skipped_already_queued", fingerprint=fingerprint)
            continue

        current = latest.get(key)
        if current and current.get("status") in {"claimed", "running", "succeeded"}:
            skipped += 1
            audit("dispatch_skipped_terminal_or_active", fingerprint=fingerprint, status=current.get("status"))
            continue

        if current and current.get("status") == "failed" and current.get("error_type") == "permanent":
            skipped += 1
            audit("dispatch_skipped_permanent_failure", fingerprint=fingerprint)
            continue

        ok, reason = _preflight_ok(action_type, payload)
        if not ok:
            skipped += 1
            audit("dispatch_skipped_preflight", fingerprint=fingerprint, action_type=action_type, reason=reason)
            continue

        execution_id = f"exec_{key[:16]}"
        queue_append({
            "execution_id": execution_id,
            "idempotency_key": key,
            "fingerprint": fingerprint,
            "action_type": action_type,
            "payload": payload,
            "queued_at": now_ts(),
            "status": "queued",
            "attempt": 0,
        })
        audit("execution_dispatched", execution_id=execution_id, fingerprint=fingerprint, action_type=action_type, preflight=reason)
        dispatched += 1

    return {"ok": True, "dispatched": dispatched, "skipped": skipped}

if __name__ == "__main__":
    import json
    print(json.dumps(dispatch_approved_actions(), ensure_ascii=False, indent=2))

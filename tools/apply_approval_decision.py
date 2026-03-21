#!/usr/bin/env python3
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
APPROVAL_QUEUE = STATE / "approval_queue.jsonl"
APPROVAL_DECISIONS = STATE / "approval_decisions.jsonl"

ALLOWED = {"approved", "rejected"}

def now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def read_jsonl(path: Path):
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

def append_jsonl(path: Path, obj: dict):
    """Ensure that the JSON data is appended correctly to the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def write_jsonl(path: Path, rows):
    """Write the rows to the JSONL file, replacing it with the updated content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)

def main():
    if len(sys.argv) < 3:
        print("usage: apply_approval_decision.py <fingerprint> <approved|rejected> [reason] [source]", file=sys.stderr)
        raise SystemExit(2)

    fingerprint = sys.argv[1]
    decision = sys.argv[2]
    reason = sys.argv[3] if len(sys.argv) >= 4 else ""
    source = sys.argv[4] if len(sys.argv) >= 5 else "manual"

    if decision not in ALLOWED:
        print(f"invalid decision: {decision}", file=sys.stderr)
        raise SystemExit(2)

    # Define action_type and payload
    action_type = "session.archive"
    payload = {"basename": fingerprint.split(":")[1]}  # Adjusting this to match the use case

    decisions = read_jsonl(APPROVAL_DECISIONS)
    queue_rows = read_jsonl(APPROVAL_QUEUE)

    entry = {
        "fingerprint": fingerprint,
        "decision": decision,
        "reason": reason,
        "source": source,
        "action_type": action_type,  # Ensure action_type is included
        "payload": payload,          # Ensure payload is included
        "decided_at": now_ts(),
    }
    append_jsonl(APPROVAL_DECISIONS, entry)

    new_queue = [row for row in queue_rows if row.get("fingerprint") != fingerprint]
    write_jsonl(APPROVAL_QUEUE, new_queue)

    print(json.dumps({
        "ok": True,
        "fingerprint": fingerprint,
        "decision": decision,
        "removed_from_queue": len(queue_rows) - len(new_queue),
        "decided_at": entry["decided_at"],
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
QUEUE = STATE / "execution_queue.jsonl"
LEDGER = STATE / "execution_ledger.jsonl"
AUDIT = STATE / "audit" / "execution_audit.jsonl"
CLAIMS_DIR = STATE / "execution_claims"

STALE_SECONDS = 300
ACTIVE = {"claimed", "running"}

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

def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)

def append_jsonl(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def now_ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

def latest_ledger_by_execution_id(rows):
    out = {}
    for row in rows:
        out[row["execution_id"]] = row
    return out

queue_rows = read_jsonl(QUEUE)
ledger_rows = read_jsonl(LEDGER)
latest = latest_ledger_by_execution_id(ledger_rows)
now = datetime.now(timezone.utc)

recovered = 0

for row in queue_rows:
    status = row.get("status")
    if status not in ACTIVE:
        continue

    execution_id = row["execution_id"]
    ledger_row = latest.get(execution_id)
    if not ledger_row:
        continue

    ts = ledger_row.get("ts")
    if not ts:
        continue

    age = (now - parse_ts(ts)).total_seconds()
    if age < STALE_SECONDS:
        continue

    row["status"] = "queued"
    row["attempt"] = int(row.get("attempt", 0)) + 1

    lock_path = CLAIMS_DIR / f"{execution_id}.lock"
    if lock_path.exists():
        os.unlink(lock_path)

    append_jsonl(LEDGER, {
        "ts": now_ts(),
        "execution_id": execution_id,
        "idempotency_key": row["idempotency_key"],
        "fingerprint": row["fingerprint"],
        "status": "queued",
        "claimed_by": "recovery",
        "attempt": row["attempt"],
        "recovered_from": status,
    })
    append_jsonl(AUDIT, {
        "ts": now_ts(),
        "event": "execution_recovered",
        "execution_id": execution_id,
        "fingerprint": row["fingerprint"],
        "from_status": status,
    })
    recovered += 1

write_jsonl(QUEUE, queue_rows)

print(json.dumps({
    "ok": True,
    "recovered": recovered,
    "stale_seconds": STALE_SECONDS,
}, ensure_ascii=False, indent=2))

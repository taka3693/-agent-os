from __future__ import annotations
import json, os, time
from pathlib import Path
from typing import Any

STATE_DIR = Path(__file__).resolve().parents[1] / "state"
EXECUTION_QUEUE = STATE_DIR / "execution_queue.jsonl"
EXECUTION_LEDGER = STATE_DIR / "execution_ledger.jsonl"
AUDIT_LOG = STATE_DIR / "audit" / "execution_audit.jsonl"
CLAIMS_DIR = STATE_DIR / "execution_claims"
CLAIM_STALE_SECONDS = 900

def _append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

def now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def audit(event: str, **fields: Any) -> None:
    _append_jsonl(AUDIT_LOG, {"ts": now_ts(), "event": event, **fields})

def ledger_append(entry: dict[str, Any]) -> None:
    _append_jsonl(EXECUTION_LEDGER, entry)

def queue_append(entry: dict[str, Any]) -> None:
    _append_jsonl(EXECUTION_QUEUE, entry)

def queue_items() -> list[dict[str, Any]]:
    return _read_jsonl(EXECUTION_QUEUE)

def ledger_items() -> list[dict[str, Any]]:
    return _read_jsonl(EXECUTION_LEDGER)

def latest_status_by_key() -> dict[str, dict[str, Any]]:
    latest = {}
    for row in ledger_items():
        latest[row["idempotency_key"]] = row
    return latest

def queued_keys() -> set[str]:
    keys = set()
    for row in queue_items():
        if row.get("status") == "queued":
            keys.add(row["idempotency_key"])
    return keys

def claim_path(execution_id: str) -> Path:
    return CLAIMS_DIR / f"{execution_id}.lock"

def claim_is_stale(execution_id: str, stale_seconds: int = CLAIM_STALE_SECONDS) -> bool:
    p = claim_path(execution_id)
    if not p.exists():
        return True
    try:
        age = time.time() - p.stat().st_mtime
    except FileNotFoundError:
        return True
    return age >= stale_seconds

def create_claim(execution_id: str) -> bool:
    CLAIMS_DIR.mkdir(parents=True, exist_ok=True)
    p = claim_path(execution_id)
    try:
        fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False

def remove_claim(execution_id: str) -> None:
    p = claim_path(execution_id)
    if p.exists():
        p.unlink()

def rewrite_queue(updated_rows: list[dict[str, Any]]) -> None:
    EXECUTION_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    tmp = EXECUTION_QUEUE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in updated_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(EXECUTION_QUEUE)

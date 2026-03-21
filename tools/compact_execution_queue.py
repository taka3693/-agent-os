#!/usr/bin/env python3
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "state" / "execution_queue.jsonl"
KEEP = {"queued", "claimed", "running"}

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

rows = read_jsonl(QUEUE)
before = len(rows)
kept = [r for r in rows if r.get("status") in KEEP]
removed = before - len(kept)
write_jsonl(QUEUE, kept)

print(json.dumps({
    "ok": True,
    "before": before,
    "after": len(kept),
    "removed": removed,
}, ensure_ascii=False, indent=2))

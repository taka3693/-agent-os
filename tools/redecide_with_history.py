#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = ROOT / "state" / "decision_runs" / "decision_runs.jsonl"


def append_redecide_meta(record: dict) -> str:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return str(LOG_FILE)


def load_recent(limit: int = 3, current_query: str = ""):
    if not LOG_FILE.exists():
        return []

    lines = [x for x in LOG_FILE.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = []
    seen_pairs = set()

    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except Exception:
            continue

        q = str(obj.get("input_query") or "")
        conclusion = str(obj.get("conclusion") or "")
        pair = (q, conclusion)

        if not q or q == "--input" or q == "None":
            continue
        if conclusion == "None":
            continue
        if "過去判断要約:" in q:
            continue
        if current_query and q == current_query:
            continue
        if pair in seen_pairs:
            continue

        seen_pairs.add(pair)
        rows.append(obj)
        if len(rows) >= limit:
            break

    rows.reverse()
    return rows



def resolve_ab_query(query: str, recent: list[dict]) -> str:
    if not query or "A" not in query or "B" not in query:
        return query
    if not recent:
        return query

    for row in reversed(recent):
        winner = str(row.get("winner") or "").strip()
        loser = str(row.get("deprioritized") or "").strip()

        if not winner or not loser:
            continue
        if winner in {"A", "B"} or loser in {"A", "B"}:
            continue

        return query.replace("A", winner).replace("B", loser)

    return query

def build_context(rows) -> str:
    if not rows:
        return ""

    parts = ["過去判断要約:"]
    for i, r in enumerate(rows, start=1):
        parts.append(
            f"{i}. 問い={r.get('input_query')} / 結論={r.get('conclusion')} / 勝者={r.get('winner')}"
        )
    return "\n".join(parts)


def extract_last_json_object(raw: str):
    decoder = json.JSONDecoder()
    for i, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            obj, end = decoder.raw_decode(raw[i:])
            trailing = raw[i + end:].strip()
            if trailing == "":
                return obj
        except json.JSONDecodeError:
            continue
    return None


def run_decide_execute(query: str) -> dict:
    entrypoint = ROOT / "tools" / "entrypoint.py"

    cmd = [
        sys.executable,
        str(entrypoint),
        "decide_execute",
        query,
    ]

    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if completed.returncode != 0:
        return {
            "ok": False,
            "error": "decide_execute_failed",
            "returncode": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    if not stdout:
        return {
            "ok": False,
            "error": "decide_execute_empty_stdout",
            "returncode": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    parsed = extract_last_json_object(stdout)
    if parsed is None:
        return {
            "ok": False,
            "error": "decide_execute_invalid_json",
            "returncode": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args()

    query = args.input.strip()
    if not query:
        print(json.dumps({"ok": False, "error": "missing_query"}, ensure_ascii=False))
        return 1

    recent = load_recent(args.limit, current_query=query)
    resolved_query = resolve_ab_query(query, recent)
    context = build_context(recent)
    merged_query = resolved_query if not context else f"{resolved_query}\n\n{context}"

    out = run_decide_execute(merged_query)
    if isinstance(out, dict):
        out["original_query"] = query
        out["resolved_query"] = resolved_query
        out["history_augmented_query"] = merged_query
        out["history_used_count"] = len(recent)
        out["history_context"] = context

    result = {
        "ok": bool(out.get("ok")),
        "input_query": query,
        "original_query": query,
        "resolved_query": resolved_query,
        "history_augmented_query": merged_query,
        "history_used": len(recent),
        "history_used_count": len(recent),
        "history_context": context,
        "history_entries": recent,
        "stdout": json.dumps(out, ensure_ascii=False),
        "stderr": None if out.get("ok") else out.get("stderr"),
        "result": out,
    }

    if result["ok"]:
        append_redecide_meta({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "record_type": "redecide_meta",
            "original_query": query,
            "resolved_query": resolved_query,
            "history_augmented_query": merged_query,
            "history_used_count": len(recent),
            "history_context": context,
            "history_entries": recent,
            "result_task_id": out.get("task_id"),
            "result_conclusion": ((out.get("decision_out") or {}).get("task_result") or {}).get("decision", {}).get("conclusion"),
            "ok": True,
        })

    if args.text:
        if result["ok"]:
            print(out.get("text") or json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

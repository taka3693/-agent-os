#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

LOG_DIR = Path("runtime_logs/execution")


def _kind_from_key(key: str) -> str:
    if not key or not isinstance(key, str):
        return "unknown"
    return key.split("|", 1)[0].strip() or "unknown"


def _nested_counter():
    return {
        "attempts": 0,
        "applied": 0,
        "skipped": 0,
        "state_changed": 0,
        "verified_hits": 0,
    }


def _update_bucket(bucket: dict, *, status: str, state_changed: bool = False) -> None:
    bucket["attempts"] += 1
    if status == "completed":
        bucket["applied"] += 1
        if state_changed:
            bucket["state_changed"] += 1
    elif status == "skipped":
        bucket["skipped"] += 1


def _print_section(title: str, stats: dict[str, dict]) -> None:
    print(f"=== {title} ===")
    if not stats:
        print("none\n")
        return

    ordered = sorted(
        stats.items(),
        key=lambda kv: (-kv[1]["attempts"], kv[0]),
    )

    for key, row in ordered:
        attempts = row["attempts"]
        applied = row["applied"]
        skipped = row["skipped"]
        state_changed = row["state_changed"]
        verified_hits = row["verified_hits"]

        applied_rate = (applied / attempts) if attempts else 0.0
        changed_rate = (state_changed / attempts) if attempts else 0.0

        print(f"[{key}]")
        print(f"  attempts      : {attempts}")
        print(f"  applied       : {applied}")
        print(f"  skipped       : {skipped}")
        print(f"  state_changed : {state_changed}")
        print(f"  verified_hits : {verified_hits}")
        print(f"  applied_rate  : {applied_rate:.2%}")
        print(f"  changed_rate  : {changed_rate:.2%}")
        print()


def main() -> None:
    if not LOG_DIR.exists():
        print("no execution logs found")
        return

    by_kind = defaultdict(_nested_counter)
    by_field = defaultdict(_nested_counter)
    by_severity = defaultdict(_nested_counter)
    by_evidence_confidence = defaultdict(_nested_counter)

    valid_logs = 0
    missing_entry_logs = 0
    missing_entry_attempts = 0
    already_in_state_skips = 0
    already_applied_skips = 0

    for path in sorted(LOG_DIR.glob("execution_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not isinstance(data.get("stats"), dict):
            continue

        valid_logs += 1
        log_has_missing_entry = False

        for it in data.get("iterations", []) or []:
            for record in it.get("results", []) or []:
                result = record.get("result", {})
                if not isinstance(result, dict):
                    continue

                if result.get("action_type") != "fix_finding":
                    continue

                finding_key = result.get("finding_key", "")
                kind = _kind_from_key(finding_key)
                status = result.get("status")

                applied_fix = result.get("applied_fix", {})
                state_changed = (
                    isinstance(applied_fix, dict)
                    and applied_fix.get("state_changed") is True
                )

                _update_bucket(by_kind[kind], status=status, state_changed=state_changed)

                if status == "skipped":
                    reason = result.get("reason")
                    if reason == "already_in_state":
                        already_in_state_skips += 1
                    elif reason == "already_applied":
                        already_applied_skips += 1

                entry = applied_fix.get("entry") if isinstance(applied_fix, dict) else None
                if not isinstance(entry, dict):
                    log_has_missing_entry = True
                    missing_entry_attempts += 1
                    continue

                field = str(entry.get("field") or "unknown")
                severity = str(entry.get("severity") or "none")

                _update_bucket(by_field[field], status=status, state_changed=state_changed)
                _update_bucket(by_severity[severity], status=status, state_changed=state_changed)

                if field == "evidence":
                    evidence_item = entry.get("evidence_item", {})
                    confidence = "low"
                    if isinstance(evidence_item, dict):
                        confidence = str(evidence_item.get("confidence") or "unknown")
                    _update_bucket(
                        by_evidence_confidence[confidence],
                        status=status,
                        state_changed=state_changed,
                    )

            for record in it.get("results", []) or []:
                result = record.get("result", {})
                if not isinstance(result, dict):
                    continue
                if result.get("status") != "verified":
                    continue

                for key in result.get("verified_keys", []) or []:
                    kind = _kind_from_key(key)
                    by_kind[kind]["verified_hits"] += 1

        if log_has_missing_entry:
            missing_entry_logs += 1

    if valid_logs == 0:
        print("no valid execution logs found")
        return

    print("=== execution fix stats ===")
    print(f"valid_logs: {valid_logs}")
    print(f"missing_entry_logs: {missing_entry_logs}")
    print(f"missing_entry_attempts: {missing_entry_attempts}")
    print(f"already_in_state_skips: {already_in_state_skips}")
    print(f"already_applied_skips: {already_applied_skips}")
    print()

    _print_section("by kind", by_kind)
    _print_section("by field", by_field)
    _print_section("by severity", by_severity)
    _print_section("by evidence confidence", by_evidence_confidence)


if __name__ == "__main__":
    main()

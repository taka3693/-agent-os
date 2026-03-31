#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

LOG_DIR = Path("runtime_logs/execution")


def main() -> None:
    if not LOG_DIR.exists():
        print("no execution logs found")
        return

    paths = sorted(LOG_DIR.glob("execution_*.json"))
    found = 0
    skipped_legacy = 0

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        stats = data.get("stats")
        if not isinstance(stats, dict):
            skipped_legacy += 1
            continue

        converged = stats.get("converged")
        if converged is True:
            continue

        found += 1
        print("=" * 100)
        print(f"path: {path}")
        print(f"run_id: {data.get('run_id')}")
        print(f"iteration_count: {data.get('iteration_count')}")
        print(f"stopped_reason: {stats.get('stopped_reason')}")
        print(f"initial_findings_count: {stats.get('initial_findings_count')}")
        print(f"final_findings_count: {stats.get('final_findings_count')}")
        print("final_findings:")
        for item in data.get("final_findings", []) or []:
            print(f"  - {item}")

    print("=" * 100)
    print(f"legacy_logs_skipped: {skipped_legacy}")
    if found == 0:
        print("no non-converged logs found")


if __name__ == "__main__":
    main()

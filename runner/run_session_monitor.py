from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path("/home/milky/agent-os")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.session_monitor import monitor_once  # noqa: E402
from runner.run_execution_task import process_queued_tasks  # noqa: E402

def main() -> None:
    report = monitor_once()
    results = process_queued_tasks()
    print(
        json.dumps(
            {
                "health_status": report.get("status"),
                "created_tasks": report.get("created_tasks", []),
                "runner_results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

if __name__ == "__main__":
    main()

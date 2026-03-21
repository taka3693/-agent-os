from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from runner.run_approval_command import run_approval_command


def run_approval_argv(
    *,
    state_root: Path,
    argv: List[str],
    timestamp: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    command = " ".join(argv).strip()
    return run_approval_command(
        state_root=state_root,
        command=command,
        timestamp=timestamp,
        reason=reason,
    )

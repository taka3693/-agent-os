from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get("AGENTOS_REPO_ROOT", "/home/milky/agent-os")).resolve()

SESSIONS_DIR = Path(
    os.environ.get(
        "AGENTOS_SESSIONS_DIR",
        str(Path.home() / ".openclaw/agents/main/sessions"),
    )
).resolve()

ARCHIVE_ROOT = Path(
    os.environ.get(
        "AGENTOS_ARCHIVE_ROOT",
        str(Path.home() / ".openclaw/agents/main/sessions_archive/auto"),
    )
).resolve()

STATE_DIR = REPO_ROOT / "state"
HEALTH_DIR = STATE_DIR / "health"
AUDIT_DIR = STATE_DIR / "audit"
TASKS_DIR = STATE_DIR / "tasks"

QUEUED_DIR = TASKS_DIR / "queued"
AWAITING_APPROVAL_DIR = TASKS_DIR / "awaiting_approval"
COMPLETED_DIR = TASKS_DIR / "completed"
FAILED_DIR = TASKS_DIR / "failed"

HEALTH_REPORT_PATH = HEALTH_DIR / "session_health.json"

WARN_BYTES = int(os.environ.get("AGENTOS_SESSION_WARN_BYTES", str(300 * 1024)))
HIGH_BYTES = int(os.environ.get("AGENTOS_SESSION_HIGH_BYTES", str(800 * 1024)))
CRITICAL_BYTES = int(os.environ.get("AGENTOS_SESSION_CRITICAL_BYTES", str(1536 * 1024)))

AUTO_ARCHIVE_MIN_AGE_SECONDS = int(
    os.environ.get("AGENTOS_AUTO_ARCHIVE_MIN_AGE_SECONDS", str(30 * 60))
)
MAX_AUTO_ARCHIVES_PER_RUN = int(
    os.environ.get("AGENTOS_MAX_AUTO_ARCHIVES_PER_RUN", "2")
)

def ensure_dirs() -> None:
    for p in [
        HEALTH_DIR,
        AUDIT_DIR,
        QUEUED_DIR,
        AWAITING_APPROVAL_DIR,
        COMPLETED_DIR,
        FAILED_DIR,
        ARCHIVE_ROOT,
    ]:
        p.mkdir(parents=True, exist_ok=True)

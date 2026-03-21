from __future__ import annotations


# === VIRTUAL ACTION EXECUTION (ADDED) ===
import json
from pathlib import Path
from datetime import datetime

_ART_DIR = Path("artifacts/self_operation")
_ART_DIR.mkdir(parents=True, exist_ok=True)

def _write_art(action_type, task):
    path = _ART_DIR / f"{action_type.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    data = {"action_type": action_type, "task": task, "status": "success"}
    path.write_text(json.dumps(data, ensure_ascii=False))
    return str(path)
# === END ===

import shutil
from pathlib import Path
from typing import Any

SESSION_DIR = Path.home() / ".openclaw" / "agents" / "main" / "sessions"
ARCHIVE_DIR = Path.home() / ".openclaw" / "agents" / "main" / "sessions_archive"

def _archive_session(payload: dict[str, Any]) -> dict[str, Any]:
    basename = payload["basename"]
    src = SESSION_DIR / basename
    dst = ARCHIVE_DIR / basename
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    if not src.exists() and dst.exists():
        return {"ok": True, "status": "succeeded", "idempotent_reuse": True, "result": {"archived_path": str(dst)}}
    if not src.exists() and not dst.exists():
        return {"ok": False, "status": "failed", "error_type": "permanent", "error": f"source_missing:{src}"}
    if src.exists() and dst.exists():
        src.unlink()
        return {"ok": True, "status": "succeeded", "idempotent_reuse": True, "result": {"archived_path": str(dst)}}

    shutil.move(str(src), str(dst))
    return {"ok": True, "status": "succeeded", "idempotent_reuse": False, "result": {"archived_path": str(dst)}}

# === TEST ACTION TYPES (Phase 3 testing) ===
# These action types are for testing the result classifier and retry mechanism.

def _test_transient_fail(payload: dict[str, Any]) -> dict[str, Any]:
    """Test action that simulates a transient failure."""
    fail_count = payload.get("fail_count", 0)
    succeed_after = payload.get("succeed_after", 2)
    
    # Read current attempt from a counter file
    counter_file = Path("/tmp/test_transient_counter.txt")
    current_attempt = 0
    if counter_file.exists():
        try:
            current_attempt = int(counter_file.read_text().strip())
        except:
            current_attempt = 0
    
    current_attempt += 1
    counter_file.write_text(str(current_attempt))
    
    if current_attempt >= succeed_after:
        return {"ok": True, "status": "succeeded", "result": {"attempts": current_attempt}}
    
    return {"ok": False, "status": "failed", "error_type": "transient", "error": f"transient failure (attempt {current_attempt})"}


def _write_file(payload: dict[str, Any]) -> dict[str, Any]:
    path = payload.get("path")
    content = payload.get("content", "")

    if not path:
        return {"ok": False, "status": "failed", "error_type": "invalid_payload", "error": "missing_path"}

    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return {"ok": True, "status": "succeeded", "result": {"path": str(p)}}
    except PermissionError:
        return {"ok": False, "status": "failed", "error_type": "permanent", "error": "permission_denied"}
    except Exception as e:
        return {"ok": False, "status": "failed", "error_type": "unknown", "error": str(e)}


def execute_self_operation(action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if action_type == "session.archive":
        return _archive_session(payload)

    if action_type == "write":
        return _write_file(payload)
    
    # plan action type - acknowledges planning tasks (always succeeds)
    if action_type == "plan":
        task = payload.get("_original_task", payload.get("task", "unknown"))
        return {"ok": True, "status": "succeeded", "result": {"planned": task, "note": "task acknowledged for planning"}}
    
    # Test action types
    if action_type == "test.transient_fail":
        return _test_transient_fail(payload)
    
    # Phase 4 validation: transient_test (attempt-based)
    if action_type == "transient_test":
        attempt = payload.get("_worker_attempt", 0)
        if attempt == 0:
            return {"ok": False, "status": "failed", "error_type": "transient", "error": "forced_timeout"}
        return {"ok": True, "status": "succeeded", "result": {"attempt": attempt}}
    
    # Phase 4 validation: known_retry_test (for testing retry limit behavior)
    if action_type == "known_retry_test":
        succeed_after = payload.get("succeed_after", 3)
        attempt = payload.get("_worker_attempt", 0)
        if attempt < succeed_after - 1:
            return {"ok": False, "status": "failed", "error_type": "transient", "error": "forced_flaky_network"}
        return {"ok": True, "status": "succeeded", "result": {"attempt": attempt}}
    
    return {"ok": False, "status": "failed", "error_type": "permanent", "error": f"unsupported_action:{action_type}"}
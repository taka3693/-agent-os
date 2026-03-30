#!/usr/bin/env python3
"""Test MISO callback handling in telegram_agent_os_entry"""

import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bridge.telegram_agent_os_entry import is_miso_callback, handle_message


def test_is_miso_callback():
    """Test MISO callback detection"""
    # Valid callbacks
    assert is_miso_callback("miso:approve:task-123") is True
    assert is_miso_callback("miso:reject:task-456") is True
    assert is_miso_callback("miso:retry:mission-xyz") is True
    assert is_miso_callback("miso:skip:mission-abc") is True
    assert is_miso_callback("miso:abort:mission-def") is True
    
    # Invalid callbacks
    assert is_miso_callback("aos approve task-123") is False
    assert is_miso_callback("miso:unknown:task-123") is False
    assert is_miso_callback("hello world") is False
    assert is_miso_callback("") is False
    
    print("PASS: is_miso_callback tests")


def test_handle_message_miso_callback():
    """Test handle_message routes MISO callbacks correctly"""
    # Create a test task
    tasks_dir = PROJECT_ROOT / "state" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    
    task_id = f"task-miso-{uuid.uuid4().hex[:8]}"
    task_path = tasks_dir / f"{task_id}.json"
    
    task = {
        "task_id": task_id,
        "status": "approval_required",
        "approval_state": {
            "status": "approval_required",
            "reason": "allowlist外",
            "route_handler": "handle_direct_install",
            "target": "testpkg",
        },
        "route_execution": {
            "status": "approval_required",
            "handler": "handle_direct_install",
            "target": "testpkg",
        },
    }
    task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n")
    
    try:
        # Test approve callback
        result = handle_message(f"miso:approve:{task_id}")
        assert result["mode"] == "miso_callback", f"expected miso_callback mode, got {result}"
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert result["action"] == "approve"
        assert result["task_id"] == task_id
        
        # Verify task was updated
        updated_task = json.loads(task_path.read_text())
        assert updated_task["approval_state"]["status"] == "approved"
        assert updated_task["route_execution"]["status"] == "planned"
        
        print("PASS: handle_message MISO callback tests")
    finally:
        if task_path.exists():
            task_path.unlink()


def test_handle_message_miso_callback_reject():
    """Test handle_message routes MISO reject callback correctly"""
    tasks_dir = PROJECT_ROOT / "state" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    
    task_id = f"task-miso-rej-{uuid.uuid4().hex[:8]}"
    task_path = tasks_dir / f"{task_id}.json"
    
    task = {
        "task_id": task_id,
        "status": "approval_required",
        "approval_state": {
            "status": "approval_required",
            "reason": "allowlist外",
            "route_handler": "handle_direct_install",
            "target": "testpkg",
        },
        "route_execution": {
            "status": "approval_required",
            "handler": "handle_direct_install",
            "target": "testpkg",
        },
    }
    task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n")
    
    try:
        result = handle_message(f"miso:reject:{task_id}")
        assert result["mode"] == "miso_callback"
        assert result["ok"] is True
        assert result["action"] == "reject"
        
        updated_task = json.loads(task_path.read_text())
        assert updated_task["approval_state"]["status"] == "rejected"
        assert updated_task["route_execution"]["status"] == "rejected"
        
        print("PASS: handle_message MISO reject callback tests")
    finally:
        if task_path.exists():
            task_path.unlink()


def test_handle_message_miso_callback_not_found():
    """Test MISO callback with non-existent task"""
    result = handle_message("miso:approve:nonexistent-task-xyz")
    assert result["mode"] == "miso_callback"
    assert result["ok"] is False
    assert "not found" in result.get("error", "").lower() or "error" in result
    
    print("PASS: handle_message MISO callback not found tests")


def main():
    test_is_miso_callback()
    test_handle_message_miso_callback()
    test_handle_message_miso_callback_reject()
    test_handle_message_miso_callback_not_found()
    print("\n✅ All MISO callback entry tests passed")


if __name__ == "__main__":
    main()

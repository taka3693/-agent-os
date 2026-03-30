#!/usr/bin/env python3
"""Tests for MISO completion handler"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from miso.completion_handler import (
    parse_completion_event,
    find_mission_by_agent_label,
    handle_completion_event,
)
from miso.bridge import _save_mission, MISO_STATE_DIR


def test_parse_completion_event_detailed():
    """Test parsing detailed completion event"""
    text = """[Internal task completion event]
source: subagent
session_key: agent:worker:task-123
session_id: abc-def
type: subagent task
task: researcher
status: completed

Result (untrusted content):
<<<BEGIN_UNTRUSTED_CHILD_RESULT>>>
Found 5 relevant items.
<<<END_UNTRUSTED_CHILD_RESULT>>>"""
    
    result = parse_completion_event(text)
    assert result is not None
    assert result["session_key"] == "agent:worker:task-123"
    assert result["task_label"] == "researcher"
    assert result["status"] == "completed"
    
    print("✓ parse_completion_event detailed")


def test_parse_completion_event_simple_completed():
    """Test parsing simple completion message"""
    result = parse_completion_event("A subagent task 'worker' just completed")
    assert result is not None
    assert result["task_label"] == "worker"
    assert result["status"] == "completed"
    
    print("✓ parse_completion_event simple completed")


def test_parse_completion_event_simple_failed():
    """Test parsing simple failure message"""
    result = parse_completion_event("subagent analyzer just failed")
    assert result is not None
    assert result["task_label"] == "analyzer"
    assert result["status"] == "failed"
    
    print("✓ parse_completion_event simple failed")


def test_parse_completion_event_no_match():
    """Test that non-completion messages return None"""
    result = parse_completion_event("Hello, how are you?")
    assert result is None
    
    result = parse_completion_event("The task is running")
    assert result is None
    
    print("✓ parse_completion_event no match")


def test_find_mission_by_agent_label():
    """Test finding mission by agent label"""
    MISO_STATE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create test mission
    test_mission = {
        "mission_id": "test-find-001",
        "mission_name": "Test Mission",
        "agents": [
            {"name": "researcher", "label": "researcher", "status": "RUNNING"},
            {"name": "writer", "label": "writer", "status": "INIT"},
        ],
    }
    _save_mission("test-find-001", test_mission)
    
    try:
        # Find by label
        found = find_mission_by_agent_label("researcher")
        assert found == "test-find-001"
        
        found = find_mission_by_agent_label("writer")
        assert found == "test-find-001"
        
        # Not found
        found = find_mission_by_agent_label("nonexistent")
        assert found is None
        
        print("✓ find_mission_by_agent_label")
    finally:
        # Cleanup
        (MISO_STATE_DIR / "test-find-001.json").unlink(missing_ok=True)


@patch("miso.bridge.edit_message")
@patch("miso.bridge.react_to_message")
def test_handle_completion_event_success(mock_react, mock_edit):
    """Test handling completion event end-to-end"""
    mock_edit.return_value = {"ok": True}
    mock_react.return_value = {"ok": True}
    
    MISO_STATE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create test mission
    test_mission = {
        "mission_id": "test-complete-001",
        "mission_name": "Completion Test",
        "goal": "Test completion handling",
        "chat_id": "123456",
        "message_id": "msg-001",
        "state": "RUNNING",
        "agents": [
            {"name": "worker1", "label": "worker1", "status": "RUNNING"},
            {"name": "worker2", "label": "worker2", "status": "RUNNING"},
        ],
        "created_at": "2026-03-30T22:00:00+00:00",
        "updated_at": "2026-03-30T22:00:00+00:00",
    }
    _save_mission("test-complete-001", test_mission)
    
    try:
        # Handle first completion
        result = handle_completion_event("A subagent task 'worker1' just completed")
        
        assert result["handled"] is True
        assert result["mission_id"] == "test-complete-001"
        assert result["agent_label"] == "worker1"
        assert result["status"] == "completed"
        assert result["new_state"] == "PARTIAL"  # One done, one running
        
        # Handle second completion
        result2 = handle_completion_event("subagent worker2 just completed")
        
        assert result2["handled"] is True
        assert result2["new_state"] == "COMPLETE"  # All done
        
        print("✓ handle_completion_event success")
    finally:
        (MISO_STATE_DIR / "test-complete-001.json").unlink(missing_ok=True)


@patch("miso.bridge.edit_message")
@patch("miso.bridge.react_to_message")
def test_handle_completion_event_failure(mock_react, mock_edit):
    """Test handling failure event"""
    mock_edit.return_value = {"ok": True}
    mock_react.return_value = {"ok": True}
    
    MISO_STATE_DIR.mkdir(parents=True, exist_ok=True)
    
    test_mission = {
        "mission_id": "test-fail-001",
        "mission_name": "Failure Test",
        "goal": "Test failure handling",
        "chat_id": "123456",
        "message_id": "msg-002",
        "state": "RUNNING",
        "agents": [
            {"name": "analyzer", "label": "analyzer", "status": "RUNNING"},
        ],
        "created_at": "2026-03-30T22:00:00+00:00",
        "updated_at": "2026-03-30T22:00:00+00:00",
    }
    _save_mission("test-fail-001", test_mission)
    
    try:
        result = handle_completion_event("subagent analyzer just failed")
        
        assert result["handled"] is True
        assert result["status"] == "failed"
        assert result["new_state"] == "ERROR"
        
        print("✓ handle_completion_event failure")
    finally:
        (MISO_STATE_DIR / "test-fail-001.json").unlink(missing_ok=True)


def test_handle_completion_event_no_mission():
    """Test handling event when no mission exists"""
    result = handle_completion_event("A subagent task 'unknown_agent' just completed")
    
    assert result["handled"] is False
    assert "no mission found" in result.get("error", "")
    
    print("✓ handle_completion_event no mission")


def main():
    test_parse_completion_event_detailed()
    test_parse_completion_event_simple_completed()
    test_parse_completion_event_simple_failed()
    test_parse_completion_event_no_match()
    test_find_mission_by_agent_label()
    test_handle_completion_event_success()
    test_handle_completion_event_failure()
    test_handle_completion_event_no_mission()
    print("\n✅ All MISO completion handler tests passed")


if __name__ == "__main__":
    main()

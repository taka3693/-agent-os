#!/usr/bin/env python3
"""Tests for spawn_with_miso"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_miso_spawner_setup():
    """Test MisoSpawner initialization and agent addition"""
    from miso.spawn_with_miso import MisoSpawner
    
    spawner = MisoSpawner(
        chat_id="123456",
        mission_name="Test Mission",
        goal="Test the spawner",
    )
    
    assert spawner.chat_id == "123456"
    assert spawner.mission_name == "Test Mission"
    assert spawner.goal == "Test the spawner"
    assert len(spawner.agents) == 0
    
    # Add agents
    spawner.add_agent("researcher", "Research the topic")
    spawner.add_agent("writer", "Write the report", display_label="ライター")
    
    assert len(spawner.agents) == 2
    assert spawner.agents[0]["name"] == "researcher"
    assert spawner.agents[0]["task"] == "Research the topic"
    assert spawner.agents[1]["display_label"] == "ライター"
    
    print("PASS: MisoSpawner setup tests")


def test_miso_spawner_start_no_agents():
    """Test MisoSpawner.start() with no agents"""
    from miso.spawn_with_miso import MisoSpawner
    
    spawner = MisoSpawner(
        chat_id="123456",
        mission_name="Empty Mission",
        goal="Nothing",
    )
    
    result = spawner.start()
    assert result["ok"] is False
    assert "no agents" in result["error"]
    
    print("PASS: MisoSpawner start no agents tests")


@patch("miso.bridge.send_message")
@patch("miso.bridge.react_to_message")
def test_miso_spawner_start(mock_react, mock_send):
    """Test MisoSpawner.start() with mocked Telegram"""
    from miso.spawn_with_miso import MisoSpawner
    from miso.bridge import MISO_STATE_DIR
    
    mock_send.return_value = {"ok": True, "message_id": "msg-test-123"}
    mock_react.return_value = {"ok": True}
    
    spawner = MisoSpawner(
        chat_id="123456",
        mission_name="Test Mission",
        goal="Test the spawner",
        mission_id="test-mission-001",
    )
    spawner.add_agent("worker", "Do the work")
    
    result = spawner.start()
    
    assert result["ok"] is True
    assert result["mission_id"] == "test-mission-001"
    assert result["message_id"] == "msg-test-123"
    assert len(result["agents"]) == 1
    assert result["agents"][0]["name"] == "worker"
    
    # Verify mission state was saved
    state_path = MISO_STATE_DIR / "test-mission-001.json"
    assert state_path.exists()
    
    state = json.loads(state_path.read_text())
    assert state["mission_id"] == "test-mission-001"
    assert state["state"] == "INIT"
    assert len(state["agents"]) == 1
    
    # Cleanup
    state_path.unlink()
    
    print("PASS: MisoSpawner start tests")


@patch("miso.bridge.send_message")
@patch("miso.bridge.react_to_message")
@patch("miso.bridge.edit_message")
def test_miso_spawner_lifecycle(mock_edit, mock_react, mock_send):
    """Test full MisoSpawner lifecycle: start -> attach -> complete"""
    from miso.spawn_with_miso import MisoSpawner
    from miso.bridge import MISO_STATE_DIR
    
    mock_send.return_value = {"ok": True, "message_id": "msg-lc-123"}
    mock_react.return_value = {"ok": True}
    mock_edit.return_value = {"ok": True}
    
    spawner = MisoSpawner(
        chat_id="123456",
        mission_name="Lifecycle Test",
        goal="Test full lifecycle",
        mission_id="test-lifecycle-001",
    )
    spawner.add_agent("agent1", "Task 1")
    spawner.add_agent("agent2", "Task 2")
    
    # Start
    result = spawner.start()
    assert result["ok"] is True
    
    # Attach first agent
    attach1 = spawner.attach_agent("agent1", session_id="sess-001")
    assert attach1["ok"] is True
    assert attach1["state"] == "PARTIAL"  # Not all running yet
    
    # Attach second agent
    attach2 = spawner.attach_agent("agent2", session_id="sess-002")
    assert attach2["ok"] is True
    assert attach2["state"] == "RUNNING"  # All running now
    
    # Complete first agent
    complete1 = spawner.complete_agent("agent1", "Done task 1")
    assert complete1["ok"] is True
    assert complete1["state"] == "PARTIAL"  # One done, one running
    
    # Complete second agent
    complete2 = spawner.complete_agent("agent2", "Done task 2")
    assert complete2["ok"] is True
    assert complete2["state"] == "COMPLETE"  # All done
    
    # Cleanup
    state_path = MISO_STATE_DIR / "test-lifecycle-001.json"
    if state_path.exists():
        state_path.unlink()
    
    print("PASS: MisoSpawner lifecycle tests")


def test_spawn_single_with_miso():
    """Test convenience function"""
    from miso.spawn_with_miso import spawn_single_with_miso
    
    with patch("miso.bridge.send_message") as mock_send, \
         patch("miso.bridge.react_to_message") as mock_react:
        
        mock_send.return_value = {"ok": True, "message_id": "msg-single-123"}
        mock_react.return_value = {"ok": True}
        
        result = spawn_single_with_miso(
            chat_id="123456",
            task="Do something",
            agent_name="worker",
        )
        
        assert result["ok"] is True
        assert len(result["agents"]) == 1
        assert result["agents"][0]["name"] == "worker"
        
        # Cleanup
        from miso.bridge import MISO_STATE_DIR
        for f in MISO_STATE_DIR.glob("mission-*.json"):
            f.unlink()
    
    print("PASS: spawn_single_with_miso tests")


def main():
    test_miso_spawner_setup()
    test_miso_spawner_start_no_agents()
    test_miso_spawner_start()
    test_miso_spawner_lifecycle()
    test_spawn_single_with_miso()
    print("\n✅ All spawn_with_miso tests passed")


if __name__ == "__main__":
    main()

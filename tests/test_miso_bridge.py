#!/usr/bin/env python3
"""Tests for MISO bridge"""

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_formatter():
    """Test message formatter"""
    from miso.formatter import (
        format_mission_message,
        format_approval_message,
        progress_bar,
        format_agent_line,
        normalize_detail,
        get_reaction_for_state,
    )
    
    # Progress bar
    assert "░" * 16 in progress_bar(0)
    assert "▓" * 16 in progress_bar(100)
    assert "50%" in progress_bar(50)
    
    # Agent line
    line = format_agent_line("担当A", "RUNNING", "準備完了")
    assert "担当A" in line
    assert "🔥" in line
    assert "進行中" in line
    assert "準備完了" in line
    
    # Normalize detail
    assert normalize_detail("worker attached and ready") == "準備完了"
    assert normalize_detail("blocked by allowlist") == "allowlist外"
    
    # Mission message
    msg = format_mission_message(
        mission_name="テストミッション",
        goal="テストを実行する",
        agents=[
            {"name": "調査A", "status": "RUNNING", "detail": "分析中"},
            {"name": "実行B", "status": "INIT"},
        ],
        state="RUNNING",
        elapsed="5m",
        next_action="調査完了待ち",
    )
    assert "MISSION CONTROL" in msg
    assert "テストミッション" in msg
    assert "テストを実行する" in msg
    assert "調査A" in msg
    assert "実行B" in msg
    assert "調査完了待ち" in msg
    assert "powered by miyabi" in msg
    
    # Approval message
    approval_msg = format_approval_message(
        task_id="task-123",
        target="scrapling",
        handler="handle_direct_install",
        reason="allowlist外",
    )
    assert "承認待ち" in approval_msg
    assert "task-123" in approval_msg
    assert "scrapling" in approval_msg
    
    # Reactions
    assert get_reaction_for_state("RUNNING") == "🔥"
    assert get_reaction_for_state("AWAITING_APPROVAL") == "👀"
    assert get_reaction_for_state("COMPLETE") == "🎉"
    assert get_reaction_for_state("ERROR") == "❌"
    
    print("PASS: formatter tests")


def test_telegram_hooks():
    """Test Telegram hooks (mocked)"""
    from miso.telegram_hooks import (
        make_approval_buttons,
        make_retry_buttons,
    )
    
    # Approval buttons
    buttons = make_approval_buttons("task-abc")
    assert len(buttons) == 1
    assert len(buttons[0]) == 2
    assert "承認" in buttons[0][0]["text"]
    assert "却下" in buttons[0][1]["text"]
    assert "miso:approve:task-abc" in buttons[0][0]["callback_data"]
    assert "miso:reject:task-abc" in buttons[0][1]["callback_data"]
    
    # Retry buttons
    retry = make_retry_buttons("mission-xyz")
    assert len(retry) == 2
    assert "再試行" in retry[0][0]["text"]
    assert "スキップ" in retry[0][1]["text"]
    assert "中止" in retry[1][0]["text"]
    
    print("PASS: telegram_hooks tests")


def test_bridge_state_management():
    """Test bridge state save/load"""
    from miso.bridge import _load_mission, _save_mission, MISO_STATE_DIR
    
    test_id = f"test-{uuid.uuid4().hex[:8]}"
    test_data = {
        "mission_id": test_id,
        "mission_name": "テスト",
        "state": "INIT",
    }
    
    # Save
    _save_mission(test_id, test_data)
    
    # Load
    loaded = _load_mission(test_id)
    assert loaded["mission_id"] == test_id
    assert loaded["mission_name"] == "テスト"
    assert loaded["state"] == "INIT"
    
    # Cleanup
    (MISO_STATE_DIR / f"{test_id}.json").unlink()
    
    print("PASS: bridge state management tests")


def test_handle_approval_callback_parse():
    """Test approval callback parsing"""
    # Valid format
    callback = "miso:approve:task-123"
    parts = callback.split(":")
    assert parts[0] == "miso"
    assert parts[1] == "approve"
    assert parts[2] == "task-123"
    
    callback2 = "miso:reject:task-456"
    parts2 = callback2.split(":")
    assert parts2[1] == "reject"
    assert parts2[2] == "task-456"
    
    print("PASS: approval callback parse tests")


def main():
    test_formatter()
    test_telegram_hooks()
    test_bridge_state_management()
    test_handle_approval_callback_parse()
    print("\n✅ All MISO bridge tests passed")


if __name__ == "__main__":
    main()

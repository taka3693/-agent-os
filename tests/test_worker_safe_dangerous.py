#!/usr/bin/env python3
"""
Phase 2: Worker統合テスト — safe/dangerous タスクの自動処理

キューにタスクを投入して、ワーカーが正しく処理するかテスト：
- safe タスク → 自動実行される
- dangerous タスク → ブロックされる
"""

import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from execution.execution_store import (
    queue_items,
    rewrite_queue,
    ledger_append,
    ledger_items,
    now_ts,
)
from runner.run_execution_worker import run_execution_worker


def make_execution_id() -> str:
    return f"exec-{uuid.uuid4().hex[:8]}"


def add_to_queue(action_type: str, payload: dict) -> str:
    """Add a task to the execution queue."""
    execution_id = make_execution_id()
    fingerprint = f"fp-{uuid.uuid4().hex[:6]}"
    idempotency_key = f"idem-{uuid.uuid4().hex[:6]}"
    
    rows = queue_items()
    rows.append({
        "execution_id": execution_id,
        "fingerprint": fingerprint,
        "idempotency_key": idempotency_key,
        "action_type": action_type,
        "payload": payload,
        "status": "queued",
        "attempt": 0,
        "created_at": now_ts(),
    })
    rewrite_queue(rows)
    
    return execution_id


def get_queue_item(execution_id: str) -> dict | None:
    """Get a specific item from the queue."""
    for row in queue_items():
        if row.get("execution_id") == execution_id:
            return row
    return None


def get_ledger_for_execution(execution_id: str) -> list:
    """Get all ledger entries for an execution."""
    entries = ledger_items()
    return [e for e in entries if e.get("execution_id") == execution_id]


class TestWorkerSafeDangerous:
    """Test worker safe/dangerous behavior."""
    
    def test_safe_task_executed(self):
        """Safe write task should be executed (or at least attempted)."""
        # Add a safe task
        execution_id = add_to_queue("write", {
            "path": "/tmp/agent-os-test-safe.txt",
            "content": "safe content",
        })
        
        # Run worker
        result = run_execution_worker("test-worker")
        
        # Check result
        assert result.get("execution_id") == execution_id
        # Should not be blocked
        assert result.get("status") != "blocked", f"Safe task was blocked: {result}"
        assert result.get("class") != "blocked"
        
        # Check ledger
        ledger = get_ledger_for_execution(execution_id)
        statuses = [e.get("status") for e in ledger]
        assert "blocked" not in statuses, f"Safe task has 'blocked' in ledger: {statuses}"
        
        # Should be claimed and attempted
        assert "claimed" in statuses or "running" in statuses or "succeeded" in statuses, \
            f"Safe task should be attempted: {statuses}"
        
        print(f"✓ Safe task executed, statuses: {statuses}")
    
    def test_dangerous_task_blocked(self):
        """Dangerous write task should be blocked."""
        # Add a dangerous task
        execution_id = add_to_queue("write", {
            "path": "/etc/passwd",
            "content": "malicious",
        })
        
        # Run worker
        result = run_execution_worker("test-worker")
        
        # Check result
        assert result.get("execution_id") == execution_id
        assert result.get("status") == "blocked", f"Dangerous task should be blocked: {result}"
        assert result.get("class") == "blocked"
        assert result.get("reason") == "dangerous_path"
        
        # Check ledger
        ledger = get_ledger_for_execution(execution_id)
        statuses = [e.get("status") for e in ledger]
        assert "blocked" in statuses, f"Dangerous task should have 'blocked' in ledger: {statuses}"
        
        # Should NOT be claimed or running
        assert "claimed" not in statuses, f"Dangerous task should not be claimed: {statuses}"
        assert "running" not in statuses, f"Dangerous task should not be running: {statuses}"
        
        print(f"✓ Dangerous task blocked, statuses: {statuses}")
    
    def test_dangerous_ssh_blocked(self):
        """Write to ~/.ssh should be blocked."""
        execution_id = add_to_queue("write", {
            "path": "~/.ssh/authorized_keys",
            "content": "ssh-rsa AAAA...",
        })
        
        result = run_execution_worker("test-worker")
        
        assert result.get("status") == "blocked"
        assert result.get("reason") == "dangerous_path"
        
        print("✓ SSH write blocked")
    
    def test_dangerous_boot_blocked(self):
        """Write to /boot should be blocked."""
        execution_id = add_to_queue("write", {
            "path": "/boot/grub/grub.cfg",
            "content": "malicious",
        })
        
        result = run_execution_worker("test-worker")
        
        assert result.get("status") == "blocked"
        assert result.get("reason") == "dangerous_path"
        
        print("✓ Boot write blocked")
    
    def test_read_action_not_blocked(self):
        """Read action should not be blocked even for sensitive paths."""
        execution_id = add_to_queue("read", {
            "path": "/etc/passwd",
        })
        
        result = run_execution_worker("test-worker")
        
        # Read should not be blocked (guard only checks write)
        assert result.get("status") != "blocked", f"Read should not be blocked: {result}"
        
        print("✓ Read action not blocked")


def main():
    """Run tests without pytest for quick verification."""
    import traceback
    
    test_instance = TestWorkerSafeDangerous()
    passed = 0
    failed = 0
    
    for method_name in dir(test_instance):
        if method_name.startswith("test_"):
            try:
                getattr(test_instance, method_name)()
                passed += 1
            except AssertionError as e:
                print(f"✗ {method_name}: {e}")
                failed += 1
            except Exception as e:
                print(f"✗ {method_name}: {type(e).__name__}: {e}")
                traceback.print_exc()
                failed += 1
    
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

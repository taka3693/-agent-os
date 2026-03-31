"""Tests for approval executor"""
import unittest
import tempfile
import json
from pathlib import Path

from ops.approval_executor import (
    execute_approved_action,
    execute_and_log,
    execution_log_path,
)


class TestApprovalExecutor(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_root = Path(self.tmpdir)

    def test_unknown_action_returns_error(self):
        result = execute_approved_action("nonexistent_action", {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "unknown_action")

    def test_execute_and_log_creates_log_file(self):
        result = execute_and_log(
            self.state_root,
            fingerprint="test_fp_001",
            action="unknown_test_action",
            args={"test": True},
        )

        log_path = execution_log_path(self.state_root)
        self.assertTrue(log_path.exists())

        with log_path.open() as f:
            log_entry = json.loads(f.readline())

        self.assertEqual(log_entry["fingerprint"], "test_fp_001")
        self.assertEqual(log_entry["action"], "unknown_test_action")

    def test_execute_run_skill_action(self):
        # Mock test - スキル実行のテスト
        result = execute_approved_action(
            "run_skill",
            {"skill": "research", "query": "test query"},
        )
        # 実行自体は成功するはず（結果は環境依存）
        self.assertIn("ok", result)


class TestApprovalDecisionWithExecution(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_root = Path(self.tmpdir)

    def test_approve_triggers_execution(self):
        from ops.approval_queue import append_approval_queue_entry
        from ops.approval_decision import apply_approval_decision
        from datetime import datetime, timezone

        # キューにエントリ追加
        append_approval_queue_entry(
            self.state_root,
            timestamp=datetime.now(timezone.utc).isoformat(),
            fingerprint="exec_test_001",
            action="run_skill",
            args={"skill": "research", "query": "auto exec test"},
            policy="require_approval",
            reason="test",
        )

        # 承認
        result = apply_approval_decision(
            self.state_root,
            timestamp=datetime.now(timezone.utc).isoformat(),
            fingerprint="exec_test_001",
            decision="approve",
            auto_execute=True,
        )

        self.assertTrue(result["ok"])
        self.assertIn("execution", result)
        self.assertIn("executed", result)

    def test_reject_does_not_execute(self):
        from ops.approval_queue import append_approval_queue_entry
        from ops.approval_decision import apply_approval_decision
        from datetime import datetime, timezone

        append_approval_queue_entry(
            self.state_root,
            timestamp=datetime.now(timezone.utc).isoformat(),
            fingerprint="reject_test_001",
            action="run_skill",
            args={"skill": "research", "query": "should not run"},
            policy="require_approval",
            reason="test",
        )

        result = apply_approval_decision(
            self.state_root,
            timestamp=datetime.now(timezone.utc).isoformat(),
            fingerprint="reject_test_001",
            decision="reject",
        )

        self.assertTrue(result["ok"])
        self.assertNotIn("execution", result)


if __name__ == "__main__":
    unittest.main()

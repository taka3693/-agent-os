from __future__ import annotations

import tempfile
import json
import time
import unittest
from pathlib import Path
from importlib import reload


class TestExecutionQueueHygiene(unittest.TestCase):
    def setUp(self) -> None:
        import execution.execution_store as store
        import execution.self_operation_executor as executor
        import runner.run_execution_worker as worker

        self.store = reload(store)
        self.executor = reload(executor)
        self.worker = reload(worker)

        self._orig_guard = self.worker.pre_execution_guard

    def tearDown(self) -> None:
        self.worker.pre_execution_guard = self._orig_guard

    def _bind_state(self, state_dir: Path) -> None:
        self.store.STATE_DIR = state_dir
        self.store.EXECUTION_QUEUE = state_dir / "execution_queue.jsonl"
        self.store.EXECUTION_LEDGER = state_dir / "execution_ledger.jsonl"
        self.store.AUDIT_LOG = state_dir / "audit" / "execution_audit.jsonl"
        self.store.CLAIMS_DIR = state_dir / "execution_claims"
        self.worker.INSIGHTS_DIR = state_dir / "agentos"
        self.worker.INSIGHTS_FILE = self.worker.INSIGHTS_DIR / "learning_insights.jsonl"

    def test_blocked_items_are_removed_from_queue(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            self._bind_state(state_dir)

            self.worker.pre_execution_guard = lambda action_type, payload: (
                "blocked",
                {"reason": "dangerous_path", "detail": "simulated"},
            )

            row = {
                "execution_id": "exec-blocked-test-001",
                "idempotency_key": "k-blocked-test-001",
                "fingerprint": "fp-blocked",
                "status": "queued",
                "action_type": "write",
                "payload": {"path": "/etc/passwd", "content": "x"},
                "attempt": 0,
            }
            self.store.rewrite_queue([row])

            out = self.worker.run_execution_worker("test-worker")
            self.assertEqual(out["status"], "blocked")
            self.assertEqual(self.store.queue_items(), [])

            ledger = self.store.ledger_items()
            self.assertEqual(ledger[-1]["status"], "blocked")
            self.assertEqual(ledger[-1]["action_type"], "write")
            self.assertEqual(ledger[-1]["error"], "dangerous_path")

    def test_stale_running_is_recovered_and_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_dir = root / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            self._bind_state(state_dir)

            out_file = root / "recovered.txt"

            row = {
                "execution_id": "exec-stale-test-001",
                "idempotency_key": "k-stale-test-001",
                "fingerprint": "fp-stale",
                "status": "running",
                "action_type": "write",
                "payload": {"path": str(out_file), "content": "RECOVERED_OK"},
                "attempt": 0,
            }
            self.store.rewrite_queue([row])

            lock = self.store.claim_path(row["execution_id"])
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("stale", encoding="utf-8")
            old = time.time() - 3600
            import os
            os.utime(lock, (old, old))

            out = self.worker.run_execution_worker("test-worker")
            self.assertTrue(out["ok"])
            self.assertEqual(out["class"], "success")
            self.assertTrue(out_file.exists())
            self.assertEqual(out_file.read_text(encoding="utf-8"), "RECOVERED_OK")
            self.assertEqual(self.store.queue_items(), [])

            statuses = [x["status"] for x in self.store.ledger_items()]
            self.assertIn("recovered_stale_claim", statuses)
            self.assertIn("claimed", statuses)
            self.assertIn("running", statuses)
            self.assertIn("succeeded", statuses)

    def test_retryable_item_requeues_and_then_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            self._bind_state(state_dir)

            row = {
                "execution_id": "exec-retry-test-001",
                "idempotency_key": "k-retry-test-001",
                "fingerprint": "fp-retry",
                "status": "queued",
                "action_type": "known_retry_test",
                "payload": {"succeed_after": 3},
                "attempt": 0,
            }
            self.store.rewrite_queue([row])

            out1 = self.worker.run_execution_worker("test-worker")
            out2 = self.worker.run_execution_worker("test-worker")
            out3 = self.worker.run_execution_worker("test-worker")

            self.assertEqual(out1["status"], "retry_scheduled")
            self.assertEqual(out2["status"], "retry_scheduled")
            self.assertTrue(out3["ok"])
            self.assertEqual(out3["class"], "success")
            self.assertEqual(self.store.queue_items(), [])

            retry_rows = [x for x in self.store.ledger_items() if x["status"] == "retry_scheduled"]
            self.assertEqual(len(retry_rows), 2)
            self.assertEqual(retry_rows[0]["next_attempt"], 2)
            self.assertEqual(retry_rows[1]["next_attempt"], 3)

    def test_claimed_and_running_ledger_rows_include_action_type(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_dir = root / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            self._bind_state(state_dir)

            out_file = root / "ledger_write.txt"

            row = {
                "execution_id": "exec-ledger-test-001",
                "idempotency_key": "k-ledger-test-001",
                "fingerprint": "fp-ledger",
                "status": "queued",
                "action_type": "write",
                "payload": {"path": str(out_file), "content": "LEDGER_OK"},
                "attempt": 0,
            }
            self.store.rewrite_queue([row])

            out = self.worker.run_execution_worker("test-worker")
            self.assertTrue(out["ok"])

            ledger = self.store.ledger_items()
            claimed = [x for x in ledger if x["status"] == "claimed"][-1]
            running = [x for x in ledger if x["status"] == "running"][-1]
            succeeded = [x for x in ledger if x["status"] == "succeeded"][-1]

            self.assertEqual(claimed["action_type"], "write")
            self.assertEqual(running["action_type"], "write")
            self.assertEqual(succeeded["action_type"], "write")


    def test_known_failure_pattern_shortens_retry_budget(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            self._bind_state(state_dir)

            insights_dir = self.worker.INSIGHTS_DIR
            insights_dir.mkdir(parents=True, exist_ok=True)
            insights_file = self.worker.INSIGHTS_FILE

            pattern_key = self.worker.generate_pattern_key(
                "known_retry_test",
                "transient",
                "forced_flaky_network",
            )
            insight = {
                "type": "failure_pattern",
                "pattern_key": pattern_key,
                "count": 2,
                "first_seen": "2026-03-20T00:00:00Z",
                "last_seen": "2026-03-20T00:00:00Z",
                "action_type": "known_retry_test",
                "error_type": "transient",
                "normalized_error": "forced_flaky_network",
            }
            insights_file.write_text(json.dumps(insight, ensure_ascii=False) + "\n", encoding="utf-8")

            row = {
                "execution_id": "exec-retry-shortened-001",
                "idempotency_key": "k-retry-shortened-001",
                "fingerprint": "fp-retry-shortened",
                "status": "queued",
                "action_type": "known_retry_test",
                "payload": {"succeed_after": 3},
                "attempt": 0,
            }
            self.store.rewrite_queue([row])

            out1 = self.worker.run_execution_worker("test-worker")

            self.assertFalse(out1["ok"])
            self.assertEqual(out1["status"], "failed_max_retries")
            self.assertEqual(self.store.queue_items(), [])

            ledger = self.store.ledger_items()
            statuses = [x["status"] for x in ledger]
            self.assertIn("claimed", statuses)
            self.assertIn("running", statuses)
            self.assertIn("failed_max_retries", statuses)
            self.assertNotIn("retry_scheduled", statuses)


if __name__ == "__main__":
    unittest.main()

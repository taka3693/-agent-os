"""Tests for unified retry state management."""
import unittest
from runner.retry_state import (
    ensure_retry_state,
    can_retry,
    increment_retry,
    get_retry_summary,
    sync_from_legacy,
    sync_to_legacy,
)


class TestRetryState(unittest.TestCase):
    def test_ensure_retry_state_creates_defaults(self):
        task = {}
        task = ensure_retry_state(task)
        self.assertIn("retry_state", task)
        self.assertEqual(task["retry_state"]["total_retries"], 0)
        self.assertEqual(task["retry_state"]["max_total_retries"], 10)

    def test_can_retry_true_when_under_limit(self):
        task = ensure_retry_state({})
        self.assertTrue(can_retry(task))

    def test_can_retry_false_when_at_limit(self):
        task = ensure_retry_state({})
        task["retry_state"]["total_retries"] = 10
        self.assertFalse(can_retry(task))

    def test_increment_retry_updates_category_and_total(self):
        task = ensure_retry_state({})
        task = increment_retry(task, category="worker", reason="timeout")
        self.assertEqual(task["retry_state"]["worker_retries"], 1)
        self.assertEqual(task["retry_state"]["total_retries"], 1)
        self.assertEqual(task["retry_state"]["last_retry_reason"], "timeout")

    def test_increment_multiple_categories(self):
        task = ensure_retry_state({})
        task = increment_retry(task, category="worker", reason="fail1")
        task = increment_retry(task, category="schedule", reason="fail2")
        task = increment_retry(task, category="recovery", reason="fail3")
        
        self.assertEqual(task["retry_state"]["worker_retries"], 1)
        self.assertEqual(task["retry_state"]["schedule_retries"], 1)
        self.assertEqual(task["retry_state"]["recovery_retries"], 1)
        self.assertEqual(task["retry_state"]["total_retries"], 3)

    def test_get_retry_summary(self):
        task = ensure_retry_state({})
        task = increment_retry(task, category="worker", reason="test")
        summary = get_retry_summary(task)
        
        self.assertEqual(summary["worker"], 1)
        self.assertEqual(summary["total"], 1)
        self.assertTrue(summary["can_retry"])

    def test_sync_from_legacy(self):
        task = {
            "budget": {"spent_retries_total": 2},
            "schedule": {"retry_count": 1},
            "recovery": {"recovery_count": 1},
        }
        task = sync_from_legacy(task)
        
        self.assertEqual(task["retry_state"]["worker_retries"], 2)
        self.assertEqual(task["retry_state"]["schedule_retries"], 1)
        self.assertEqual(task["retry_state"]["recovery_retries"], 1)
        self.assertEqual(task["retry_state"]["total_retries"], 4)

    def test_sync_to_legacy(self):
        task = ensure_retry_state({})
        task["retry_state"]["worker_retries"] = 3
        task["retry_state"]["schedule_retries"] = 2
        task["retry_state"]["recovery_retries"] = 1
        
        task = sync_to_legacy(task)
        
        self.assertEqual(task["budget"]["spent_retries_total"], 3)
        self.assertEqual(task["schedule"]["retry_count"], 2)
        self.assertEqual(task["recovery"]["recovery_count"], 1)


if __name__ == "__main__":
    unittest.main()

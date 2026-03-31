from __future__ import annotations

import unittest

from ops.health import evaluate_health_snapshot


class TestHealthEvaluator(unittest.TestCase):
    def test_healthy_snapshot(self) -> None:
        result = evaluate_health_snapshot(
            {
                "tasks": {
                    "counts": {
                        "queued": 0,
                        "running": 0,
                        "awaiting_approval": 0,
                        "completed": 0,
                        "failed": 0,
                    }
                },
                "sessions": {
                    "largest_bytes": 123,
                    "top": [],
                },
            },
            session_warn_bytes=1000,
        )

        self.assertEqual(result["health_score"], 100)
        self.assertEqual(result["signals"], ["healthy"])
        self.assertEqual(result["risks"], [])
        self.assertEqual(result["recommended_actions"], [])

    def test_session_oversize_recommends_archive(self) -> None:
        result = evaluate_health_snapshot(
            {
                "tasks": {"counts": {}},
                "sessions": {
                    "largest_bytes": 5000,
                    "top": [{"basename": "sess-a.jsonl", "bytes": 5000}],
                },
            },
            session_warn_bytes=1000,
        )

        self.assertIn("session_context_growth_detected", result["signals"])
        self.assertEqual(result["health_score"], 80)
        self.assertEqual(result["risks"][0]["code"], "session_oversize")
        self.assertEqual(
            result["recommended_actions"][0]["action"],
            "session.archive",
        )
        self.assertEqual(
            result["recommended_actions"][0]["args"]["target_basename"],
            "sess-a.jsonl",
        )

    def test_failed_and_approval_backlog_reduce_score(self) -> None:
        result = evaluate_health_snapshot(
            {
                "tasks": {
                    "counts": {
                        "failed": 4,
                        "awaiting_approval": 3,
                    }
                },
                "sessions": {
                    "largest_bytes": 0,
                    "top": [],
                },
            },
            failed_task_warn_count=3,
            awaiting_approval_warn_count=3,
        )

        self.assertIn("failed_tasks_accumulating", result["signals"])
        self.assertIn("approval_queue_backlog", result["signals"])
        self.assertEqual(result["health_score"], 60)
        self.assertEqual(len(result["risks"]), 2)


if __name__ == "__main__":
    unittest.main()

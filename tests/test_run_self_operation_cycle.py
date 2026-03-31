from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.cooldown import mark_emitted
from runner.run_self_operation_cycle import run_self_operation_cycle


class TestRunSelfOperationCycle(unittest.TestCase):
    def test_cycle_returns_healthy_when_no_signals(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "queued").mkdir()

            out = run_self_operation_cycle(
                tasks_root=root,
                session_sizes=[],
                session_warn_bytes=1000,
            )

            self.assertEqual(out["evaluation"]["health_score"], 100)
            self.assertEqual(out["evaluation"]["signals"], ["healthy"])
            self.assertEqual(out["evaluation"]["recommended_actions"], [])
            self.assertEqual(out["session_hygiene"]["archive_candidates"], [])
            self.assertEqual(out["session_hygiene"]["recommended_actions"], [])
            self.assertEqual(out["queues"]["evaluation"]["auto_allowed"], [])
            self.assertEqual(out["queues"]["evaluation"]["approval_required"], [])
            self.assertEqual(out["queues"]["evaluation"]["forbidden"], [])
            self.assertEqual(out["queues"]["session_hygiene"]["auto_allowed"], [])
            self.assertEqual(out["queues"]["session_hygiene"]["approval_required"], [])
            self.assertEqual(out["queues"]["session_hygiene"]["forbidden"], [])
            self.assertNotIn("storage", out)

    def test_cycle_adds_policy_to_recommended_actions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "failed").mkdir()
            (root / "failed" / "a.json").write_text("{}", encoding="utf-8")

            out = run_self_operation_cycle(
                tasks_root=root,
                session_sizes=[
                    {"basename": "sess-big.jsonl", "bytes": 5000},
                ],
                session_warn_bytes=1000,
            )

            actions = out["evaluation"]["recommended_actions"]

            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["action"], "session.archive")
            self.assertEqual(actions[0]["policy"], "approval_required")
            self.assertEqual(
                actions[0]["args"]["target_basename"],
                "sess-big.jsonl",
            )

            q = out["queues"]["evaluation"]
            self.assertEqual(q["auto_allowed"], [])
            self.assertEqual(len(q["approval_required"]), 1)
            self.assertEqual(q["approval_required"][0]["action"], "session.archive")
            self.assertEqual(q["forbidden"], [])

    def test_cycle_writes_latest_and_history_when_state_root_given(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tasks_root = root / "tasks"
            state_root = root / "state"
            (tasks_root / "queued").mkdir(parents=True)

            out = run_self_operation_cycle(
                tasks_root=tasks_root,
                state_root=state_root,
                session_sizes=[],
                session_warn_bytes=1000,
            )

            self.assertIn("storage", out)

            latest_path = Path(out["storage"]["latest_path"])
            history_path = Path(out["storage"]["history_path"])

            self.assertTrue(latest_path.exists())
            self.assertTrue(history_path.exists())

            latest_loaded = json.loads(latest_path.read_text(encoding="utf-8"))
            self.assertEqual(latest_loaded["evaluation"]["signals"], ["healthy"])

            lines = history_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            history_loaded = json.loads(lines[0])
            self.assertEqual(history_loaded["evaluation"]["signals"], ["healthy"])

    def test_cycle_includes_session_hygiene_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "queued").mkdir()

            out = run_self_operation_cycle(
                tasks_root=root,
                session_sizes=[
                    {"basename": "active.jsonl", "bytes": 9000},
                    {"basename": "old-big.jsonl", "bytes": 8000},
                    {"basename": "small.jsonl", "bytes": 100},
                ],
                active_session_basenames=["active.jsonl"],
                session_warn_bytes=5000,
            )

            candidates = out["session_hygiene"]["archive_candidates"]

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["basename"], "old-big.jsonl")
            self.assertEqual(candidates[0]["reason"], "oversize_inactive_session")

    def test_cycle_includes_hygiene_recommended_actions_with_policy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "queued").mkdir()

            out = run_self_operation_cycle(
                tasks_root=root,
                session_sizes=[
                    {"basename": "old-big.jsonl", "bytes": 8000},
                ],
                active_session_basenames=[],
                session_warn_bytes=5000,
            )

            actions = out["session_hygiene"]["recommended_actions"]

            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["action"], "session.archive")
            self.assertEqual(
                actions[0]["args"]["target_basename"],
                "old-big.jsonl",
            )
            self.assertEqual(actions[0]["source"], "session_hygiene")
            self.assertEqual(actions[0]["policy"], "approval_required")

            q = out["queues"]["session_hygiene"]
            self.assertEqual(q["auto_allowed"], [])
            self.assertEqual(len(q["approval_required"]), 1)
            self.assertEqual(
                q["approval_required"][0]["args"]["target_basename"],
                "old-big.jsonl",
            )
            self.assertEqual(q["forbidden"], [])

    def test_cycle_suppresses_hygiene_action_within_cooldown_when_state_root_given(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tasks_root = root / "tasks"
            state_root = root / "state"
            (tasks_root / "queued").mkdir(parents=True)

            mark_emitted(
                state_root,
                "session.archive:old-big.jsonl",
                "2026-03-12T00:00:00+00:00",
            )

            out = run_self_operation_cycle(
                tasks_root=tasks_root,
                state_root=state_root,
                session_sizes=[
                    {"basename": "old-big.jsonl", "bytes": 8000},
                ],
                active_session_basenames=[],
                session_warn_bytes=5000,
                approval_cooldown_seconds=3600,
                now_iso="2026-03-12T00:30:00+00:00",
            )

            self.assertEqual(
                out["session_hygiene"]["archive_candidates"][0]["basename"],
                "old-big.jsonl",
            )
            self.assertEqual(out["session_hygiene"]["recommended_actions"], [])
            self.assertEqual(
                out["queues"]["session_hygiene"]["approval_required"],
                [],
            )


    def test_persists_approval_required_actions_to_queue(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tasks_root = root / "tasks"
            state_root = root / "state"
            tasks_root.mkdir(parents=True, exist_ok=True)

            run_self_operation_cycle(
                tasks_root=tasks_root,
                state_root=state_root,
                session_sizes=[
                    {"basename": "old-big.jsonl", "bytes": 8000},
                ],
                active_session_basenames=[],
                session_warn_bytes=5000,
                approval_cooldown_seconds=3600,
                now_iso="2026-03-12T12:00:00Z",
            )

            qpath = state_root / "approval_queue.jsonl"
            self.assertTrue(qpath.exists())

            lines = qpath.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)

            payload = json.loads(lines[0])
            self.assertEqual(payload["timestamp"], "2026-03-12T12:00:00Z")
            self.assertEqual(payload["action"], "session.archive")
            self.assertEqual(payload["args"], {"target_basename": "old-big.jsonl"})
            self.assertEqual(payload["policy"], "approval_required")
            self.assertEqual(payload["source"], "evaluation")


    def test_does_not_append_duplicate_approval_across_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tasks_root = root / "tasks"
            state_root = root / "state"
            tasks_root.mkdir(parents=True, exist_ok=True)

            kwargs = dict(
                tasks_root=tasks_root,
                state_root=state_root,
                session_sizes=[{"basename": "old-big.jsonl", "bytes": 8000}],
                active_session_basenames=[],
                session_warn_bytes=5000,
                approval_cooldown_seconds=3600,
            )

            run_self_operation_cycle(
                **kwargs,
                now_iso="2026-03-12T12:00:00Z",
            )
            run_self_operation_cycle(
                **kwargs,
                now_iso="2026-03-12T12:10:00Z",
            )

            qpath = state_root / "approval_queue.jsonl"
            self.assertTrue(qpath.exists())

            lines = qpath.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)

            payload = json.loads(lines[0])
            self.assertEqual(payload["fingerprint"], "session.archive:old-big.jsonl")


if __name__ == "__main__":
    unittest.main()

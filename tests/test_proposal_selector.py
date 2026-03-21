from __future__ import annotations

import json
import tempfile
import unittest
from importlib import reload
from pathlib import Path


class TestProposalSelector(unittest.TestCase):
    def setUp(self) -> None:
        import tools.proposal_selector as selector
        self.selector = reload(selector)

    def _bind_state(self, state_dir: Path) -> None:
        self.selector.STATE_DIR = state_dir
        self.selector.PROPOSAL_QUEUE = state_dir / "proposal_queue.jsonl"
        self.selector.PROPOSAL_TRANSITIONS = state_dir / "proposal_state_transitions.jsonl"
        self.selector.SIMULATION_RESULTS = state_dir / "simulation_results.jsonl"

    def _write_queue(self, rows: list[dict]) -> None:
        self.selector.PROPOSAL_QUEUE.parent.mkdir(parents=True, exist_ok=True)
        with self.selector.PROPOSAL_QUEUE.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_selects_pending_commit_candidate_preferring_execution_mode(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            self._bind_state(state_dir)

            self._write_queue([
                {
                    "proposal_id": "p-router",
                    "created_at": "2026-03-20T10:00:00+0900",
                    "timestamp": "2026-03-20T10:00:00+0900",
                    "review_status": "pending",
                    "proposal_candidate": True,
                    "commit_candidate": True,
                    "guard_failed": False,
                    "mode": "router",
                },
                {
                    "proposal_id": "p-exec",
                    "created_at": "2026-03-20T10:01:00+0900",
                    "timestamp": "2026-03-20T10:01:00+0900",
                    "review_status": "pending",
                    "proposal_candidate": True,
                    "commit_candidate": True,
                    "guard_failed": False,
                    "mode": "execution",
                },
            ])

            selected = self.selector.select_proposal_for_simulation()
            self.assertIsNotNone(selected)
            self.assertEqual(selected["proposal_id"], "p-exec")

    def test_run_selector_once_stores_candidate_and_transition(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            self._bind_state(state_dir)

            self._write_queue([
                {
                    "proposal_id": "p-001",
                    "created_at": "2026-03-20T10:01:00+0900",
                    "timestamp": "2026-03-20T10:01:00+0900",
                    "review_status": "pending",
                    "proposal_candidate": True,
                    "proposal_summary": "candidate",
                    "pipeline_summary": "pipeline",
                    "commit_candidate": True,
                    "guard_failed": False,
                    "mode": "execution",
                    "reasons": [],
                }
            ])

            out = self.selector.run_selector_once()
            self.assertTrue(out["ok"])
            self.assertEqual(out["proposal_id"], "p-001")

            sim_rows = self.selector._load_jsonl(self.selector.SIMULATION_RESULTS)
            self.assertEqual(len(sim_rows), 1)
            self.assertEqual(sim_rows[0]["proposal_id"], "p-001")
            self.assertTrue(sim_rows[0]["simulation_candidate"])

            tr_rows = self.selector._load_jsonl(self.selector.PROPOSAL_TRANSITIONS)
            self.assertEqual(len(tr_rows), 1)
            self.assertEqual(tr_rows[0]["proposal_id"], "p-001")
            self.assertEqual(tr_rows[0]["event"], "simulation_candidate_built")
            self.assertEqual(tr_rows[0]["new_state"], "selected")

    def test_returns_no_selectable_proposals_when_only_guard_failed_or_non_pending(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            self._bind_state(state_dir)

            self._write_queue([
                {
                    "proposal_id": "p-guard",
                    "created_at": "2026-03-20T10:01:00+0900",
                    "timestamp": "2026-03-20T10:01:00+0900",
                    "review_status": "pending",
                    "commit_candidate": True,
                    "guard_failed": True,
                    "mode": "execution",
                },
                {
                    "proposal_id": "p-reviewed",
                    "created_at": "2026-03-20T10:02:00+0900",
                    "timestamp": "2026-03-20T10:02:00+0900",
                    "review_status": "accepted",
                    "commit_candidate": True,
                    "guard_failed": False,
                    "mode": "execution",
                },
            ])

            out = self.selector.run_selector_once()
            self.assertEqual(out, {"ok": True, "message": "no_selectable_proposals"})

    def test_already_selected_proposal_is_not_selected_again(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            state_dir.mkdir(parents=True, exist_ok=True)
            self._bind_state(state_dir)

            self._write_queue([
                {
                    "proposal_id": "p-001",
                    "created_at": "2026-03-20T10:01:00+0900",
                    "timestamp": "2026-03-20T10:01:00+0900",
                    "review_status": "pending",
                    "proposal_candidate": True,
                    "proposal_summary": "candidate",
                    "pipeline_summary": "pipeline",
                    "commit_candidate": True,
                    "guard_failed": False,
                    "mode": "execution",
                    "reasons": [],
                }
            ])

            out1 = self.selector.run_selector_once()
            out2 = self.selector.run_selector_once()

            self.assertTrue(out1["ok"])
            self.assertEqual(out1["proposal_id"], "p-001")
            self.assertEqual(out2, {"ok": True, "message": "no_selectable_proposals"})

            sim_rows = self.selector._load_jsonl(self.selector.SIMULATION_RESULTS)
            self.assertEqual(len(sim_rows), 1)

            tr_rows = self.selector._load_jsonl(self.selector.PROPOSAL_TRANSITIONS)
            self.assertEqual(len(tr_rows), 1)
            self.assertEqual(tr_rows[0]["new_state"], "selected")


if __name__ == "__main__":
    unittest.main()

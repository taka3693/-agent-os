#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"
PROPOSAL_QUEUE = STATE_DIR / "proposal_queue.jsonl"
PROPOSAL_TRANSITIONS = STATE_DIR / "proposal_state_transitions.jsonl"
SIMULATION_RESULTS = STATE_DIR / "simulation_results.jsonl"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_proposal_queue() -> List[Dict[str, Any]]:
    return _load_jsonl(PROPOSAL_QUEUE)


def _latest_transition_state_by_proposal() -> Dict[str, str]:
    latest: Dict[str, str] = {}
    for row in _load_jsonl(PROPOSAL_TRANSITIONS):
        proposal_id = row.get("proposal_id")
        if not proposal_id:
            continue
        if "new_state" in row:
            latest[proposal_id] = row["new_state"]
        elif row.get("event") == "simulation_candidate_built":
            latest[proposal_id] = "selected"
    return latest


def rank_proposals(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def score(r: Dict[str, Any]) -> tuple:
        review_status = r.get("review_status")
        commit_candidate = bool(r.get("commit_candidate"))
        guard_failed = bool(r.get("guard_failed"))
        mode = r.get("mode")

        return (
            1 if review_status == "pending" else 0,
            1 if commit_candidate else 0,
            0 if guard_failed else 1,
            1 if mode == "execution" else 0,
            r.get("timestamp", ""),
            r.get("created_at", ""),
        )

    return sorted(rows, key=score, reverse=True)


def select_proposal_for_simulation() -> Optional[Dict[str, Any]]:
    rows = load_proposal_queue()
    if not rows:
        return None

    latest_state = _latest_transition_state_by_proposal()
    ranked = rank_proposals(rows)
    for row in ranked:
        proposal_id = row.get("proposal_id")
        if row.get("review_status") != "pending":
            continue
        if not row.get("commit_candidate"):
            continue
        if row.get("guard_failed"):
            continue
        if proposal_id and latest_state.get(proposal_id) in ("selected", "reviewed", "apply_ready"):
            continue
        return row
    return None


def record_selector_transition(proposal_id: str, event: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    row: Dict[str, Any] = {
        "ts": _now(),
        "proposal_id": proposal_id,
        "event": event,
        "old_state": "pending",
        "new_state": "selected",
    }
    if metadata:
        row["metadata"] = metadata
    _append_jsonl(PROPOSAL_TRANSITIONS, row)


def build_simulation_candidate(selected: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "simulation_candidate": True,
        "proposal_id": selected.get("proposal_id"),
        "selected_at": _now(),
        "source": "proposal_selector",
        "mode": selected.get("mode"),
        "proposal_summary": selected.get("proposal_summary"),
        "pipeline_summary": selected.get("pipeline_summary"),
        "commit_candidate": selected.get("commit_candidate"),
        "guard_failed": selected.get("guard_failed"),
        "reasons": selected.get("reasons", []),
    }


def store_simulation_candidate(candidate: Dict[str, Any]) -> None:
    _append_jsonl(SIMULATION_RESULTS, candidate)


def run_selector_once() -> Dict[str, Any]:
    selected = select_proposal_for_simulation()
    if not selected:
        return {"ok": True, "message": "no_selectable_proposals"}

    proposal_id = selected["proposal_id"]
    candidate = build_simulation_candidate(selected)
    store_simulation_candidate(candidate)
    record_selector_transition(proposal_id, "simulation_candidate_built", {
        "source": "proposal_selector",
        "mode": selected.get("mode"),
    })

    return {
        "ok": True,
        "proposal_id": proposal_id,
        "selected_mode": selected.get("mode"),
        "simulation_candidate": True,
    }


if __name__ == "__main__":
    print(json.dumps(run_selector_once(), ensure_ascii=False, indent=2))


# alias for compatibility
def select_proposals(*args, **kwargs):
    return select_proposals_for_execution(*args, **kwargs)

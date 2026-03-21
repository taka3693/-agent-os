from typing import Dict, Any, List
import json
from datetime import datetime
from pathlib import Path

from tools.state import append_jsonl
from tools import proposal_selector
from tools import simulation

BASE = Path("state")
BASE.mkdir(exist_ok=True)

SIM_FILE = BASE / "simulation_results.jsonl"
TRANS_FILE = BASE / "proposal_state_transitions.jsonl"


def _transition(proposal_id: str, new_state: str):
    append_jsonl(TRANS_FILE, {
        "ts": datetime.utcnow().isoformat(),
        "proposal_id": proposal_id,
        "new_state": new_state,
    })


def run_simulation_once(mode: str = "execution") -> List[Dict[str, Any]]:
    rows = proposal_selector.select_proposals(mode=mode)
    results = []

    for p in rows:
        proposal_id = p.get("proposal_id") or p.get("id")
        if not proposal_id:
            continue

        candidate = simulation.build_apply_simulation_candidate(p)
        eval_result = simulation.evaluate_simulation_candidate(candidate)
        passed = bool(eval_result.get("passed"))

        append_jsonl(SIM_FILE, {
            "ts": datetime.utcnow().isoformat(),
            "proposal_id": proposal_id,
            "candidate": candidate,
            "result": eval_result,
        })

        _transition(proposal_id, "reviewed" if passed else "rejected")

        results.append({
            "proposal_id": proposal_id,
            "passed": passed,
            "candidate": candidate,
            "result": eval_result,
        })

    return results


if __name__ == "__main__":
    print(json.dumps(run_simulation_once(), ensure_ascii=False, indent=2))

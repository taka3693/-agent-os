from tools.simulation_runner import run_simulation_once
from tools.state import read_jsonl
from tools.paths import PROPOSAL_TRANSITIONS, SIMULATION_RESULTS


def test_simulation_runner_flow(tmp_path, monkeypatch):
    from tools import proposal_selector

    def fake_select_proposals(mode="execution"):
        return [{
            "proposal_id": "p-test-1",
            "commit_candidate": True,
            "guard_failed": False
        }]

    monkeypatch.setattr(proposal_selector, "select_proposals", fake_select_proposals)

    from tools import simulation

    def fake_build(p):
        return {"dummy": True}

    def fake_eval(c):
        return {"passed": True}

    monkeypatch.setattr(simulation, "build_apply_simulation_candidate", fake_build)
    monkeypatch.setattr(simulation, "evaluate_simulation_candidate", fake_eval)

    results = run_simulation_once()

    assert len(results) == 1
    assert results[0]["passed"] is True

    sim_rows = read_jsonl(SIMULATION_RESULTS)
    assert any(r["proposal_id"] == "p-test-1" for r in sim_rows)

    trans_rows = read_jsonl(PROPOSAL_TRANSITIONS)
    assert any(
        r["proposal_id"] == "p-test-1" and r["new_state"] == "reviewed"
        for r in trans_rows
    )

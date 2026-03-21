from pathlib import Path

BASE = Path("state")
BASE.mkdir(exist_ok=True)

PROPOSAL_TRANSITIONS = BASE / "proposal_state_transitions.jsonl"
SIMULATION_RESULTS = BASE / "simulation_results.jsonl"

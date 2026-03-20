import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run_cmd(*args):
    cp = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(cp.stdout)

def test_run_decision_json_contract():
    obj = run_cmd(
        "tools/run_decision.py",
        "マネタイズ重視で 買い切り または サブスク どっちがいい？",
    )
    assert obj["selected_skill"] == "decision"

    r = obj["task_result"]
    for key in [
        "summary", "goal", "options", "criteria", "weights",
        "comparison", "scores", "recommendation",
        "reasoning", "rejected", "next_actions", "preset"
    ]:
        assert key in r

    assert isinstance(r["options"], list) and len(r["options"]) >= 2
    assert r["recommendation"]["option"] in r["options"]

def test_run_agent_os_request_decision_contract():
    obj = run_cmd(
        "tools/run_agent_os_request.py",
        "マネタイズ重視で 買い切り または サブスク どっちがいい？",
    )

    assert obj["ok"] is True
    assert obj["selected_skill"] == "decision"
    assert obj["route_reason"] == "decision_keyword_match"
    assert "pipeline" in obj
    assert "plan" in obj
    assert "planning_mode" in obj

    reply = obj["reply_text"]
    assert "router 受付完了" in reply
    assert "selected_skill: decision" in reply
    assert "route_reason: decision_keyword_match" in reply
    assert "task: decision" in reply
    assert "bridge: selected_skill=decision route_reason=decision_keyword_match" in reply

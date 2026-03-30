import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CLI = ROOT / "tools" / "run_agent_os_request.py"
spec = importlib.util.spec_from_file_location("run_agent_os_request", str(CLI))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_step73_validate_only_router_step_planned():
    text = 'aos json {"validate_only": true, "steps": [{"command": "aos router 調査"}]}'
    out = mod.handle_message_with_json(text)
    assert out["ok"] is True
    assert out["validate_only"] is True
    assert isinstance(out["results"], list) and len(out["results"]) == 1
    assert out["results"][0]["status"] == "planned"
    assert out["results"][0]["validation_action"] == "plan_router_step"
    assert out["results"][0]["mode"] == "validation"

def test_step73_execute_router_step():
    text = 'aos json {"validate_only": false, "steps": [{"command": "aos router 比較して"}]}'
    out = mod.handle_message_with_json(text)
    assert out["ok"] is True
    assert out["validate_only"] is False
    assert isinstance(out["results"], list) and len(out["results"]) == 1
    assert out["results"][0]["status"] == "completed"
    assert out["results"][0]["mode"] == "router"

if __name__ == "__main__":
    test_step73_validate_only_router_step_planned()
    test_step73_execute_router_step()
    print("PASS: Step73 json batch router OK")

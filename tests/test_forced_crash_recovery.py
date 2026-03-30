import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("run_agent_os_request", "tools/run_agent_os_request.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

out = mod.simulate_forced_crash_and_recover(
    "aos router 比較して整理したい",
    chat_id="6474742983",
)

print(out)

assert out["ok"] is True, f"recovery failed: {out}"
assert out["phase"] == "recovered", f"unexpected phase: {out}"
assert isinstance(out.get("crash_target"), str) and out["crash_target"].endswith(".json")
assert Path(out["crash_target"]).exists(), "recovered file missing"

rollback = out.get("rollback_info") or {}
assert rollback.get("latest_path"), f"rollback latest_path missing: {rollback}"
assert Path(rollback["latest_path"]).exists(), "rollback latest file missing"

restored_keys = out.get("restored_keys") or []
assert "task_id" in restored_keys, f"restored content unexpected: {restored_keys}"

print("PASS: forced crash -> auto recovery OK")

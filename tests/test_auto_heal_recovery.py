import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("run_agent_os_request", "tools/run_agent_os_request.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

rate_file = Path("state/policy/rate_limits.json")
if rate_file.exists():
    rate_file.unlink()

# 1回目: 正常deployして rollback を作る
first = mod.run_router_command_full("aos router 比較して整理したい", chat_id="6474742983")
assert first.get("executed_action") == "deploy", first
assert first.get("rollback_info"), first

# 2回目: rate limit で block されるが auto-heal で復元される
second = mod.run_router_command_full("aos router 比較して整理したい", chat_id="6474742983")
print(second)

assert second.get("next_action") == "deploy", second
assert second.get("auto_heal", {}).get("ok") is True, second
assert second.get("executed_action") == "deploy", second
assert second.get("rollback_info"), second
artifact = second.get("deploy_artifact") or {}
assert Path(artifact.get("json_path", "")).exists(), second
assert "auto-healed" in str(second.get("execution_log")), second

print("PASS: auto-heal recovery OK")

#!/usr/bin/env python3
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from runner.run_execution_task import run_task as run_skill_task
except ModuleNotFoundError:
    import sys
    from pathlib import Path as _Path
    ROOT = _Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from runner.run_execution_task import run_task as run_skill_task
from tools.log_execution_result import append_execution_result
from tools.update_execution_result import update_execution_result



def decision_cycle(request: str, cycles: int = 2) -> Dict[str, Any]:
    script_path = ROOT / "tools" / "decision_cycle.sh"

    if not script_path.exists():
        return {"ok": False, "error": "decision_cycle_not_found", "path": str(script_path)}

    try:
        result = subprocess.run(
            ["bash", str(script_path), request, str(cycles)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(ROOT),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "decision_cycle_timeout"}
    except Exception as e:
        return {"ok": False, "error": "decision_cycle_error", "detail": str(e)}

    if result.returncode != 0:
        return {
            "ok": False,
            "error": "decision_cycle_failed",
            "detail": result.stderr[-500:] if result.stderr else "Unknown error",
        }

    lines = result.stdout.strip().split("\n")
    final_recommendation = None
    for line in reversed(lines):
        if '"option"' in line and '"score"' in line:
            try:
                if line.strip().startswith('{'):
                    final_recommendation = json.loads(line)
                break
            except Exception:
                pass

    weights_history = [line for line in lines if "Weights:" in line]
    feedback_history = []
    for line in lines:
        if "success_rate" in line and "Feedback:" in line:
            try:
                feedback_history.append(json.loads(line.split("Feedback:")[1].strip()))
            except Exception:
                pass

    return {
        "ok": True,
        "recommendation": final_recommendation,
        "weights_history": weights_history,
        "feedback_history": feedback_history,
        "cycles_executed": cycles,
    }


def run_task_action(task_payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return run_skill_task(task_payload)
    except Exception as e:
        return {"ok": False, "error": "run_task_failed", "detail": f"{type(e).__name__}: {e}"}


def auto_task_action(query: str) -> Dict[str, Any]:
    try:
        cp = subprocess.run(
            ["python3", str(ROOT / "tools" / "run_agent_os_request.py"), f"aos router {query}"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(ROOT),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "auto_task_timeout"}
    except Exception as e:
        return {"ok": False, "error": "auto_task_router_error", "detail": str(e)}

    stdout = (cp.stdout or "").strip()
    stderr = (cp.stderr or "").strip()

    try:
        router_out = json.loads(stdout) if stdout else {}
    except Exception as e:
        return {
            "ok": False,
            "error": "auto_task_invalid_router_json",
            "detail": str(e),
            "stdout": stdout[-500:],
            "stderr": stderr[-500:],
        }

    if not isinstance(router_out, dict) or not router_out.get("ok"):
        return {
            "ok": False,
            "error": "auto_task_router_failed",
            "router_out": router_out,
            "stderr": stderr[-500:] if stderr else None,
        }

    task_payload = {
        "selected_skill": router_out.get("selected_skill"),
        "query": query,
        "router_result": router_out.get("router_result", {}),
        "plan": router_out.get("plan", {}),
        "task_id": router_out.get("task_id"),
        "task_path": router_out.get("task_path"),
    }
    result = run_task_action(task_payload)
    result["router"] = {
        "selected_skill": router_out.get("selected_skill"),
        "route_reason": router_out.get("route_reason"),
        "task_id": router_out.get("task_id"),
    }
    return result




def looks_like_decision_query(query: str) -> bool:
    if not query:
        return False
    q = query.lower()
    patterns = [
        "どちら",
        "どっち",
        "どれが良い",
        "どれがいい",
        "aとb",
        "a or b",
        " or ",
        "か、それとも",
    ]
    return any(p in q for p in patterns)


def decide_execute_action(query: str) -> Dict[str, Any]:
    try:
        cp = subprocess.run(
            ["python3", str(ROOT / "tools" / "decision_to_execution.py"), query],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(ROOT),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "decide_execute_timeout"}
    except Exception as e:
        return {"ok": False, "error": "decide_execute_error", "detail": str(e)}

    stdout = (cp.stdout or "").strip()
    stderr = (cp.stderr or "").strip()

    if not stdout:
        return {
            "ok": False,
            "error": "decide_execute_empty_stdout",
            "stderr": stderr[-500:] if stderr else None,
        }

    try:
        return json.loads(stdout)
    except Exception as e:
        return {
            "ok": False,
            "error": "decide_execute_invalid_json",
            "detail": str(e),
            "stdout": stdout[-500:],
            "stderr": stderr[-500:] if stderr else None,
        }






def redecide_action(query: str) -> Dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "redecide_with_history.py"),
                "--input",
                query,
                "--text",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "redecide_timeout", "stdout": "", "stderr": "timeout"}
    except Exception as e:
        return {"ok": False, "error": "redecide_error", "detail": str(e), "stdout": "", "stderr": str(e)}

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    return {
        "ok": completed.returncode == 0,
        "action": "redecide",
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def maybe_log_execution_result(action: str, query: str, result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {"ok": False, "error": "result_not_dict"}

    execution_out = None
    decision_out = None
    log_source = None

    # 1) decide_execute 直下
    if isinstance(result.get("execution_out"), dict):
        execution_out = result.get("execution_out")
        decision_out = result.get("decision_out")
        log_source = "direct"

    # 2) redecide の1段ネスト
    nested = result.get("result")
    if execution_out is None and isinstance(nested, dict):
        if isinstance(nested.get("execution_out"), dict):
            execution_out = nested.get("execution_out")
            decision_out = nested.get("decision_out")
            log_source = "nested_result"

    # 3) redecide の2段ネスト
    nested2 = nested.get("result") if isinstance(nested, dict) else None
    if execution_out is None and isinstance(nested2, dict):
        if isinstance(nested2.get("execution_out"), dict):
            execution_out = nested2.get("execution_out")
            decision_out = nested2.get("decision_out")
            log_source = "nested_result_result"

    if execution_out is None:
        return {"ok": False, "error": "execution_out_not_found"}

    task_result = decision_out.get("task_result", {}) if isinstance(decision_out, dict) else {}
    decision_meta = task_result.get("decision", {}) if isinstance(task_result, dict) else {}

    record = {
        "action": action,
        "query": query,
        "result_flag": "success" if execution_out.get("ok") else "fail",
        "decision_summary": task_result.get("summary"),
        "decision_conclusion": decision_meta.get("conclusion"),
        "decision_winner": decision_meta.get("winner"),
        "decision_deprioritized": decision_meta.get("deprioritized"),
        "execution_skill": execution_out.get("skill"),
        "execution_summary": execution_out.get("summary"),
        "execution_output": execution_out.get("output"),
        "execution_steps": execution_out.get("steps"),
        "execution_notes": execution_out.get("notes"),
        "completion_definition": execution_out.get("completion_definition"),
        "source": log_source,
    }

    if isinstance(decision_out, dict):
        router = decision_out.get("router", {})
        if isinstance(router, dict):
            record["task_id"] = router.get("task_id")
            record["selected_skill"] = router.get("selected_skill")
            record["route_reason"] = router.get("route_reason")

    return append_execution_result(record)



def resolve_query_arg(argv):
    if not argv:
        return None
    if argv[0] == "--input":
        if len(argv) < 2:
            return None
        return argv[1]
    return argv[0]

def decision_history_action(limit: int = 5) -> Dict[str, Any]:

    try:
        cp = subprocess.run(
            ["python3", str(ROOT / "tools" / "read_decision_runs.py"), str(limit), "text"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(ROOT),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "decision_history_timeout"}
    except Exception as e:
        return {"ok": False, "error": "decision_history_error", "detail": str(e)}

    stdout = (cp.stdout or "").strip()
    stderr = (cp.stderr or "").strip()

    if not stdout:
        return {
            "ok": False,
            "error": "decision_history_empty_stdout",
            "stderr": stderr[-500:] if stderr else None,
        }

    return {
        "ok": True,
        "history": stdout,
    }


def generate_task_id() -> str:
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
    rand = uuid.uuid4().hex[:6]
    return f"task-{ts}-{rand}"

def main():
    available_actions = [
        "decision_cycle",
        "run_task",
        "auto_task",
        "decide_execute",
        "redecide",
        "decision_history",
        "health",
    ]

    if len(sys.argv) < 2:
        print(json.dumps({
            "ok": False,
            "error": "missing_action",
            "usage": "entrypoint.py <action> [args...]",
            "available_actions": available_actions,
        }, ensure_ascii=False))
        sys.exit(1)

    action = sys.argv[1]

    if action == "decision_cycle":
        if len(sys.argv) < 3:
            print(json.dumps({"ok": False, "error": "missing_request"}, ensure_ascii=False))
            sys.exit(1)

        request = sys.argv[2]
        cycles = 2
        if len(sys.argv) > 3:
            try:
                cycles = int(sys.argv[3])
                if cycles <= 0 or cycles > 10:
                    raise ValueError
            except ValueError:
                print(json.dumps({"ok": False, "error": "invalid_cycles"}, ensure_ascii=False))
                sys.exit(1)

        result = decision_cycle(request, cycles)

    elif action == "run_task":
        if len(sys.argv) < 3:
            print(json.dumps({"ok": False, "error": "missing_task_payload"}, ensure_ascii=False))
            sys.exit(1)

        try:
            task_payload = json.loads(sys.argv[2])
        except Exception as e:
            print(json.dumps({
                "ok": False,
                "error": "invalid_task_payload_json",
                "detail": str(e),
            }, ensure_ascii=False))
            sys.exit(1)

        result = run_task_action(task_payload)

    elif action == "auto_task":
        query = resolve_query_arg(sys.argv[2:])
        if not query:
            print(json.dumps({"ok": False, "error": "missing_query"}, ensure_ascii=False))
            sys.exit(1)

        result = auto_task_action(query)

    elif action == "decide_execute":
        query = resolve_query_arg(sys.argv[2:])
        if not query:
            print(json.dumps({"ok": False, "error": "missing_query"}, ensure_ascii=False))
            sys.exit(1)

        if looks_like_decision_query(query):
            result = decide_execute_action(query)
        else:
            result = decide_execute_action(query)

        task_id = result.get("task_id")

        if not task_id:
            router = result.get("router", {})
            if isinstance(router, dict):
                task_id = router.get("task_id")

        if not task_id:
            decision_out = result.get("decision_out", {})
            if isinstance(decision_out, dict):
                router = decision_out.get("router", {})
                if isinstance(router, dict):
                    task_id = router.get("task_id")

        if not task_id:
            task_id = "task-" + str(hash(query))

        result["task_id"] = task_id

        has_execution_out = False
        if isinstance(result.get("execution_out"), dict):
            has_execution_out = True
        elif isinstance(result.get("result"), dict) and isinstance(result["result"].get("execution_out"), dict):
            has_execution_out = True

        if has_execution_out:
            result["execution_log"] = maybe_log_execution_result("decide_execute", query, result)

            execution_output = ""
            if isinstance(result.get("execution_out"), dict):
                execution_output = result["execution_out"].get("output", "") or ""
            elif isinstance(result.get("result"), dict) and isinstance(result["result"].get("execution_out"), dict):
                execution_output = result["result"]["execution_out"].get("output", "") or ""

            if result.get("ok"):
                result["execution_update"] = update_execution_result(task_id, "success", execution_output)
            else:
                result["execution_update"] = update_execution_result(task_id, "fail", execution_output)
        else:
            result["execution_log"] = {"ok": False, "error": "execution_out_not_found"}
            result["execution_update"] = {"ok": False, "error": "execution_out_not_found"}

    elif action == "redecide":
        argv = sys.argv[2:]

        query = None
        text_mode = False
        limit = None

        i = 0
        while i < len(argv):
            token = argv[i]
            if token == "--input":
                if i + 1 >= len(argv):
                    print(json.dumps({"ok": False, "error": "missing_query"}, ensure_ascii=False))
                    sys.exit(1)
                query = argv[i + 1]
                i += 2
                continue
            if query is None and not token.startswith("--"):
                query = token
                i += 1
                continue
            if token == "--text":
                text_mode = True
                i += 1
                continue
            if token == "--limit":
                if i + 1 >= len(argv):
                    print(json.dumps({"ok": False, "error": "missing_limit"}, ensure_ascii=False))
                    sys.exit(1)
                limit = argv[i + 1]
                i += 2
                continue
            i += 1

        if not query:
            print(json.dumps({"ok": False, "error": "missing_query"}, ensure_ascii=False))
            sys.exit(1)

        result = redecide_action(query)
        if result.get("stdout") is None or result.get("stdout") == "":
            print(f"Error: No output received from redecide action. stderr: {result.get('stderr')}")
            raise ValueError(f"Error with redecide action. stderr: {result.get('stderr')}")

        if result.get("stderr"):
            print(f"stderr from redecide action: {result.get('stderr')}")

        if text_mode:
            print(result.get("stdout"))
        else:
            print(json.dumps(result, ensure_ascii=False))
        return

    elif action == "decision_history":
        limit = 5
        if len(sys.argv) > 2:
            try:
                limit = int(sys.argv[2])
                if limit <= 0:
                    raise ValueError
            except ValueError:
                print(json.dumps({"ok": False, "error": "invalid_limit"}, ensure_ascii=False))
                sys.exit(1)

        result = decision_history_action(limit)

    elif action == "health":
        result = {
            "ok": True,
            "status": "healthy",
            "available_actions": available_actions,
        }

    else:
        result = {
            "ok": False,
            "error": f"unknown_action: {action}",
            "available_actions": available_actions,
        }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

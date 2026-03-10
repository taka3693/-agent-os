from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def parse_bridge_stdout_json(raw: str) -> Dict[str, Any]:
    text = "" if raw is None else str(raw).strip()
    if not text:
        raise ValueError("empty stdout")

    candidates = [text]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        candidates.append(lines[-1])
        if len(lines) > 1:
            candidates.append("".join(lines))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and start <= end:
        candidates.append(text[start:end + 1])

    seen = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    raise ValueError(f"bridge stdout is not valid json: {text[:500]}")


def run_router_command_core(
    query: str,
    *,
    base_dir: Path,
    tasks_dir: Path,
) -> Dict[str, Any]:
    bridge_script = base_dir / "bridge" / "route_to_task.py"
    if not bridge_script.exists():
        return {
            "ok": False,
            "mode": "router",
            "status": "bridge_missing",
            "reason": "bridge_missing",
            "router_result": {},
            "reply_text": f"router 実行失敗\n理由: bridge が存在しません\npath: {bridge_script}",
            "telegram_send": None,
            "telegram_reply_text": f"router 実行失敗\n理由: bridge が存在しません\npath: {bridge_script}",
        }

    cp = subprocess.run(
        [sys.executable, str(bridge_script), str(query or "")],
        capture_output=True,
        text=True,
    )

    stdout = (cp.stdout or "").strip()
    stderr = (cp.stderr or "").strip()

    try:
        route_obj = parse_bridge_stdout_json(stdout)
    except Exception:
        return {
            "ok": False,
            "mode": "router",
            "status": "bridge_invalid_json",
            "reason": "router_invalid_json",
            "router_result": {},
            "reply_text": "router 実行失敗\n理由: bridge 出力が JSON ではありません\nstdout: " + (stdout or "(empty)"),
            "telegram_send": None,
            "telegram_reply_text": "router 実行失敗\n理由: bridge 出力が JSON ではありません\nstdout: " + (stdout or "(empty)"),
        }

    if cp.returncode != 0 or route_obj.get("ok") is False:
        err = route_obj.get("error") or stderr or stdout or "(empty)"
        return {
            "ok": False,
            "mode": "router",
            "status": "bridge_failed",
            "reason": "bridge_failed",
            "router_result": route_obj if isinstance(route_obj, dict) else {},
            "reply_text": f"router 実行失敗\n理由: bridge 実行エラー\n詳細: {err}",
            "telegram_send": None,
            "telegram_reply_text": f"router 実行失敗\n理由: bridge 実行エラー\n詳細: {err}",
        }

    selected_skill = route_obj.get("selected_skill") or "research"
    selected_skills = route_obj.get("selected_skills")
    if not isinstance(selected_skills, list) or not selected_skills:
        selected_skills = [selected_skill]

    route_reason = route_obj.get("route_reason") or (
        "fallback_research" if selected_skill == "research" else f"{selected_skill}_keyword_match"
    )

    route_obj = dict(route_obj)
    route_obj["selected_skill"] = selected_skill
    route_obj["selected_skills"] = selected_skills
    route_obj.setdefault("route_reason", route_reason)
    route_obj.setdefault("pipeline", {
        "primary_skill": selected_skill,
        "skill_chain": selected_skills,
        "chain_length": len(selected_skills),
        "max_chain": 3,
    })
    route_obj.setdefault("plan", {
        "goal": str(query or ""),
        "steps": [{"skill": selected_skill, "purpose": "router step", "done_when": "route selected"}],
        "step_count": len(selected_skills),
        "mode": "autonomous_planning",
    })
    route_obj.setdefault("planning_mode", "autonomous")

    now = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    task_id = route_obj.get("task_id")
    if not isinstance(task_id, str) or not task_id.startswith("task-"):
        task_id = f"task-{now}"

    task_path = tasks_dir / f"{task_id}.json"
    route_obj["task_id"] = task_id
    route_obj["task_path"] = str(task_path)

    task_obj = {
        "task_id": task_id,
        "status": "completed",
        "query": str(query or ""),
        "selected_skill": selected_skill,
        "selected_skills": selected_skills,
        "route_reason": route_reason,
        "router_result": route_obj,
        "pipeline": route_obj.get("pipeline"),
        "plan": route_obj.get("plan"),
        "planning_mode": route_obj.get("planning_mode", "autonomous"),
        "result": {
            "summary": route_obj.get("reply_text") or "",
            "findings": [],
        },
    }
    task_path.write_text(json.dumps(task_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    bridge_reply = route_obj.get("reply_text") or (
        f"selected_skill={selected_skill} route_reason={route_reason}"
    )
    reply_text = (
        "router 受付完了\n"
        f"task: {task_id}\n"
        f"selected_skill: {selected_skill}\n"
        f"route_reason: {route_reason}\n"
        f"bridge: {bridge_reply}"
    )

    return {
        "ok": True,
        "mode": "router",
        "status": "completed",
        "task_id": task_id,
        "task_path": str(task_path),
        "selected_skill": selected_skill,
        "selected_skills": selected_skills,
        "route_reason": route_reason,
        "router_policy": route_obj.get("router_policy"),
        "pipeline": route_obj.get("pipeline"),
        "plan": route_obj.get("plan"),
        "planning_mode": route_obj.get("planning_mode", "autonomous"),
        "router_result": route_obj,
        "reply_text": reply_text,
        "telegram_send": None,
        "telegram_reply_text": reply_text,
    }


def run_router_command_with_optional_telegram(
    query: str,
    *,
    base_dir: Path,
    tasks_dir: Path,
    chat_id: str | int | None,
    send_telegram_message,
) -> Dict[str, Any]:
    out = run_router_command_core(query, base_dir=base_dir, tasks_dir=tasks_dir)

    if chat_id is None:
        return out

    if out.get("telegram_send") is not None:
        return out

    text = out.get("telegram_reply_text") or out.get("reply_text")
    if not isinstance(text, str) or not text.strip():
        return out

    out = dict(out)
    try:
        out["telegram_send"] = send_telegram_message(chat_id, text)
    except Exception as e:
        out["telegram_send"] = {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
        }
    return out


def router_cli_short_circuit(
    argv,
    *,
    run_router_command,
) -> int | None:
    args = list(sys.argv if argv is None else argv)
    norm = [str(x).strip() for x in args if str(x).strip()]
    low = [x.lower() for x in norm]

    router_idx = None
    for i, token in enumerate(low):
        if token in {"router", "route"}:
            router_idx = i
            break

    if router_idx is None:
        return None

    query = " ".join(norm[router_idx + 1:]).strip()

    for flag in ("--query", "--text", "-q", "-t"):
        if flag in low:
            j = low.index(flag)
            if j + 1 < len(norm):
                query = str(norm[j + 1]).strip()
                break

    out = run_router_command(query)
    rc = 0 if out.get("ok") else 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return rc

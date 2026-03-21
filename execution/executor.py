from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from execution.config import ARCHIVE_ROOT, AUDIT_DIR, SESSIONS_DIR, ensure_dirs


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _audit_path() -> Path:
    day = datetime.now().strftime("%Y%m%d")
    return AUDIT_DIR / f"session_hygiene-{day}.jsonl"


def write_audit(payload: Dict[str, Any]) -> None:
    ensure_dirs()
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def current_active_candidate_name() -> str | None:
    newest_path: Path | None = None
    newest_mtime: float = -1.0

    for path in SESSIONS_DIR.glob("*.jsonl"):
        try:
            if not path.is_file() or path.is_symlink():
                continue
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > newest_mtime:
            newest_mtime = mtime
            newest_path = path

    return newest_path.name if newest_path else None


def _validate_target_basename(name: str) -> None:
    if not isinstance(name, str) or not name:
        raise ValueError("target_basename must be a non-empty string")
    if "/" in name or "\\" in name or "\x00" in name:
        raise ValueError("path separators are not allowed")
    if Path(name).name != name:
        raise ValueError("basename only")
    if not name.endswith(".jsonl"):
        raise ValueError("target must end with .jsonl")


def archive_session(target_basename: str) -> Dict[str, Any]:
    started = time.time()
    _validate_target_basename(target_basename)
    ensure_dirs()

    source = SESSIONS_DIR / target_basename
    if not source.exists():
        raise FileNotFoundError(f"session not found: {target_basename}")
    if not source.is_file():
        raise ValueError("target is not a regular file")
    if source.is_symlink():
        raise ValueError("symlink is forbidden")

    active_name = current_active_candidate_name()
    if active_name == target_basename:
        raise ValueError("refusing to archive current active candidate")

    day_dir = ARCHIVE_ROOT / datetime.now().strftime("%Y%m%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    dest = day_dir / target_basename
    if dest.exists():
        suffix = datetime.now().strftime("%H%M%S")
        dest = day_dir / f"{dest.stem}.{suffix}{dest.suffix}"

    shutil.move(str(source), str(dest))
    ended = time.time()

    result = {
        "ok": True,
        "operation": "session_archive",
        "started_at": _now_iso(),
        "ended_at": _now_iso(),
        "elapsed_ms": int((ended - started) * 1000),
        "exit_code": 0,
        "stdout_preview": f"archived {target_basename} -> {dest}",
        "stderr_preview": "",
        "artifacts": [str(dest)],
    }

    write_audit(
        {
            "ts": _now_iso(),
            "event": "session_archive",
            "target_basename": target_basename,
            "active_candidate_at_execution": active_name,
            "destination": str(dest),
            "ok": True,
            "exit_code": 0,
            "elapsed_ms": result["elapsed_ms"],
        }
    )
    return result


SHELL_METACHAR_RE = re.compile(r'[;&|`$<>()\[\]{}\\\n\r!#*?~^]')
_STDOUT_MAX = 2000
_STDERR_MAX = 500


@dataclass
class ArgSchema:
    name: str
    type: str
    required: bool = True
    allowlist: Optional[List[str]] = None
    default: Any = None


@dataclass
class ActionDef:
    action_id: str
    kind: str
    approval_required: bool
    timeout_sec: int
    args_schema: List[ArgSchema]
    description: str = ""
    cmd_builder: Optional[Callable[[Dict[str, Any]], List[str]]] = None
    callable_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None


_CONFIG_VIEW_SCRIPT = (
    "import json, pathlib\n"
    "p = pathlib.Path.home() / '.openclaw' / 'openclaw.json'\n"
    "d = json.loads(p.read_text())\n"
    "def g(o, *ks):\n"
    "    for k in ks:\n"
    "        if not isinstance(o, dict) or k not in o:\n"
    "            return None\n"
    "        o = o[k]\n"
    "    return o\n"
    "_p = g(d, 'models', 'providers')\n"
    "out = {\n"
    "    'tools.profile': g(d, 'tools', 'profile'),\n"
    "    'agents.defaults.model.primary': g(d, 'agents', 'defaults', 'model', 'primary'),\n"
    "    'agents.defaults.models': g(d, 'agents', 'defaults', 'models'),\n"
    "    'models.provider_names': list(_p.keys()) if isinstance(_p, dict) else None,\n"
    "    'contextPruning': g(d, 'contextPruning'),\n"
    "}\n"
    "print(json.dumps({k: v for k, v in out.items() if v is not None}, indent=2, ensure_ascii=False))\n"
)

_SESSION_SIZES_SCRIPT = (
    "import json, pathlib\n"
    "base = pathlib.Path.home() / '.openclaw' / 'agents' / 'main' / 'sessions'\n"
    "rows = []\n"
    "if base.exists():\n"
    "    for f in sorted(base.glob('*.jsonl')):\n"
    "        rows.append({'session': f.stem, 'bytes': f.stat().st_size})\n"
    "print(json.dumps(rows, indent=2))\n"
)

_ALLOWLISTED_REPO_PATHS = [
    "/home/milky/agent-os",
    "/home/milky/.openclaw/workspace",
]


def _call_archive_session(args: Dict[str, Any]) -> Dict[str, Any]:
    result = archive_session(args["target_basename"])
    result.setdefault("action_id", "session.archive")
    result.setdefault("finished_at", result.get("ended_at", _now_iso()))
    result.setdefault("duration_ms", result.get("elapsed_ms", 0))
    return result


ACTION_REGISTRY: Dict[str, ActionDef] = {
    "service.status_openclaw_gateway": ActionDef(
        action_id="service.status_openclaw_gateway",
        kind="read",
        approval_required=False,
        timeout_sec=10,
        args_schema=[],
        cmd_builder=lambda a: [
            "systemctl",
            "--user",
            "status",
            "openclaw-gateway.service",
            "--no-pager",
        ],
        description="Get status of OpenClaw gateway service",
    ),
    "service.logs_openclaw_gateway_recent": ActionDef(
        action_id="service.logs_openclaw_gateway_recent",
        kind="read",
        approval_required=False,
        timeout_sec=15,
        args_schema=[ArgSchema("lines", "int", required=False, default=50)],
        cmd_builder=lambda a: [
            "journalctl",
            "--user",
            "-u",
            "openclaw-gateway.service",
            "-n",
            str(a.get("lines", 50)),
            "--no-pager",
        ],
        description="Fetch recent log lines from OpenClaw gateway",
    ),
    "service.restart_openclaw_gateway": ActionDef(
        action_id="service.restart_openclaw_gateway",
        kind="mutating",
        approval_required=True,
        timeout_sec=30,
        args_schema=[],
        cmd_builder=lambda a: [
            "systemctl",
            "--user",
            "restart",
            "openclaw-gateway.service",
        ],
        description=(
            "Restart OpenClaw gateway. approval_required=True. "
            "Must not be sole action; pair with status checks."
        ),
    ),
    "config.read_openclaw_json": ActionDef(
        action_id="config.read_openclaw_json",
        kind="read",
        approval_required=False,
        timeout_sec=5,
        args_schema=[],
        cmd_builder=lambda a: ["python3", "-c", _CONFIG_VIEW_SCRIPT],
        description=(
            "Read safe operational fields from openclaw.json. "
            "channels and auth fields excluded by design."
        ),
    ),
    "session.list_jsonl_sizes": ActionDef(
        action_id="session.list_jsonl_sizes",
        kind="read",
        approval_required=False,
        timeout_sec=5,
        args_schema=[],
        cmd_builder=lambda a: ["python3", "-c", _SESSION_SIZES_SCRIPT],
        description="List active session .jsonl sizes (file count + bytes only)",
    ),
    "git.status_repo": ActionDef(
        action_id="git.status_repo",
        kind="read",
        approval_required=False,
        timeout_sec=10,
        args_schema=[
            ArgSchema(
                "repo_path",
                "path_allowlisted",
                required=False,
                allowlist=_ALLOWLISTED_REPO_PATHS,
                default="/home/milky/agent-os",
            ),
        ],
        cmd_builder=lambda a: [
            "git",
            "-C",
            a.get("repo_path", "/home/milky/agent-os"),
            "status",
            "--short",
            "--branch",
        ],
        description="Get git status of an allowlisted repository",
    ),
    "session.archive": ActionDef(
        action_id="session.archive",
        kind="mutating",
        approval_required=True,
        timeout_sec=30,
        args_schema=[ArgSchema("target_basename", "str", required=True)],
        callable_fn=_call_archive_session,
        description="Archive a session using archive_session(). approval_required=True.",
    ),
}


def _validate_args(
    args_schema: List[ArgSchema],
    provided: Dict[str, Any],
) -> Dict[str, Any]:
    schema_names = {s.name for s in args_schema}
    for k in provided:
        if k not in schema_names:
            raise ValueError(f"Unknown argument: {k!r}")

    validated: Dict[str, Any] = {}
    for s in args_schema:
        if s.name in provided:
            val = provided[s.name]
        elif not s.required:
            if s.default is not None:
                validated[s.name] = s.default
            continue
        else:
            raise ValueError(f"Missing required argument: {s.name!r}")

        if s.type == "int":
            try:
                val = int(val)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Arg {s.name!r}: expected int") from exc
            if not (0 <= val <= 10_000):
                raise ValueError(f"Arg {s.name!r}: out of range [0, 10000]")
        elif s.type in ("str", "path_allowlisted"):
            val = str(val)
            if SHELL_METACHAR_RE.search(val):
                raise ValueError(f"Arg {s.name!r}: forbidden shell characters")
            if s.allowlist is not None and val not in s.allowlist:
                raise ValueError(f"Arg {s.name!r}: {val!r} not in allowlist")
        else:
            raise ValueError(f"Unsupported arg type: {s.type!r}")

        validated[s.name] = val

    return validated


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fail(action_id: str, error: str, started_at: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "action_id": action_id,
        "exit_code": -1,
        "error": error,
        "started_at": started_at,
        "finished_at": _now_iso_utc(),
        "duration_ms": 0,
        "stdout_preview": "",
        "stderr_preview": "",
    }


def execute_action(action_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
    t0 = _now_iso_utc()

    if action_id not in ACTION_REGISTRY:
        return _fail(action_id, f"Unknown action_id: {action_id!r}", t0)

    defn = ACTION_REGISTRY[action_id]
    try:
        validated = _validate_args(defn.args_schema, args)
    except ValueError as exc:
        return _fail(action_id, str(exc), t0)

    if defn.callable_fn is not None:
        started = datetime.now(timezone.utc)
        try:
            result = defn.callable_fn(validated)
            finished = datetime.now(timezone.utc)
            result.setdefault("action_id", action_id)
            result.setdefault("started_at", started.isoformat())
            result.setdefault("finished_at", finished.isoformat())
            result.setdefault("duration_ms", int((finished - started).total_seconds() * 1000))
            result.setdefault("stdout_preview", "")
            result.setdefault("stderr_preview", "")
            return result
        except Exception as exc:
            finished = datetime.now(timezone.utc)
            return {
                "ok": False,
                "action_id": action_id,
                "exit_code": -1,
                "error": str(exc),
                "started_at": started.isoformat(),
                "finished_at": finished.isoformat(),
                "duration_ms": int((finished - started).total_seconds() * 1000),
                "stdout_preview": "",
                "stderr_preview": "",
            }

    if defn.cmd_builder is None:
        return _fail(action_id, "Action has neither cmd_builder nor callable_fn", t0)

    cmd = defn.cmd_builder(validated)
    started = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=defn.timeout_sec,
        )
        finished = datetime.now(timezone.utc)
        return {
            "ok": proc.returncode == 0,
            "action_id": action_id,
            "exit_code": proc.returncode,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "duration_ms": int((finished - started).total_seconds() * 1000),
            "stdout_preview": (proc.stdout or "")[:_STDOUT_MAX],
            "stderr_preview": (proc.stderr or "")[:_STDERR_MAX],
        }
    except subprocess.TimeoutExpired:
        finished = datetime.now(timezone.utc)
        return {
            "ok": False,
            "action_id": action_id,
            "exit_code": -1,
            "error": f"Timeout after {defn.timeout_sec}s",
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "duration_ms": int((finished - started).total_seconds() * 1000),
            "stdout_preview": "",
            "stderr_preview": "",
        }
    except Exception as exc:
        finished = datetime.now(timezone.utc)
        return {
            "ok": False,
            "action_id": action_id,
            "exit_code": -1,
            "error": f"Unexpected error: {exc}",
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "duration_ms": int((finished - started).total_seconds() * 1000),
            "stdout_preview": "",
            "stderr_preview": "",
        }


def execute_actions(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for i, item in enumerate(actions):
        r = execute_action(item.get("action_id", ""), item.get("args", {}))
        r["action_index"] = i
        results.append(r)
        if not r["ok"]:
            return {
                "ok": False,
                "results": results,
                "failed_index": i,
                "completed_count": len(results),
            }
    return {
        "ok": True,
        "results": results,
        "failed_index": None,
        "completed_count": len(results),
    }

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from execution.config import (
    AUTO_ARCHIVE_MIN_AGE_SECONDS,
    CRITICAL_BYTES,
    HEALTH_REPORT_PATH,
    HIGH_BYTES,
    MAX_AUTO_ARCHIVES_PER_RUN,
    QUEUED_DIR,
    AWAITING_APPROVAL_DIR,
    SESSIONS_DIR,
    WARN_BYTES,
    ensure_dirs,
)

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

def _safe_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def list_session_files() -> List[Dict[str, Any]]:
    ensure_dirs()
    if not SESSIONS_DIR.exists():
        return []

    rows: List[Dict[str, Any]] = []
    for path in sorted(SESSIONS_DIR.glob("*.jsonl")):
        try:
            if not path.is_file() or path.is_symlink():
                continue
            st = path.stat()
        except OSError:
            continue

        rows.append(
            {
                "name": path.name,
                "path": path,
                "bytes": int(st.st_size),
                "mtime": float(st.st_mtime),
                "age_seconds": max(0, int(time.time() - st.st_mtime)),
            }
        )
    return rows

def choose_active_candidate(entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not entries:
        return None
    return max(entries, key=lambda x: x["mtime"])

def classify_status(largest_bytes: int) -> str:
    if largest_bytes > CRITICAL_BYTES:
        return "critical"
    if largest_bytes > HIGH_BYTES:
        return "high"
    if largest_bytes > WARN_BYTES:
        return "warn"
    return "healthy"

def pending_task_exists(target_basename: str) -> bool:
    for d in [QUEUED_DIR, AWAITING_APPROVAL_DIR]:
        for task_file in d.glob("*.json"):
            try:
                task = json.loads(task_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if (
                task.get("operation") == "session_archive"
                and task.get("args", {}).get("target_basename") == target_basename
            ):
                return True
    return False

def make_task(entry: Dict[str, Any], approval_required: bool, reason: str) -> Dict[str, Any]:
    seed = f"{entry['name']}|{entry['bytes']}|{int(entry['mtime'])}|{approval_required}"
    task_id = "task-session-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    now = _now_iso()

    task = {
        "schema": "agentos.execution_task.v1",
        "task_id": task_id,
        "type": "execution",
        "operation": "session_archive",
        "args": {"target_basename": entry["name"]},
        "status": "queued",
        "risk_level": "medium",
        "approval_required": approval_required,
        "approved": not approval_required,
        "approved_at": None,
        "approved_by": None,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "ended_at": None,
        "result": None,
        "error": None,
        "audit_reason": reason,
        "source": {
            "kind": "session_monitor",
            "health_report": str(HEALTH_REPORT_PATH),
        },
    }

    task_path = QUEUED_DIR / f"{task_id}.json"
    if not task_path.exists() and not pending_task_exists(entry["name"]):
        _safe_write_json(task_path, task)
    return task

def build_health_report() -> Dict[str, Any]:
    entries = list_session_files()
    active = choose_active_candidate(entries)

    largest = max((e["bytes"] for e in entries), default=0)
    total = sum(e["bytes"] for e in entries)
    status = classify_status(largest)
    active_name = active["name"] if active else None
    active_bytes = active["bytes"] if active else 0

    oversized = [
        {"name": e["name"], "bytes": e["bytes"], "age_seconds": e["age_seconds"]}
        for e in entries
        if e["bytes"] > HIGH_BYTES and e["name"] != active_name
    ]

    auto_archive_candidates = [
        item for item in oversized if item["age_seconds"] >= AUTO_ARCHIVE_MIN_AGE_SECONDS
    ][:MAX_AUTO_ARCHIVES_PER_RUN]

    manual_review_candidates = [
        item for item in oversized if item["age_seconds"] < AUTO_ARCHIVE_MIN_AGE_SECONDS
    ]

    rotation_level = "none"
    rotation_reason = None
    rotate_recommended = False

    if active and active_bytes > CRITICAL_BYTES:
        rotation_level = "critical"
        rotation_reason = "active session exceeded CRITICAL_BYTES"
        rotate_recommended = True
    elif active and active_bytes > HIGH_BYTES:
        rotation_level = "high"
        rotation_reason = "active session exceeded HIGH_BYTES"
        rotate_recommended = True
    elif active and active_bytes > WARN_BYTES:
        rotation_level = "warn"
        rotation_reason = "active session exceeded WARN_BYTES"
        rotate_recommended = True

    handoff_prompt = None
    handoff_prompt_path = str(HEALTH_REPORT_PATH.with_name("rotation_handoff_prompt.txt"))
    if rotate_recommended:
        handoff_prompt = (
            "この会話はコンテキスト肥大を避けるため新しいスレッドへ移行する。"
            "以下を前提に継続せよ。\n"
            f"- active_session: {active_name}\n"
            f"- active_bytes: {active_bytes}\n"
            f"- rotation_level: {rotation_level}\n"
            f"- current_health_status: {status}\n"
            "- 直近の目的と次アクションを短く整理して再開すること。"
        )
        HEALTH_REPORT_PATH.with_name("rotation_handoff_prompt.txt").write_text(
            handoff_prompt,
            encoding="utf-8",
        )
    else:
        try:
            HEALTH_REPORT_PATH.with_name("rotation_handoff_prompt.txt").unlink()
        except FileNotFoundError:
            pass

    recommendation = "none"
    if manual_review_candidates:
        recommendation = "approval_required"
    elif auto_archive_candidates:
        recommendation = "archive_pending"
    elif rotate_recommended and rotation_level == "critical":
        recommendation = "rotate_now"
    elif rotate_recommended:
        recommendation = "rotate_soon"

    report: Dict[str, Any] = {
        "schema": "agentos.session_health.v1",
        "generated_at": _now_iso(),
        "status": status,
        "sessions_dir": str(SESSIONS_DIR),
        "file_count": len(entries),
        "total_bytes": total,
        "largest_file": max(entries, key=lambda e: e["bytes"])["name"] if entries else None,
        "largest_bytes": largest,
        "oversized_files": oversized,
        "active_candidate": active_name,
        "active_candidate_bytes": active_bytes,
        "thresholds": {
            "warn_bytes": WARN_BYTES,
            "high_bytes": HIGH_BYTES,
            "critical_bytes": CRITICAL_BYTES,
            "auto_archive_min_age_seconds": AUTO_ARCHIVE_MIN_AGE_SECONDS,
        },
        "recommendation": recommendation,
        "auto_archive_candidates": auto_archive_candidates,
        "manual_review_candidates": manual_review_candidates,
        "rotate_recommended": rotate_recommended,
        "rotation_level": rotation_level,
        "rotation_reason": rotation_reason,
        "handoff_prompt": handoff_prompt,
        "handoff_prompt_path": handoff_prompt_path if rotate_recommended else None,
    }

    _safe_write_json(HEALTH_REPORT_PATH, report)
    return report

def create_tasks_from_report(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries = {e["name"]: e for e in list_session_files()}
    created: List[Dict[str, Any]] = []

    for item in report.get("auto_archive_candidates", []):
        entry = entries.get(item["name"])
        if entry and not pending_task_exists(entry["name"]):
            created.append(
                make_task(
                    entry=entry,
                    approval_required=False,
                    reason=f"auto archive: non-active session exceeds HIGH_BYTES and age_seconds >= {AUTO_ARCHIVE_MIN_AGE_SECONDS}",
                )
            )

    for item in report.get("manual_review_candidates", []):
        entry = entries.get(item["name"])
        if entry and not pending_task_exists(entry["name"]):
            created.append(
                make_task(
                    entry=entry,
                    approval_required=True,
                    reason=f"approval required: non-active session exceeds HIGH_BYTES but age_seconds < {AUTO_ARCHIVE_MIN_AGE_SECONDS}",
                )
            )

    return created

def monitor_once() -> Dict[str, Any]:
    report = build_health_report()
    created = create_tasks_from_report(report)
    report["created_tasks"] = [t["task_id"] for t in created]
    _safe_write_json(HEALTH_REPORT_PATH, report)
    return report

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, Optional

JsonDict = Dict[str, Any]

MAX_QUERY = 200
LIST_LIMIT = 5


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _truncate_query(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if len(value) <= MAX_QUERY:
        return value
    return value[:MAX_QUERY] + "...<truncated>"


def _compact_list(value: Any, *, keep_last: bool = False) -> Any:
    if not isinstance(value, list):
        return value
    if len(value) <= LIST_LIMIT:
        return value
    if keep_last:
        # tests expect len == 5 and last element preserved
        return value[: LIST_LIMIT - 1] + [value[-1]]
    remain = len(value) - LIST_LIMIT
    return value[:LIST_LIMIT] + [f"...<{remain} more>"]


def _safe_task_id(entry: JsonDict) -> str:
    for key in ("task_id", "id", "request_id"):
        if entry.get(key):
            return str(entry[key])
    return "unknown-task"


def _build_auto_heal_summary(entry: JsonDict) -> Optional[JsonDict]:
    auto = entry.get("auto_heal") or entry.get("auto_heal_result") or {}
    if not auto:
        return None
    return {
        "ok": auto.get("ok", True),
        "mode": auto.get("mode"),
        "kind": auto.get("kind"),
        "healed_keys": auto.get("healed_keys", []),
    }


def _build_snapshot_repair_summary(entry: JsonDict) -> Optional[JsonDict]:
    snap = entry.get("snapshot_repair") or {}
    if not snap:
        return None
    return {
        "ok": snap.get("ok", True),
        "repaired": snap.get("repaired", False),
        "selected_kind": snap.get("selected_kind"),
    }


def _build_status(entry: JsonDict) -> str:
    auto = entry.get("auto_heal") or entry.get("auto_heal_result")
    snap = entry.get("snapshot_repair")
    diagnostics = entry.get("diagnostics") or {}

    if auto or snap:
        return "recovered"
    if diagnostics.get("state_anomaly_count", 0) > 0 or diagnostics.get("snapshot_anomaly_count", 0) > 0:
        return "degraded"
    return entry.get("status") or "ok"


def _build_visual_summary(entry: JsonDict) -> JsonDict:
    auto = entry.get("auto_heal") or entry.get("auto_heal_result") or {}
    snap = entry.get("snapshot_repair") or {}
    executed_action = entry.get("executed_action")

    flags = []
    if auto:
        flags.append(f"auto-heal:{auto.get('mode')}")
    if snap:
        flags.append(f"snapshot-repair:{snap.get('selected_kind')}")
    if executed_action:
        flags.append(f"executed:{executed_action}")

    status = _build_status(entry)
    headline = f"{status} | " + ", ".join(flags) if flags else status

    return {
        "status": status,
        "flags": flags,
        "headline": headline,
    }


def _build_compact_summary(entry: JsonDict) -> JsonDict:
    auto = entry.get("auto_heal") or entry.get("auto_heal_result") or {}
    snap = entry.get("snapshot_repair") or {}

    diagnostics = entry.get("diagnostics") or {}
    return {
        "status": _build_status(entry),
        "healed": bool(auto),
        "heal_mode": auto.get("mode") if auto else None,
        "snapshot_repaired": bool(snap),
        "snapshot_repair_kind": snap.get("selected_kind") if snap else None,
        "executed_action": entry.get("executed_action"),
        "state_anomaly_count": diagnostics.get("state_anomaly_count", 0),
        "snapshot_anomaly_count": diagnostics.get("snapshot_anomaly_count", 0),
    }


def build_compact_entry(entry: JsonDict) -> JsonDict:
    e = deepcopy(entry)

    e["query"] = _truncate_query(e.get("query"))

    if "selected_skills" in e:
        e["selected_skills"] = _compact_list(e["selected_skills"])
    if "state_anomalies" in e:
        e["state_anomalies"] = _compact_list(e["state_anomalies"])
    if "snapshot_anomalies" in e:
        e["snapshot_anomalies"] = _compact_list(e["snapshot_anomalies"])
    if "execution_log" in e and isinstance(e["execution_log"], list):
        e["execution_log"] = _compact_list(e["execution_log"], keep_last=True)

    if "deploy_artifact" in e and isinstance(e["deploy_artifact"], dict):
        e["deploy_artifact"] = {
            "json_path": e["deploy_artifact"].get("json_path"),
            "markdown_path": e["deploy_artifact"].get("markdown_path"),
        }

    auto_summary = _build_auto_heal_summary(e)
    if auto_summary:
        e["auto_heal_summary"] = auto_summary

    snap_summary = _build_snapshot_repair_summary(e)
    if snap_summary:
        e["snapshot_repair_summary"] = snap_summary

    e["visual_summary"] = _build_visual_summary(e)
    e["compact_summary"] = _build_compact_summary(e)

    return e


def build_index_record(entry: JsonDict, full_path: Path) -> JsonDict:
    diagnostics = entry.get("diagnostics") or {}
    return {
        "task_id": _safe_task_id(entry),
        "query": _truncate_query(entry.get("query")),
        "status": _build_status(entry),
        "selected_skill": entry.get("selected_skill"),
        "selected_skills": entry.get("selected_skills"),
        "state_anomaly_count": diagnostics.get("state_anomaly_count"),
        "snapshot_anomaly_count": diagnostics.get("snapshot_anomaly_count"),
        "full_path": str(full_path),
    }


def _rewrite_index(index_path: Path, record: JsonDict, max_entries: int = 2000) -> None:
    items = []
    if index_path.exists():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                items = loaded
        except Exception:
            items = []

    task_id = record.get("task_id")
    items = [x for x in items if x.get("task_id") != task_id]
    items.append(record)
    items = items[-max_entries:]

    _ensure_parent(index_path)
    index_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def write_audit_bundle(
    *,
    entry: JsonDict,
    history_path: Path,
    full_dir: Path,
    index_path: Path,
    rotate_func: Optional[Callable[..., Any]] = None,
    max_bytes: Optional[int] = None,
    backup_count: Optional[int] = None,
) -> JsonDict:
    compact = build_compact_entry(entry)
    task_id = _safe_task_id(entry)

    full_dir.mkdir(parents=True, exist_ok=True)
    full_path = full_dir / f"{task_id}.json"
    full_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")

    rotation = None
    if rotate_func is not None:
        _ensure_parent(history_path)
        rotation = rotate_func(
            history_path,
            max_bytes=max_bytes,
            backup_count=backup_count,
        )

    if rotation:
        compact["audit_rotation"] = rotation

    _ensure_parent(history_path)
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(compact, ensure_ascii=False) + "\n")

    index_record = build_index_record(entry, full_path)
    _rewrite_index(index_path, index_record)

    return {
        "ok": True,
        "history_path": str(history_path),
        "full_path": str(full_path),
        "index_path": str(index_path),
        "rotation": rotation,
    }


def append_audit_log(entry: JsonDict, base_dir: str | Path) -> str:
    base = Path(base_dir)
    history_path = base / "state" / "execution_history.jsonl"
    full_dir = base / "state" / "execution_full"
    index_path = base / "state" / "execution_index.json"

    write_audit_bundle(
        entry=entry,
        history_path=history_path,
        full_dir=full_dir,
        index_path=index_path,
        rotate_func=None,
        max_bytes=None,
        backup_count=None,
    )
    return str(history_path)

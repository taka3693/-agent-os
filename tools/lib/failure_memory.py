from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import json


def _resolve_base_dir(base_dir):
    if base_dir:
        return Path(base_dir)

    import tools.run_agent_os_request as mod
    return Path(mod.__file__).resolve().parents[1]


def _episode_store_path(base_dir=None) -> Path:
    root = _resolve_base_dir(base_dir)
    p = root / "state" / "learning_memory" / "failure_episodes.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def build_failure_episodes(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(result, dict):
        return []

    failure_control = result.get("failure_control", {})
    if not isinstance(failure_control, dict):
        return []

    failures = failure_control.get("failures", [])
    if not isinstance(failures, list):
        failures = []

    heal_actions = failure_control.get("heal_actions", [])
    if not isinstance(heal_actions, list):
        heal_actions = []

    actions_by_type = {}
    for action in heal_actions:
        if isinstance(action, dict):
            ftype = action.get("failure_type")
            if ftype:
                actions_by_type[str(ftype)] = dict(action)

    episodes = []
    for failure in failures:
        if not isinstance(failure, dict):
            continue

        ftype = str(failure.get("type") or "")
        action = actions_by_type.get(ftype, {})

        episode = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "failure_type": ftype,
            "severity": failure.get("severity"),
            "recoverable": bool(failure.get("recoverable", False)),
            "confidence": float(failure.get("confidence", 0.0)),
            "risk": failure.get("risk"),
            "anomalies": list(failure.get("anomalies", [])),
            "chosen_strategy": failure.get("strategy"),
            "decision": action.get("decision"),
            "reason": action.get("reason"),
            "healed_keys": list(result.get("healed_keys", [])),
            "outcome": {
                "snapshot_repair_attempted": bool(result.get("snapshot_repair_attempted", False)),
                "snapshot_repaired": bool(result.get("snapshot_repaired", False)),
                "auto_heal_attempted": bool(result.get("auto_heal_attempted", False)),
                "auto_heal_applied": bool(result.get("auto_heal_applied", False)),
            },
        }
        episodes.append(episode)

    return episodes


def append_failure_episodes(result: Dict[str, Any], *, base_dir=None) -> Dict[str, Any]:
    episodes = build_failure_episodes(result)
    path = _episode_store_path(base_dir=base_dir)

    with path.open("a", encoding="utf-8") as f:
        for episode in episodes:
            f.write(json.dumps(episode, ensure_ascii=False) + "\n")

    return {
        "ok": True,
        "path": str(path),
        "count": len(episodes),
    }

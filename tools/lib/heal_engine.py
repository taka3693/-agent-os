from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json

from tools.lib.rollback_store import inspect_latest_snapshot


def _resolve_base_dir(base_dir):
    if base_dir:
        return Path(base_dir)

    import tools.run_agent_os_request as mod
    return Path(mod.__file__).resolve().parents[1]


def _detect_state_anomalies(result):
    anomalies = []

    if not isinstance(result, dict):
        anomalies.append("invalid_result_type")
        return anomalies

    if result.get("next_action") == "deploy" and not result.get("executed_action"):
        anomalies.append("deploy_not_executed")

    if result.get("executed_action") == "deploy" and not result.get("deploy_artifact"):
        anomalies.append("missing_deploy_artifact")

    return anomalies


def _detect_snapshot_anomalies(base_dir=None):
    base_dir = _resolve_base_dir(base_dir)

    latest_path = Path(base_dir) / "state" / "rollback" / "rollback.latest.json"

    if not latest_path.exists():
        return ["snapshot_unavailable"]

    try:
        snap = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception:
        return ["snapshot_unavailable"]

    if not snap.get("deploy_artifact"):
        return ["snapshot_missing_deploy_artifact"]

    return []


def _auto_heal_result(result, base_dir=None):
    base_dir = _resolve_base_dir(base_dir)
    result = dict(result)

    latest_path = Path(base_dir) / "state" / "rollback" / "rollback.latest.json"

    snap = None
    if latest_path.exists():
        try:
            snap = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception:
            snap = None

    if result.get("next_action") == "deploy" and not result.get("executed_action"):
        if snap and snap.get("deploy_artifact"):
            result["deploy_artifact"] = snap["deploy_artifact"]
            result["executed_action"] = "deploy"
            result["rollback_info"] = {
                "restored_from": "latest",
                "snapshot_kind": "latest"
            }
            result["auto_heal"] = {
                "ok": True,
                "mode": "partial",
                "healed_keys": ["deploy_artifact", "executed_action", "rollback_info"]
            }
            return result

    result["auto_heal"] = {"ok": False}
    return result


def _repair_snapshot_if_needed(result, base_dir=None):
    base_dir = _resolve_base_dir(base_dir)
    result = dict(result)

    rollback_dir = Path(base_dir) / "state" / "rollback"
    latest_path = rollback_dir / "rollback.latest.json"

    snap = None
    if latest_path.exists():
        try:
            snap = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception:
            snap = None

    if snap and not snap.get("deploy_artifact"):
        files = sorted(rollback_dir.glob("rollback.*.json"), reverse=True)

        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("deploy_artifact"):
                    latest_path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )

                    result["snapshot_repair"] = {
                        "ok": True,
                        "mode": "versioned",
                        "repaired": True,
                        "selected_kind": "versioned",
                        "attempted": True,
                    }

                    result.setdefault("diagnostics", {})
                    result["diagnostics"]["snapshot_repair_attempted"] = True
                    result["diagnostics"]["snapshot_repaired"] = True

                    return result
            except Exception:
                continue

    result["snapshot_repair"] = {
        "ok": False,
        "attempted": True,
    }

    result.setdefault("diagnostics", {})
    result["diagnostics"]["snapshot_repair_attempted"] = True
    result["diagnostics"]["snapshot_repaired"] = False

    return result


def _normalize_execution_state(result, base_dir=None):
    result = _repair_snapshot_if_needed(result, base_dir=base_dir)
    result = _auto_heal_result(result, base_dir=base_dir)

    result.setdefault("diagnostics", {})
    result["diagnostics"]["snapshot_repair_attempted"] = result.get("snapshot_repair", {}).get("attempted", False)

    return result

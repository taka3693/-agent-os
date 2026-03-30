from typing import Dict, List, Optional
from tools.lib.failure_policy import build_failure_control_output

def run_phase2_failure_control(
    result: Dict,
    *,
    base_dir: Optional[str] = None,
    state_anomalies: Optional[List[str]] = None,
    snapshot_anomalies: Optional[List[str]] = None,
    repair_snapshot_fn=None,
    auto_heal_fn=None,
    retry_or_skip_fn=None,
    policy=None,
):
    if not isinstance(result, dict):
        result = {}

    merged_anomalies = []
    if isinstance(state_anomalies, list):
        merged_anomalies.extend([str(x) for x in state_anomalies if x is not None])
    if isinstance(snapshot_anomalies, list):
        merged_anomalies.extend([str(x) for x in snapshot_anomalies if x is not None])

    phase2 = build_failure_control_output(
        result=result,
        anomalies=merged_anomalies,
        base_dir=base_dir,
        policy=policy,
        repair_snapshot_fn=repair_snapshot_fn,
        auto_heal_fn=auto_heal_fn,
        retry_or_skip_fn=retry_or_skip_fn,
    )

    working = dict(phase2.get("result", result))
    failure_control = phase2.get("failure_control", {})

    working["failure_control"] = failure_control
    working["failures"] = failure_control.get("failures", [])
    working["failure_count"] = failure_control.get("failure_count", 0)

    snapshot_repair = failure_control.get("snapshot_repair", {})
    auto_heal = failure_control.get("auto_heal", {})

    working["snapshot_repair_attempted"] = bool(snapshot_repair.get("attempted", False))
    working["snapshot_repaired"] = bool(snapshot_repair.get("repaired", False))
    working["auto_heal_attempted"] = bool(auto_heal.get("attempted", False))
    working["auto_heal_applied"] = bool(auto_heal.get("healed", False))
    working["healed_keys"] = auto_heal.get("healed_keys", [])

    return working

from tools.lib.policy_overrides import load_policy_overrides
from tools.lib.failure_insights import load_failure_insights
from datetime import datetime, timezone
from typing import List, Dict, Any



def _insight_adjusted_strategy(
    failure: Dict[str, Any],
    *,
    base_dir=None,
    default_strategy: str,
) -> str:
    insights = load_failure_insights(base_dir=base_dir)
    if not isinstance(insights, dict):
        return default_strategy

    ftype = str(failure.get("type") or "")
    risk = str(failure.get("risk") or "mid")
    has_recoverable = "recoverable" in failure
    recoverable = bool(failure.get("recoverable", False))

    risk_summary = insights.get("risk_summary", {})
    if not isinstance(risk_summary, dict):
        risk_summary = {}

    type_risks = risk_summary.get(ftype, {})
    if not isinstance(type_risks, dict):
        type_risks = {}

    high_risk_seen = int(type_risks.get("high", 0))
    low_risk_seen = int(type_risks.get("low", 0))

    # 後方互換:
    # recoverable 未指定の古い failure には insight 補正で方針を変えない
    if ftype == "state_failure" and has_recoverable and not recoverable:
        return "retry_or_skip"

    if ftype == "execution_failure" and risk == "high" and high_risk_seen >= 3:
        return "retry_or_skip"

    if ftype == "rate_limit_failure" and low_risk_seen >= 3:
        return "retry_or_skip"

    return default_strategy


DEFAULT_HEAL_POLICY = {
    "snapshot_failure": "repair_snapshot",
    "state_failure": "auto_heal",
    "execution_failure": "retry_or_skip",
    "rate_limit_failure": "retry_or_skip",
}

ANOMALY_RULES = {
    "snapshot_unavailable": {
        "type": "snapshot_failure",
        "severity": "high",
        "recoverable": True,
    },
    "latest_snapshot_corrupt": {
        "type": "snapshot_failure",
        "severity": "high",
        "recoverable": True,
    },
    "latest_snapshot_invalid": {
        "type": "snapshot_failure",
        "severity": "high",
        "recoverable": True,
    },
    "snapshot_invalid": {
        "type": "snapshot_failure",
        "severity": "high",
        "recoverable": True,
    },
    "snapshot_missing": {
        "type": "snapshot_failure",
        "severity": "high",
        "recoverable": True,
    },
    "rollback_snapshot_missing": {
        "type": "snapshot_failure",
        "severity": "high",
        "recoverable": True,
    },
    "deploy_not_executed": {
        "type": "state_failure",
        "severity": "high",
        "recoverable": True,
    },
    "missing_deploy_artifact": {
        "type": "state_failure",
        "severity": "high",
        "recoverable": True,
    },
    "missing_executed_action": {
        "type": "state_failure",
        "severity": "mid",
        "recoverable": True,
    },
    "missing_rollback_info": {
        "type": "state_failure",
        "severity": "mid",
        "recoverable": True,
    },
    "invalid_result_type": {
        "type": "state_failure",
        "severity": "mid",
        "recoverable": True,
    },
    "execution_failed": {
        "type": "execution_failure",
        "severity": "mid",
        "recoverable": True,
    },
    "command_failed": {
        "type": "execution_failure",
        "severity": "mid",
        "recoverable": True,
    },
    "process_exit_nonzero": {
        "type": "execution_failure",
        "severity": "high",
        "recoverable": True,
    },
    "timeout": {
        "type": "execution_failure",
        "severity": "mid",
        "recoverable": True,
    },
    "exception": {
        "type": "execution_failure",
        "severity": "mid",
        "recoverable": True,
    },
    "retry_exhausted": {
        "type": "execution_failure",
        "severity": "high",
        "recoverable": False,
    },
    "rate_limit": {
        "type": "rate_limit_failure",
        "severity": "mid",
        "recoverable": True,
    },
    "429": {
        "type": "rate_limit_failure",
        "severity": "mid",
        "recoverable": True,
    },
    "quota_exceeded": {
        "type": "rate_limit_failure",
        "severity": "mid",
        "recoverable": True,
    },
    "too_many_requests": {
        "type": "rate_limit_failure",
        "severity": "mid",
        "recoverable": True,
    },
}

SEVERITY_SCORE = {"low": 1, "mid": 2, "high": 3}

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


FAILURE_TYPE_PRIORITY = {
    "snapshot_failure": 1,
    "state_failure": 2,
    "execution_failure": 3,
    "rate_limit_failure": 4,
}


def _classify_anomaly(anomaly: str) -> Dict[str, Any]:
    key = str(anomaly or "").strip().lower()
    rule = ANOMALY_RULES.get(key)
    if rule is not None:
        return dict(rule)
    return {
        "type": "execution_failure",
        "severity": "mid",
        "recoverable": True,
    }


def _default_confidence_for(rule_found: bool, severity: str) -> float:
    if rule_found:
        if severity == "high":
            return 0.95
        if severity == "mid":
            return 0.90
        return 0.85
    return 0.60


def _default_risk_for(ftype: str, severity: str, recoverable: bool) -> str:
    if ftype == "snapshot_failure":
        return "high"
    if severity == "high" and not recoverable:
        return "high"
    if severity == "high":
        return "mid"
    if ftype == "rate_limit_failure":
        return "low"
    return "mid"


def _classify_with_assessment(anomaly: str) -> Dict[str, Any]:
    key = str(anomaly or "").strip().lower()
    rule = ANOMALY_RULES.get(key)
    base = _classify_anomaly(anomaly)

    out = dict(base)
    out["confidence"] = _default_confidence_for(rule is not None, out["severity"])
    out["risk"] = _default_risk_for(
        out["type"],
        out["severity"],
        bool(out["recoverable"]),
    )
    return out


def detect_failures_from_anomalies(anomalies: List[str]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}

    for anomaly in anomalies or []:
        classified = _classify_with_assessment(str(anomaly))
        ftype = classified["type"]

        if ftype not in grouped:
            grouped[ftype] = {
                "type": ftype,
                "severity": classified["severity"],
                "recoverable": bool(classified["recoverable"]),
                "confidence": float(classified["confidence"]),
                "risk": classified["risk"],
                "anomalies": [anomaly],
                "strategy": None,
            }
            continue

        current = grouped[ftype]
        if SEVERITY_SCORE[classified["severity"]] > SEVERITY_SCORE[current["severity"]]:
            current["severity"] = classified["severity"]
        current["recoverable"] = bool(current["recoverable"] and classified["recoverable"])
        current["confidence"] = max(float(current["confidence"]), float(classified["confidence"]))

        risk_rank = {"low": 1, "mid": 2, "high": 3}
        if risk_rank.get(classified["risk"], 0) > risk_rank.get(current["risk"], 0):
            current["risk"] = classified["risk"]

        current["anomalies"].append(anomaly)

    failures = list(grouped.values())
    failures.sort(
        key=lambda x: (
            FAILURE_TYPE_PRIORITY.get(x.get("type"), 999),
            -SEVERITY_SCORE.get(x.get("severity", "low"), 0),
        )
    )
    return failures


def resolve_heal_strategy(failure: Dict[str, Any], policy=None, *, base_dir=None) -> str:
    if policy is not None and not isinstance(policy, dict):
        raise TypeError("policy must be dict or None")

    if isinstance(policy, dict):
        forced = policy.get(failure.get("type"))
        if forced:
            return forced

    overrides_doc = load_policy_overrides(base_dir=base_dir)
    if isinstance(overrides_doc, dict):
        overrides = overrides_doc.get("overrides", {})
        if isinstance(overrides, dict):
            forced = overrides.get(failure.get("type"))
            if forced:
                return str(forced)

    ftype = str(failure.get("type") or "")
    has_recoverable = "recoverable" in failure
    has_confidence = "confidence" in failure
    has_risk = "risk" in failure

    # 後方互換:
    # failure情報が未成熟な既存呼び出しは type既定戦略を優先する
    if not has_recoverable and not has_confidence and not has_risk:
        default_strategy = DEFAULT_HEAL_POLICY.get(ftype, "retry_or_skip")
        return _insight_adjusted_strategy(
            failure,
            base_dir=base_dir,
            default_strategy=default_strategy,
        )

    severity = str(failure.get("severity") or "low")
    recoverable = bool(failure.get("recoverable", False))
    confidence = float(failure.get("confidence", 0.0))
    risk = str(failure.get("risk") or "mid")

    if ftype == "snapshot_failure":
        return _insight_adjusted_strategy(
            failure,
            base_dir=base_dir,
            default_strategy="repair_snapshot",
        )

    if ftype == "state_failure":
        default_strategy = "auto_heal" if recoverable else "retry_or_skip"
        return _insight_adjusted_strategy(
            failure,
            base_dir=base_dir,
            default_strategy=default_strategy,
        )

    if ftype == "rate_limit_failure":
        return _insight_adjusted_strategy(
            failure,
            base_dir=base_dir,
            default_strategy="retry_or_skip",
        )

    if ftype == "execution_failure":
        if recoverable and confidence >= 0.8 and risk != "high":
            default_strategy = "retry_or_skip"
        else:
            default_strategy = "retry_or_skip"
        return _insight_adjusted_strategy(
            failure,
            base_dir=base_dir,
            default_strategy=default_strategy,
        )

    return _insight_adjusted_strategy(
        failure,
        base_dir=base_dir,
        default_strategy=DEFAULT_HEAL_POLICY.get(ftype, "retry_or_skip"),
    )


def apply_heal_policy(failures, policy=None, *, base_dir=None):
    out = []
    for failure in failures or []:
        item = dict(failure)
        item["strategy"] = resolve_heal_strategy(item, policy=policy, base_dir=base_dir)
        out.append(item)
    return out


def build_failure_control_output(**kwargs):
    result = kwargs.get("result", {})
    anomalies = kwargs.get("anomalies", [])
    policy = kwargs.get("policy")
    base_dir = kwargs.get("base_dir")
    repair_snapshot_fn = kwargs.get("repair_snapshot_fn")
    auto_heal_fn = kwargs.get("auto_heal_fn")
    retry_or_skip_fn = kwargs.get("retry_or_skip_fn")

    failures = detect_failures_from_anomalies(anomalies)
    failures = apply_heal_policy(failures, policy=policy, base_dir=base_dir)

    failure_control = {
        "anomalies": list(anomalies or []),
        "failures": failures,
        "failure_count": len(failures),
        "policy": policy or DEFAULT_HEAL_POLICY,
        "heal_actions": [],
        "snapshot_repair": {
            "attempted": False,
            "repaired": False,
            "selected_kind": None,
        },
        "auto_heal": {
            "attempted": False,
            "healed": False,
            "healed_keys": [],
        },
    }

    working = result if isinstance(result, dict) else {}

    for failure in failures:
        strategy = failure.get("strategy")

        if strategy == "repair_snapshot" and callable(repair_snapshot_fn):
            started_at = _now_iso()
            repair_res = repair_snapshot_fn(base_dir=base_dir)
            finished_at = _now_iso()
            if not isinstance(repair_res, dict):
                repair_res = {}
            failure_control["snapshot_repair"]["attempted"] = bool(repair_res.get("attempted", True))
            failure_control["snapshot_repair"]["repaired"] = bool(repair_res.get("repaired", False))
            failure_control["snapshot_repair"]["selected_kind"] = repair_res.get("selected_kind")
            failure_control["heal_actions"].append({
                "failure_type": failure.get("type"),
                "strategy": strategy,
                "ok": True,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": 0,
            })

        elif strategy == "auto_heal" and callable(auto_heal_fn):
            started_at = _now_iso()
            healed_res = auto_heal_fn(working, base_dir=base_dir)
            finished_at = _now_iso()
            if not isinstance(healed_res, dict):
                healed_res = {}
            working = healed_res.get("result", working)
            healed_keys = healed_res.get("healed_keys", [])
            if not isinstance(healed_keys, list):
                healed_keys = []
            failure_control["auto_heal"]["attempted"] = True
            failure_control["auto_heal"]["healed"] = bool(healed_keys)
            failure_control["auto_heal"]["healed_keys"] = healed_keys
            failure_control["heal_actions"].append({
                "failure_type": failure.get("type"),
                "strategy": strategy,
                "ok": True,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": 0,
            })

        elif strategy == "retry_or_skip":
            retry_res = {}
            if callable(retry_or_skip_fn):
                retry_res = retry_or_skip_fn(
                    working,
                    failure=failure,
                    base_dir=base_dir,
                )
                if not isinstance(retry_res, dict):
                    retry_res = {}
            else:
                retry_res = {
                    "attempted": True,
                    "decision": "skip",
                    "reason": "retry_or_skip_not_implemented",
                }

            started_at = _now_iso()
            finished_at = _now_iso()
            failure_control["heal_actions"].append({
                "failure_type": failure.get("type"),
                "strategy": strategy,
                "ok": True,
                "decision": retry_res.get("decision"),
                "reason": retry_res.get("reason"),
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": 0,
            })

        elif strategy == "manual_review":
            started_at = _now_iso()
            finished_at = _now_iso()
            failure_control["heal_actions"].append({
                "failure_type": failure.get("type"),
                "strategy": strategy,
                "ok": True,
                "decision": "manual_review",
                "reason": "requires_human_review",
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": 0,
            })

        elif strategy == "backoff_retry":
            started_at = _now_iso()
            finished_at = _now_iso()
            failure_control["heal_actions"].append({
                "failure_type": failure.get("type"),
                "strategy": strategy,
                "ok": True,
                "decision": "backoff_retry",
                "reason": "policy_override_backoff_retry",
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": 0,
            })

    return {
        "result": working,
        "failure_control": failure_control,
    }

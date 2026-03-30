from __future__ import annotations

from collections import Counter, defaultdict
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
    return root / "state" / "learning_memory" / "failure_episodes.jsonl"


def _insight_store_path(base_dir=None) -> Path:
    root = _resolve_base_dir(base_dir)
    p = root / "state" / "learning_memory" / "failure_insights.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_failure_episodes(*, base_dir=None) -> List[Dict[str, Any]]:
    path = _episode_store_path(base_dir=base_dir)
    if not path.exists():
        return []

    episodes: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            episodes.append(item)
    return episodes


def load_failure_insights(*, base_dir=None) -> Dict[str, Any]:
    path = _insight_store_path(base_dir=base_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def build_failure_insights(*, base_dir=None) -> Dict[str, Any]:
    episodes = load_failure_episodes(base_dir=base_dir)

    by_type = Counter()
    by_strategy = Counter()
    retry_reasons = Counter()
    heal_key_counter = Counter()
    outcome_counter = Counter()
    risk_by_type = defaultdict(Counter)

    for ep in episodes:
        ftype = str(ep.get("failure_type") or "unknown")
        strategy = str(ep.get("chosen_strategy") or "unknown")
        by_type[ftype] += 1
        by_strategy[strategy] += 1

        reason = ep.get("reason")
        if reason:
            retry_reasons[str(reason)] += 1

        for key in ep.get("healed_keys", []) or []:
            heal_key_counter[str(key)] += 1

        outcome = ep.get("outcome", {}) or {}
        if outcome.get("snapshot_repaired"):
            outcome_counter["snapshot_repaired"] += 1
        if outcome.get("auto_heal_applied"):
            outcome_counter["auto_heal_applied"] += 1

        risk = str(ep.get("risk") or "unknown")
        risk_by_type[ftype][risk] += 1

    top_failure_types = [
        {"failure_type": k, "count": v}
        for k, v in by_type.most_common(10)
    ]
    top_strategies = [
        {"strategy": k, "count": v}
        for k, v in by_strategy.most_common(10)
    ]
    top_retry_reasons = [
        {"reason": k, "count": v}
        for k, v in retry_reasons.most_common(10)
    ]
    top_healed_keys = [
        {"key": k, "count": v}
        for k, v in heal_key_counter.most_common(10)
    ]

    risk_summary = {}
    for ftype, counter in risk_by_type.items():
        risk_summary[ftype] = dict(counter)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "episode_count": len(episodes),
        "top_failure_types": top_failure_types,
        "top_strategies": top_strategies,
        "top_retry_reasons": top_retry_reasons,
        "top_healed_keys": top_healed_keys,
        "outcomes": dict(outcome_counter),
        "risk_summary": risk_summary,
    }


def write_failure_insights(*, base_dir=None) -> Dict[str, Any]:
    insights = build_failure_insights(base_dir=base_dir)
    path = _insight_store_path(base_dir=base_dir)
    path.write_text(json.dumps(insights, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "episode_count": insights.get("episode_count", 0),
    }

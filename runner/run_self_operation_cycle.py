from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from ops.action_queue import build_action_queue
from ops.approval_queue import append_approval_queue_entry
from ops.cooldown_filter import filter_actions_by_cooldown
from ops.health_evaluator import evaluate_health_snapshot
from ops.health_snapshot import build_health_snapshot, utc_now_iso
from ops.health_store import append_health_history, write_latest_health
from ops.hygiene_recommendations import build_hygiene_recommended_actions
from ops.policy import decide_recommended_action
from ops.session_hygiene import select_archive_candidates


def _apply_cooldown_if_possible(
    *,
    state_root: Optional[Path],
    actions,
    now_iso: str,
    cooldown_seconds: int,
):
    if state_root is None:
        return list(actions)

    return filter_actions_by_cooldown(
        state_root=state_root,
        actions=actions,
        now_iso=now_iso,
        cooldown_seconds=cooldown_seconds,
    )


def run_self_operation_cycle(
    *,
    tasks_root: Path,
    state_root: Optional[Path] = None,
    session_sizes: Optional[Iterable[Dict[str, Any]]] = None,
    active_session_basenames: Optional[Iterable[str]] = None,
    gateway_status: Optional[Dict[str, Any]] = None,
    recent_log_summary: Optional[Dict[str, Any]] = None,
    session_warn_bytes: int = 5_000_000,
    failed_task_warn_count: int = 3,
    awaiting_approval_warn_count: int = 3,
    approval_cooldown_seconds: int = 1800,
    now_iso: Optional[str] = None,
) -> Dict[str, Any]:
    current_now_iso = now_iso or utc_now_iso()

    snapshot = build_health_snapshot(
        tasks_root=tasks_root,
        session_sizes=session_sizes,
        gateway_status=gateway_status,
        recent_log_summary=recent_log_summary,
    )

    evaluation = evaluate_health_snapshot(
        snapshot,
        session_warn_bytes=session_warn_bytes,
        failed_task_warn_count=failed_task_warn_count,
        awaiting_approval_warn_count=awaiting_approval_warn_count,
    )

    raw_eval_actions = [
        decide_recommended_action(x)
        for x in evaluation.get("recommended_actions", [])
    ]
    eval_actions = _apply_cooldown_if_possible(
        state_root=state_root,
        actions=raw_eval_actions,
        now_iso=current_now_iso,
        cooldown_seconds=approval_cooldown_seconds,
    )

    archive_candidates = select_archive_candidates(
        session_sizes,
        warn_bytes=session_warn_bytes,
        active_basenames=active_session_basenames,
    )

    raw_hygiene_actions = [
        decide_recommended_action(x)
        for x in build_hygiene_recommended_actions(archive_candidates)
    ]
    hygiene_actions = _apply_cooldown_if_possible(
        state_root=state_root,
        actions=raw_hygiene_actions,
        now_iso=current_now_iso,
        cooldown_seconds=approval_cooldown_seconds,
    )

    result = {
        "snapshot": snapshot,
        "evaluation": {
            **evaluation,
            "recommended_actions": eval_actions,
        },
        "session_hygiene": {
            "archive_candidates": archive_candidates,
            "recommended_actions": hygiene_actions,
        },
        "queues": {
            "evaluation": build_action_queue(eval_actions),
            "session_hygiene": build_action_queue(hygiene_actions),
        },
    }

    if state_root is not None:
        seen_approval_fingerprints = set()
        for queue_name in ("evaluation", "session_hygiene"):
            for item in result["queues"][queue_name].get("approval_required", []):
                fingerprint = item["fingerprint"]
                if fingerprint in seen_approval_fingerprints:
                    continue
                seen_approval_fingerprints.add(fingerprint)
                append_approval_queue_entry(
                    state_root,
                    timestamp=current_now_iso,
                    fingerprint=fingerprint,
                    action=item["action"],
                    args=item.get("args", {}),
                    policy=item["policy"],
                    reason=item["reason"],
                    source=queue_name,
                )
        latest_path = write_latest_health(state_root, result)
        history_path = append_health_history(state_root, result)
        result["storage"] = {
            "latest_path": str(latest_path),
            "history_path": str(history_path),
        }

    return result

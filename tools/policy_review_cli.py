from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lib.policy_review_queue import (
    list_pending_policy_suggestions,
    mark_policy_suggestion_status,
)
from tools.lib.policy_overrides import write_policy_overrides, load_policy_overrides
from tools.lib.policy_review_audit import load_latest_policy_review_audit
from tools.lib.failure_insights import build_failure_insights
from tools.lib.policy_review_audit import append_policy_review_audit


def cmd_list(args):
    rows = list_pending_policy_suggestions(base_dir=args.base_dir)
    out = {
        "ok": True,
        "count": len(rows),
        "items": [],
    }

    for i, row in enumerate(rows):
        out["items"].append({
            "index": i,
            "failure_type": row.get("failure_type"),
            "suggested_action": row.get("suggested_action"),
            "reason": row.get("reason"),
            "evidence": row.get("evidence", {}),
            "status": row.get("status"),
            "ts": row.get("ts"),
        })

    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_review(args):
    res = mark_policy_suggestion_status(
        index=args.index,
        status=args.status,
        reviewer_note=args.note,
        base_dir=args.base_dir,
    )

    audit = append_policy_review_audit(
        action="review",
        updated=res.get("updated", {}),
        reviewer=args.reviewer,
        base_dir=args.base_dir,
    )

    overrides = write_policy_overrides(base_dir=args.base_dir)

    out = {
        "ok": True,
        "review": res,
        "audit": audit,
        "policy_overrides": overrides,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _build_status_payload(args):
    pending = list_pending_policy_suggestions(base_dir=args.base_dir)
    overrides_doc = load_policy_overrides(base_dir=args.base_dir)
    latest_audit = load_latest_policy_review_audit(base_dir=args.base_dir)
    insights = build_failure_insights(base_dir=args.base_dir)

    if not isinstance(pending, list):
        pending = []
    if not isinstance(overrides_doc, dict):
        overrides_doc = {}
    if not isinstance(latest_audit, dict):
        latest_audit = {}
    if not isinstance(insights, dict):
        insights = {}

    override_map = overrides_doc.get("overrides", {})
    if not isinstance(override_map, dict):
        override_map = {}

    return {
        "ok": True,
        "pending_policy_suggestion_count": len(pending),
        "active_policy_override_count": len(override_map),
        "active_policy_override_types": sorted(str(k) for k in override_map.keys()),
        "latest_policy_review_audit": latest_audit,
        "insight_summary": {
            "episode_count": insights.get("episode_count", 0),
            "top_failure_types": insights.get("top_failure_types", [])[:3],
            "top_strategies": insights.get("top_strategies", [])[:3],
        },
        "learning_control_preview": {
            "pending_suggestions": len(pending),
            "active_overrides": len(override_map),
            "last_review_status": latest_audit.get("status"),
            "last_review_failure_type": latest_audit.get("failure_type"),
        },
    }


def _status_text(payload):
    latest = payload.get("latest_policy_review_audit", {})
    if not isinstance(latest, dict):
        latest = {}

    last_review = "none"
    if latest:
        last_review = (
            f"{latest.get('status', 'unknown')}:"
            f"{latest.get('failure_type', 'unknown')}"
        )

    top_failure_types = payload.get("insight_summary", {}).get("top_failure_types", [])
    if not isinstance(top_failure_types, list):
        top_failure_types = []

    top_failure_text = "none"
    if top_failure_types:
        parts = []
        for item in top_failure_types[:3]:
            if isinstance(item, dict):
                parts.append(f"{item.get('failure_type', 'unknown')}={item.get('count', 0)}")
        if parts:
            top_failure_text = ", ".join(parts)

    override_types = payload.get("active_policy_override_types", [])
    if not isinstance(override_types, list):
        override_types = []

    override_text = ", ".join(str(x) for x in override_types) if override_types else "none"

    lines = [
        "policy-review status",
        f"pending_suggestions: {payload.get('pending_policy_suggestion_count', 0)}",
        f"active_overrides: {payload.get('active_policy_override_count', 0)}",
        f"override_types: {override_text}",
        f"last_review: {last_review}",
        f"episode_count: {payload.get('insight_summary', {}).get('episode_count', 0)}",
        f"top_failure_types: {top_failure_text}",
    ]
    return "\n".join(lines)


def cmd_status(args):
    out = _build_status_payload(args)
    if getattr(args, "text", False):
        print(_status_text(out))
        return
    print(json.dumps(out, ensure_ascii=False, indent=2))


def build_parser():
    p = argparse.ArgumentParser(prog="policy_review_cli")
    p.add_argument("--base-dir", default=None)

    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.set_defaults(func=cmd_list)

    p_review = sub.add_parser("review")
    p_review.add_argument("--index", type=int, required=True)
    p_review.add_argument("--status", choices=["approved", "rejected"], required=True)
    p_review.add_argument("--note", default=None)
    p_review.add_argument("--reviewer", default="unknown")
    p_review.set_defaults(func=cmd_review)

    p_status = sub.add_parser("status")
    p_status.add_argument("--text", action="store_true")
    p_status.set_defaults(func=cmd_status)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

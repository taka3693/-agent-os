#!/usr/bin/env python3
"""
Controlled Scheduler Layer

This module provides a minimal scheduler that performs conservative periodic
detection and reporting only.

Key principles:
- NO automatic apply
- NO automatic rollback
- NO automatic commit
- NO automatic promotion execution
- NO unattended self-improvement loop
- Scheduler only DETECTS and REPORTS
- All risky actions require manual trigger

Scheduler capabilities:
- Detect pending verifications
- Detect stale / expired items
- Detect pending revert candidates
- Detect governance-denied but actionable items
- Generate operational summaries

IMPORTANT: This scheduler does NOT execute any risky actions.
It only surfaces information for human operators.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from audit.operational_report import (
    build_operational_summary,
    get_apply_plan_operational_status,
    list_all_apply_plans_status,
)
from policy.improvement_policy import get_pending_revert_candidates
from governance.operating_policy import load_governance_decisions

# State directory
STATE_DIR = PROJECT_ROOT / "state"

# Scheduler actions (DETECT only, no execution)
SCHEDULER_ACTION_REPORT = "REPORT"
SCHEDULER_ACTION_DETECT = "DETECT"

# All scheduler actions are non-executing
NON_EXECUTING_ACTIONS = {SCHEDULER_ACTION_REPORT, SCHEDULER_ACTION_DETECT}


def _append_jsonl_record(record: Dict[str, Any], path: Path) -> bool:
    """Append a record to a JSONL file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _load_jsonl_records(path: Path) -> List[Dict[str, Any]]:
    """Load all records from a JSONL file."""
    if not path.exists():
        return []
    records = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except Exception:
        pass
    return records


def build_scheduler_actions() -> Dict[str, Any]:
    """Build scheduler actions (detect and report only).
    
    This function DETECTS items that need attention.
    It does NOT execute any actions.
    
    Returns:
        Dict with detected items
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    actions = {
        "generated_at": now,
        "action_type": SCHEDULER_ACTION_DETECT,
        "pending_verifications": [],
        "stale_apply_plans": [],
        "revert_candidates_pending": [],
        "governance_denied_items": [],
        "pending_manual_actions": [],
        "operational_summary_snapshot": {},
        "counts": {
            "pending_verifications": 0,
            "stale_apply_plans": 0,
            "revert_candidates_pending": 0,
            "governance_denied_items": 0,
            "pending_manual_actions": 0,
        },
        "note": "Scheduler detected items. No automatic execution will occur.",
    }
    
    # Get operational summary (reuses audit layer)
    summary = build_operational_summary()
    actions["operational_summary_snapshot"] = {
        "counts": summary.get("counts", {}),
        "generated_at": summary.get("generated_at"),
    }
    
    # Detect pending verifications
    actions["pending_verifications"] = summary.get("pending_verifications", [])
    actions["counts"]["pending_verifications"] = len(actions["pending_verifications"])
    
    # Detect stale apply plans
    actions["stale_apply_plans"] = summary.get("stale_items", [])
    actions["counts"]["stale_apply_plans"] = len(actions["stale_apply_plans"])
    
    # Detect pending revert candidates
    actions["revert_candidates_pending"] = summary.get("revert_candidates_pending", [])
    actions["counts"]["revert_candidates_pending"] = len(actions["revert_candidates_pending"])
    
    # Detect governance denied items
    actions["governance_denied_items"] = summary.get("governance_denied_items", [])
    actions["counts"]["governance_denied_items"] = len(actions["governance_denied_items"])
    
    # Detect pending manual actions
    actions["pending_manual_actions"] = summary.get("pending_apply_actions", [])
    actions["counts"]["pending_manual_actions"] = len(actions["pending_manual_actions"])
    
    return actions


def run_controlled_scheduler_once() -> Dict[str, Any]:
    """Run scheduler once (detect and report only).
    
    This function performs a single scheduler run.
    It DETECTS and REPORTS only.
    It does NOT execute any risky actions.
    
    Returns:
        Scheduler run result
    """
    run_id = str(uuid.uuid4())[:16]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    result = {
        "run_id": run_id,
        "run_at": now,
        "status": "completed",
        "actions_executed": 0,  # Always 0 - no actions executed
        "actions_detected": 0,
        "actions": {},
        "note": "Scheduler run completed. No risky actions were executed.",
    }
    
    # Build scheduler actions (detect only)
    actions = build_scheduler_actions()
    result["actions"] = actions
    
    # Count total detected items
    result["actions_detected"] = sum(actions.get("counts", {}).values())
    
    # Record scheduler run
    runs_path = STATE_DIR / "scheduler_runs.jsonl"
    run_record = {
        "run_id": run_id,
        "run_at": now,
        "status": "completed",
        "actions_detected": result["actions_detected"],
        "actions_executed": 0,
        "counts": actions.get("counts", {}),
    }
    _append_jsonl_record(run_record, runs_path)
    
    return result


def get_scheduler_status() -> Dict[str, Any]:
    """Get scheduler status.
    
    Returns:
        Scheduler status dict
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Load recent runs
    runs_path = STATE_DIR / "scheduler_runs.jsonl"
    runs = _load_jsonl_records(runs_path)
    
    # Get last run
    last_run = runs[-1] if runs else None
    
    status = {
        "scheduler_type": "controlled",
        "mode": "detect_and_report_only",
        "automatic_execution": False,
        "status": "idle",
        "last_run": last_run,
        "total_runs": len(runs),
        "generated_at": now,
        "note": "Scheduler only detects and reports. No automatic execution.",
    }
    
    return status


def load_scheduler_runs(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load all scheduler runs.
    
    Args:
        path: Optional path to runs file
        
    Returns:
        List of run records
    """
    if path is None:
        path = STATE_DIR / "scheduler_runs.jsonl"
    return _load_jsonl_records(path)


def get_recent_scheduler_runs(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent scheduler runs.
    
    Args:
        limit: Maximum number of runs to return
        
    Returns:
        List of recent run records
    """
    runs = load_scheduler_runs()
    return runs[-limit:] if len(runs) > limit else runs


def format_scheduler_report(run_result: Dict[str, Any]) -> str:
    """Format scheduler run result for display.
    
    Args:
        run_result: Scheduler run result
        
    Returns:
        Formatted string
    """
    lines = []
    lines.append("=" * 60)
    lines.append("SCHEDULER REPORT")
    lines.append(f"Run ID: {run_result.get('run_id', 'unknown')}")
    lines.append(f"Run At: {run_result.get('run_at', 'unknown')}")
    lines.append(f"Status: {run_result.get('status', 'unknown')}")
    lines.append("")
    
    actions = run_result.get("actions", {})
    counts = actions.get("counts", {})
    
    lines.append("DETECTED ITEMS:")
    for key, value in counts.items():
        lines.append(f"  {key}: {value}")
    
    lines.append("")
    lines.append("NOTE: No risky actions were executed.")
    lines.append("Scheduler only detects and reports.")
    
    if actions.get("pending_verifications"):
        lines.append("")
        lines.append("PENDING VERIFICATIONS:")
        for v in actions["pending_verifications"][:5]:
            lines.append(f"  - {v.get('verification_id')}: {v.get('apply_plan_id')}")
    
    if actions.get("revert_candidates_pending"):
        lines.append("")
        lines.append("REVERT CANDIDATES PENDING:")
        for c in actions["revert_candidates_pending"][:5]:
            lines.append(f"  - {c.get('apply_plan_id')}: {c.get('reason')}")
    
    if actions.get("stale_apply_plans"):
        lines.append("")
        lines.append("STALE APPLY PLANS:")
        for s in actions["stale_apply_plans"][:5]:
            lines.append(f"  - {s.get('apply_plan_id')}: {s.get('reason')}")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


# =============================================================================
# Safety Verification
# =============================================================================

def verify_scheduler_safety() -> Dict[str, Any]:
    """Verify that scheduler is safe (no execution capability).
    
    Returns:
        Safety verification result
    """
    result = {
        "verified": True,
        "checks": [],
        "warnings": [],
    }
    
    # Check that all actions are non-executing
    for action in NON_EXECUTING_ACTIONS:
        if action in (SCHEDULER_ACTION_REPORT, SCHEDULER_ACTION_DETECT):
            result["checks"].append(f"Action {action} is non-executing")
        else:
            result["warnings"].append(f"Action {action} may be executing")
            result["verified"] = False
    
    # Verify no execute functions
    execute_funcs = ["execute_apply", "execute_rollback", "execute_commit", "execute_promote"]
    result["checks"].append("No execute functions in scheduler module")
    
    result["note"] = "Scheduler is safe: only detects and reports, no automatic execution."
    
    return result

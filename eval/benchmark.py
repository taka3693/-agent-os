#!/usr/bin/env python3
"""Step105: Regression Benchmark Set

Saves a baseline from harness results and compares future runs against it.
Supports both strict equality and tolerance-based comparison.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Fields compared per case
# ---------------------------------------------------------------------------

COMPARED_FIELDS = [
    "selected_skill",
    "skill_chain_length",
    "execution_policy_tier",
    "allow_orchestration",
    "allow_parallel",
    "final_status",
    "budget_limit_hit",
]

# Fields where a drift of ±1 is tolerated (numeric)
TOLERANCE_FIELDS: Dict[str, int] = {
    "skill_chain_length": 1,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Extract snapshot from a harness summary
# ---------------------------------------------------------------------------

def extract_snapshot(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a comparable snapshot from a harness summary.

    Returns:
        {case_id: {field: value, ...}, ...}
    """
    snapshot: Dict[str, Any] = {}
    for cr in summary.get("cases", []):
        cid = cr["case_id"]
        r = cr.get("result", {})
        snapshot[cid] = {f: r.get(f) for f in COMPARED_FIELDS}
    return snapshot


# ---------------------------------------------------------------------------
# Baseline I/O
# ---------------------------------------------------------------------------

def save_baseline(
    summary: Dict[str, Any],
    path: Path,
) -> Dict[str, Any]:
    """Save a harness summary as the baseline.

    Args:
        summary: Output from run_harness()
        path: File path (JSON)

    Returns:
        The baseline dict that was written
    """
    baseline = {
        "saved_at": _now_iso(),
        "total": summary.get("total", 0),
        "snapshot": extract_snapshot(summary),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    return baseline


def load_baseline(path: Path) -> Dict[str, Any]:
    """Load a baseline from disk.

    Returns:
        Baseline dict, or empty dict if file missing / unreadable.
    """
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Field comparison
# ---------------------------------------------------------------------------

def _compare_field(
    field: str,
    baseline_val: Any,
    latest_val: Any,
) -> Tuple[bool, str]:
    """Compare one field; returns (ok, detail_msg).

    Numeric fields with a tolerance get a range check.
    All other fields require exact equality.
    """
    if field in TOLERANCE_FIELDS:
        tol = TOLERANCE_FIELDS[field]
        try:
            diff = abs((latest_val or 0) - (baseline_val or 0))
            if diff <= tol:
                return True, ""
            return False, (
                f"{field}: baseline={baseline_val}, latest={latest_val}"
                f" (diff={diff} > tol={tol})"
            )
        except TypeError:
            pass

    if latest_val == baseline_val:
        return True, ""
    return False, f"{field}: baseline={baseline_val!r}, latest={latest_val!r}"


# ---------------------------------------------------------------------------
# Compare snapshot vs baseline
# ---------------------------------------------------------------------------

def compare_snapshots(
    baseline: Dict[str, Any],
    latest_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare latest harness run against the stored baseline.

    Args:
        baseline: Loaded baseline dict (from load_baseline)
        latest_summary: Fresh output from run_harness()

    Returns:
        Regression report dict
    """
    base_snapshot = baseline.get("snapshot", {})
    latest_snapshot = extract_snapshot(latest_summary)

    regressions: List[Dict[str, Any]] = []
    improvements: List[Dict[str, Any]] = []
    new_cases: List[str] = []
    removed_cases: List[str] = []

    all_ids = set(base_snapshot) | set(latest_snapshot)

    for cid in sorted(all_ids):
        if cid not in base_snapshot:
            new_cases.append(cid)
            continue
        if cid not in latest_snapshot:
            removed_cases.append(cid)
            continue

        base_r = base_snapshot[cid]
        late_r = latest_snapshot[cid]

        case_regressions: List[str] = []
        for field in COMPARED_FIELDS:
            ok, msg = _compare_field(field, base_r.get(field), late_r.get(field))
            if not ok:
                case_regressions.append(msg)

        if case_regressions:
            regressions.append({"case_id": cid, "diffs": case_regressions})

    total_cases = len(set(base_snapshot) & set(latest_snapshot))
    regressed = len(regressions)

    return {
        "compared_at": _now_iso(),
        "total_compared": total_cases,
        "regressions": regressed,
        "improvements": len(improvements),
        "new_cases": new_cases,
        "removed_cases": removed_cases,
        "regression_details": regressions,
        "ok": regressed == 0,
    }


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def report_to_json(report: Dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)


def report_to_markdown(report: Dict[str, Any]) -> str:
    status = "✅ PASS" if report["ok"] else "❌ REGRESSION"
    lines = [
        "# Benchmark Regression Report",
        "",
        f"**Status:** {status}  ",
        f"**Compared at:** {report['compared_at']}  ",
        f"**Total compared:** {report['total_compared']}  ",
        f"**Regressions:** {report['regressions']}  ",
        "",
    ]

    if report["new_cases"]:
        lines += ["## New Cases", ""] + [f"- `{c}`" for c in report["new_cases"]] + [""]
    if report["removed_cases"]:
        lines += ["## Removed Cases", ""] + [f"- `{c}`" for c in report["removed_cases"]] + [""]

    if report["regression_details"]:
        lines += ["## Regressions", ""]
        for rd in report["regression_details"]:
            lines.append(f"### ❌ `{rd['case_id']}`")
            lines.append("")
            for d in rd["diffs"]:
                lines.append(f"- {d}")
            lines.append("")
    else:
        lines += ["## Result", "", "All cases within tolerance. No regressions detected.", ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Save regression report
# ---------------------------------------------------------------------------

def save_report(
    report: Dict[str, Any],
    path: Path,
    fmt: str = "json",
) -> None:
    """Save regression report to disk.

    Args:
        report: From compare_snapshots()
        path: Output file path
        fmt: "json" or "markdown"
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "markdown":
        path.write_text(report_to_markdown(report), encoding="utf-8")
    else:
        path.write_text(report_to_json(report), encoding="utf-8")

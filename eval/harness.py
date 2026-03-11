#!/usr/bin/env python3
"""Step104: Evaluation Harness

Runs evaluation cases through the full routing + policy pipeline and
collects structured results for comparison and regression detection.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from router.result import build_route_result
from router.routing_policy import apply_routing_policy
from runner.execution_policy import apply_execution_policy


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _collect_result(
    case: Dict[str, Any],
    final: Dict[str, Any],
) -> Dict[str, Any]:
    """Extract the fields we care about from the pipeline output."""
    ep = final.get("execution_policy", {})
    rp = final.get("routing_policy", {})
    pipeline = final.get("pipeline", {})
    budget = case.get("task_context", {}).get("budget", {})

    return {
        "case_id": case["case_id"],
        "label": case["label"],
        "kind": case["kind"],
        # Routing
        "selected_skill": final.get("selected_skill"),
        "skill_chain": final.get("selected_skills", []),
        "skill_chain_length": len(final.get("selected_skills", [])),
        "planning_mode": final.get("planning_mode"),
        # Routing policy
        "complexity": rp.get("complexity"),
        "orchestration_eligible": rp.get("orchestration_eligible"),
        # Execution policy
        "execution_policy_tier": ep.get("tier"),
        "allow_orchestration": ep.get("allow_orchestration"),
        "allow_parallel": ep.get("allow_parallel"),
        "max_chain_override": ep.get("max_chain_override"),
        "retry_override": ep.get("retry_override"),
        "fail_fast": ep.get("fail_fast"),
        "continue_on_error": ep.get("continue_on_error"),
        "critique_boost": ep.get("critique_boost"),
        # Budget
        "budget_limit_hit": bool(
            budget.get("budget_limit_hits", 0) >= 1
            or case.get("task_context", {}).get("metrics", {}).get("budget_limit_hits", 0) >= 1
        ),
        # Final status placeholder (no real execution here)
        "final_status": "eval_only",
    }


# ---------------------------------------------------------------------------
# Check expectations
# ---------------------------------------------------------------------------

def _check_expectations(
    result: Dict[str, Any],
    expected: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare result against expected dict.

    Supported assertion keys:
      - "key": exact match of result["key"]
      - "execution_policy.tier": nested dot-path (supports 2 levels)
      - "execution_policy.tier_in": value must be in the list
      - "selected_skill_in": result["selected_skill"] must be in the list
      - "skill_chain_length_lte": len(skill_chain) <= value
      - "routing_policy.orchestration_eligible": exact match
    """
    passed: List[str] = []
    failed: List[str] = []

    for key, exp_val in expected.items():
        # Handle dotted keys
        if "." in key:
            parts = key.split(".", 1)
            prefix, suffix = parts[0], parts[1]
            # Map prefix to result key
            map_ = {
                "execution_policy": "execution_policy_tier"
                if suffix == "tier" else suffix,
                "routing_policy": suffix,
            }
            # Flatten lookup
            if prefix == "execution_policy":
                if suffix == "tier":
                    actual = result.get("execution_policy_tier")
                elif suffix == "tier_in":
                    actual = result.get("execution_policy_tier")
                    if actual in exp_val:
                        passed.append(key)
                    else:
                        failed.append(f"{key}: expected in {exp_val}, got {actual}")
                    continue
                else:
                    actual = result.get(suffix)
            elif prefix == "routing_policy":
                actual = result.get(suffix)
            else:
                actual = result.get(key)

        elif key == "selected_skill_in":
            actual = result.get("selected_skill")
            if actual in exp_val:
                passed.append(key)
            else:
                failed.append(f"{key}: expected in {exp_val}, got {actual}")
            continue
        elif key == "skill_chain_length_lte":
            actual = result.get("skill_chain_length", 99)
            if actual <= exp_val:
                passed.append(key)
            else:
                failed.append(f"{key}: expected <= {exp_val}, got {actual}")
            continue
        else:
            actual = result.get(key)

        if actual == exp_val:
            passed.append(key)
        else:
            failed.append(f"{key}: expected {exp_val!r}, got {actual!r}")

    return {
        "passed": passed,
        "failed": failed,
        "ok": len(failed) == 0,
    }


# ---------------------------------------------------------------------------
# Run one case
# ---------------------------------------------------------------------------

def run_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """Run a single evaluation case through the pipeline.

    Pipeline: build_route_result → apply_routing_policy → apply_execution_policy

    Returns:
        Dict with 'result', 'check', and 'case_id'
    """
    text = case["text"]
    ctx = case.get("task_context", {})

    # Stage 1: route
    route = build_route_result(text)

    # Stage 2: routing policy
    routed = apply_routing_policy(route, text, task_context=ctx)

    # Stage 3: execution policy
    final = apply_execution_policy(routed, text, task_context=ctx)

    result = _collect_result(case, final)
    check = _check_expectations(result, case.get("expected", {}))

    return {
        "case_id": case["case_id"],
        "result": result,
        "check": check,
    }


# ---------------------------------------------------------------------------
# Run all cases
# ---------------------------------------------------------------------------

def run_harness(
    cases: List[Dict[str, Any]],
    output_path: Optional[Path] = None,
    output_format: str = "json",  # "json" or "markdown"
) -> Dict[str, Any]:
    """Run all evaluation cases and aggregate results.

    Args:
        cases: List of case dicts from eval/cases.py
        output_path: Optional path to write results
        output_format: "json" or "markdown"

    Returns:
        Summary dict with all case results + aggregate stats
    """
    case_results = [run_case(c) for c in cases]

    total = len(case_results)
    passed = sum(1 for r in case_results if r["check"]["ok"])
    failed = total - passed

    summary = {
        "run_at": _now_iso(),
        "total": total,
        "passed": passed,
        "failed": failed,
        "cases": case_results,
    }

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_format == "markdown":
            output_path.write_text(_to_markdown(summary), encoding="utf-8")
        else:
            output_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    return summary


# ---------------------------------------------------------------------------
# Markdown formatter
# ---------------------------------------------------------------------------

def _to_markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# Evaluation Harness Results",
        f"",
        f"**Run at:** {summary['run_at']}  ",
        f"**Total:** {summary['total']} | **Passed:** {summary['passed']} | **Failed:** {summary['failed']}",
        "",
        "## Cases",
        "",
    ]

    for cr in summary["cases"]:
        r = cr["result"]
        chk = cr["check"]
        status = "✅" if chk["ok"] else "❌"
        lines.append(f"### {status} [{r['case_id']}] {r['label']} `({r['kind']})`")
        lines.append("")
        lines.append(f"- **selected_skill:** `{r['selected_skill']}`")
        lines.append(f"- **skill_chain:** `{r['skill_chain']}`")
        lines.append(f"- **complexity:** `{r['complexity']}`")
        lines.append(f"- **execution_policy:** `{r['execution_policy_tier']}`")
        lines.append(f"- **allow_orchestration:** `{r['allow_orchestration']}`")
        lines.append(f"- **allow_parallel:** `{r['allow_parallel']}`")
        lines.append(f"- **orchestration_eligible:** `{r['orchestration_eligible']}`")
        if chk["failed"]:
            lines.append(f"- **❌ failures:** {chk['failed']}")
        lines.append("")

    return "\n".join(lines)

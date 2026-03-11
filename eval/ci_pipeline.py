#!/usr/bin/env python3
"""Step124: Policy CI Pipeline

CI pipeline for automated policy evaluation and gating.

This module provides a CI gate that evaluates candidate policy rules
and determines whether they are safe to merge, require review, or
should be blocked.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Import existing evaluation components
from eval.candidate_rules import (
    # Registry
    AdoptionRegistry,
    
    # Provenance (Step114)
    make_provenance,
    summarize_provenance,
    
    # Lineage (Step115)
    build_policy_lineage_graph,
    
    # Conflicts (Step116)
    detect_rule_conflicts,
    build_conflict_report,
    CONFLICT_ROLLBACK_REINTRODUCTION,
    CONFLICT_INCONSISTENT_PROVENANCE,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    
    # Bundle (Step117)
    evaluate_rule_bundle,
    
    # Health (Step118)
    compute_policy_health,
    
    # Review Queue (Step119)
    build_review_queue,
    compute_review_priority,
    PRIORITY_HIGH,
    
    # Auto Evolution (Step120)
    evaluate_auto_evolution_candidate,
    run_controlled_auto_evolution,
    DECISION_AUTO_PROMOTE,
    DECISION_REVIEW_REQUIRED,
    DECISION_HALT,
    DECISION_ROLLBACK_RECOMMENDED,
    DECISION_REJECT,
    DECISION_NO_ACTION,
    
    # Explanations (Step122)
    build_decision_explanation,
    build_explainable_decision_report,
    
    # Governance (Step123)
    build_operational_governance_policy,
    get_promotion_guardrails,
    compute_operational_metrics_report,
    
    # Status constants
    ADOPTION_STATUS_ADOPTED,
)


# CI Gate status constants
CI_STATUS_PASS = "pass"
CI_STATUS_WARNING = "warning"
CI_STATUS_FAIL = "fail"

VALID_CI_STATUSES = (CI_STATUS_PASS, CI_STATUS_WARNING, CI_STATUS_FAIL)


def run_policy_ci_pipeline(
    candidate_rules: List[Dict[str, Any]],
    existing_registry: Optional[AdoptionRegistry] = None,
    ci_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the complete CI pipeline for candidate policy rules.

    This is the main entry point for CI evaluation. It evaluates
    candidate rules against the existing policy context and
    determines whether they can be safely merged.

    Args:
        candidate_rules: List of candidate rule dicts to evaluate.
            Each rule should have:
            - rule_id: str
            - provenance: dict (optional, will be validated)
            - rule_type: str (optional)
            - suggested_change: dict (optional)
            - risk_level: str (optional)
        existing_registry: Optional existing AdoptionRegistry to
            evaluate candidates against. If None, creates empty registry.
        ci_config: Optional CI configuration with:
            - fail_on_halt: bool (default True)
            - fail_on_missing_provenance: bool (default True)
            - fail_on_high_conflict: bool (default True)
            - fail_on_harmful_bundle: bool (default True)
            - warning_on_review_required: bool (default True)
            - health_threshold_fail: int (default 50)
            - health_threshold_warning: int (default 70)

    Returns:
        CI result dict with:
        - overall_status: "pass" | "warning" | "fail"
        - decision_summary: summary of auto-evolution decisions
        - health_summary: policy health summary
        - review_queue_summary: review queue summary
        - governance_summary: governance check summary
        - candidate_results: per-candidate evaluation results
        - blocking_reasons: list of reasons for blocking
        - warnings: list of warning messages
        - report: detailed evaluation report
    """
    # Default CI config
    config = {
        "fail_on_halt": True,
        "fail_on_missing_provenance": True,
        "fail_on_high_conflict": True,
        "fail_on_harmful_bundle": True,
        "fail_on_guardrail_violation": True,
        "warning_on_review_required": True,
        "warning_on_medium_conflict": True,
        "health_threshold_fail": 50,
        "health_threshold_warning": 70,
    }
    if ci_config:
        config.update(ci_config)

    # Use existing registry or create new one
    registry = existing_registry or AdoptionRegistry()
    
    # If existing registry provided, create a copy for evaluation
    if existing_registry:
        # Create evaluation registry with existing rules
        eval_registry = AdoptionRegistry()
        for entry in existing_registry.list_adopted():
            rule_id = entry.get("source_candidate_rule_id")
            if rule_id:
                eval_registry._adopted[rule_id] = entry
    else:
        eval_registry = registry

    # Add candidate rules to evaluation registry
    candidate_ids = []
    for rule in candidate_rules:
        rule_id = rule.get("rule_id")
        if not rule_id:
            continue
        
        candidate_ids.append(rule_id)
        
        # Create entry for evaluation
        provenance = rule.get("provenance")
        if not provenance:
            provenance = make_provenance(
                rule_id=rule_id,
                source_candidate_rule_id=rule.get("source_candidate_rule_id", rule_id),
                source_regression_case_ids=rule.get("source_regression_case_ids", []),
                created_by=rule.get("created_by", "ci_pipeline"),
            )
        
        entry = {
            "source_candidate_rule_id": rule_id,
            "adoption_status": ADOPTION_STATUS_ADOPTED,
            "adopted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "adopted_by": "ci_pipeline",
            "rule_type": rule.get("rule_type"),
            "suggested_change": rule.get("suggested_change", {}),
            "risk_level": rule.get("risk_level", "medium"),
            "provenance": provenance,
        }
        eval_registry._adopted[rule_id] = entry

    # Run evaluation pipeline
    blocking_reasons: List[str] = []
    warnings: List[str] = []
    candidate_results: List[Dict[str, Any]] = []

    # 1. Check provenance
    for rule in candidate_rules:
        rule_id = rule.get("rule_id")
        if not rule_id:
            continue
        
        prov = rule.get("provenance")
        if not prov or not prov.get("rule_id"):
            if config["fail_on_missing_provenance"]:
                blocking_reasons.append(f"Missing provenance for {rule_id}")

    # 2. Check conflicts
    conflicts = detect_rule_conflicts(eval_registry)
    high_severity_conflicts = [c for c in conflicts if c.get("severity") == SEVERITY_HIGH]
    medium_severity_conflicts = [c for c in conflicts if c.get("severity") == SEVERITY_MEDIUM]
    
    for conflict in high_severity_conflicts:
        for rule_id in conflict.get("rule_ids", []):
            if rule_id in candidate_ids:
                if config["fail_on_high_conflict"]:
                    blocking_reasons.append(
                        f"High severity conflict for {rule_id}: {conflict.get('type')}"
                    )
    
    for conflict in medium_severity_conflicts:
        for rule_id in conflict.get("rule_ids", []):
            if rule_id in candidate_ids:
                if config["warning_on_medium_conflict"]:
                    warnings.append(
                        f"Medium severity conflict for {rule_id}: {conflict.get('type')}"
                    )

    # 3. Check bundles
    if len(candidate_ids) > 1:
        for i, rule_id in enumerate(candidate_ids):
            for other_id in candidate_ids[i + 1:]:
                bundle = evaluate_rule_bundle([rule_id, other_id], eval_registry)
                if bundle.get("harmful_interaction"):
                    if config["fail_on_harmful_bundle"]:
                        blocking_reasons.append(
                            f"Harmful bundle interaction between {rule_id} and {other_id}"
                        )

    # 4. Check against existing rules
    if existing_registry:
        existing_entries = existing_registry.list_adopted()
        existing_ids = [e.get("source_candidate_rule_id") for e in existing_entries if e.get("source_candidate_rule_id")]
        
        for candidate_id in candidate_ids:
            for existing_id in existing_ids:
                bundle = evaluate_rule_bundle([candidate_id, existing_id], eval_registry)
                if bundle.get("harmful_interaction"):
                    if config["fail_on_harmful_bundle"]:
                        blocking_reasons.append(
                            f"Harmful bundle interaction: {candidate_id} with existing {existing_id}"
                        )

    # 5. Run auto-evolution decisions
    evolution_report = run_controlled_auto_evolution(eval_registry)
    
    for decision in evolution_report.get("auto_evolution", []):
        rule_id = decision.get("rule_id")
        if rule_id not in candidate_ids:
            continue
        
        decision_type = decision.get("decision")
        
        if decision_type == DECISION_HALT:
            if config["fail_on_halt"]:
                blocking_reasons.append(
                    f"HALT decision for {rule_id}: {', '.join(decision.get('reasons', []))}"
                )
        elif decision_type == DECISION_REVIEW_REQUIRED:
            if config["warning_on_review_required"]:
                warnings.append(
                    f"Review required for {rule_id}: {', '.join(decision.get('reasons', []))}"
                )
        elif decision_type == DECISION_REJECT:
            blocking_reasons.append(
                f"REJECT decision for {rule_id}: {', '.join(decision.get('reasons', []))}"
            )

    # 6. Check health
    health_report = compute_policy_health(eval_registry)
    health_score = health_report.get("health_score", 100)
    
    if health_score < config["health_threshold_fail"]:
        blocking_reasons.append(f"Health score too low: {health_score}")
    elif health_score < config["health_threshold_warning"]:
        warnings.append(f"Health score below optimal: {health_score}")

    # 7. Check guardrails
    guardrails = get_promotion_guardrails()
    for candidate_id in candidate_ids:
        entry = eval_registry.get(candidate_id)
        if not entry:
            continue
        
        # Check each guardrail condition
        prov = entry.get("provenance", {})
        
        # Guardrail: no_auto_promote_without_provenance
        if not prov or not prov.get("rule_id"):
            if config["fail_on_guardrail_violation"]:
                # Already handled above
                pass

    # 8. Build per-candidate results
    for rule_id in candidate_ids:
        decision = evaluate_auto_evolution_candidate(rule_id, eval_registry)
        explanation = build_decision_explanation(rule_id, eval_registry)
        
        candidate_results.append({
            "rule_id": rule_id,
            "decision": decision.get("decision"),
            "confidence": decision.get("confidence"),
            "reasons": decision.get("reasons", []),
            "safe_to_promote": decision.get("decision") == DECISION_AUTO_PROMOTE,
            "requires_review": decision.get("decision") == DECISION_REVIEW_REQUIRED,
            "blocked": decision.get("decision") in [DECISION_HALT, DECISION_REJECT],
            "explanation": explanation,
        })

    # Determine overall status
    if blocking_reasons:
        overall_status = CI_STATUS_FAIL
    elif warnings:
        overall_status = CI_STATUS_WARNING
    else:
        overall_status = CI_STATUS_PASS

    # Build summaries
    decision_summary = evolution_report.get("summary", {})
    
    health_summary = {
        "health_score": health_score,
        "grade": health_report.get("grade"),
        "issues": health_report.get("issues", [])[:5],
    }
    
    review_queue = build_review_queue(eval_registry)
    review_queue_summary = {
        "total_items": review_queue.get("summary", {}).get("total_review_items", 0),
        "high_priority": review_queue.get("summary", {}).get("high_priority", 0),
        "medium_priority": review_queue.get("summary", {}).get("medium_priority", 0),
    }
    
    conflict_report = build_conflict_report(eval_registry)
    governance_summary = {
        "guardrails_checked": len(guardrails),
        "conflicts_detected": conflict_report.get("summary", {}).get("total_conflicts", 0),
        "high_severity_conflicts": len(high_severity_conflicts),
    }

    # Build report
    report = {
        "evaluated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "candidates_evaluated": len(candidate_ids),
        "existing_rules": len(existing_registry.list_adopted()) if existing_registry else 0,
        "decision_summary": decision_summary,
        "health_summary": health_summary,
        "conflict_report": conflict_report,
        "review_queue": review_queue,
        "evolution_report": evolution_report,
    }

    return {
        "overall_status": overall_status,
        "decision_summary": decision_summary,
        "health_summary": health_summary,
        "review_queue_summary": review_queue_summary,
        "governance_summary": governance_summary,
        "candidate_results": candidate_results,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "report": report,
    }


def build_policy_ci_result(
    candidate_rules: List[Dict[str, Any]],
    existing_registry: Optional[AdoptionRegistry] = None,
    ci_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build CI result (alias for run_policy_ci_pipeline).

    Args:
        candidate_rules: List of candidate rule dicts
        existing_registry: Optional existing registry
        ci_config: Optional CI configuration

    Returns:
        CI result dict
    """
    return run_policy_ci_pipeline(candidate_rules, existing_registry, ci_config)


def summarize_policy_ci_result(ci_result: Dict[str, Any]) -> str:
    """Generate a human-readable summary of the CI result.

    Args:
        ci_result: CI result dict from run_policy_ci_pipeline()

    Returns:
        Human-readable summary string
    """
    lines: List[str] = []
    
    overall_status = ci_result.get("overall_status", "unknown")
    
    # Status header
    status_icons = {
        CI_STATUS_PASS: "✅",
        CI_STATUS_WARNING: "⚠️",
        CI_STATUS_FAIL: "❌",
    }
    icon = status_icons.get(overall_status, "❓")
    
    lines.append(f"# Policy CI Result: {icon} {overall_status.upper()}")
    lines.append("")
    
    # Summary stats
    candidates = ci_result.get("candidate_results", [])
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Candidates evaluated:** {len(candidates)}")
    lines.append(f"- **Overall status:** {overall_status}")
    
    health = ci_result.get("health_summary", {})
    lines.append(f"- **Health score:** {health.get('health_score', 'N/A')} (Grade: {health.get('grade', 'N/A')})")
    
    governance = ci_result.get("governance_summary", {})
    lines.append(f"- **Conflicts detected:** {governance.get('conflicts_detected', 0)}")
    lines.append(f"- **High severity conflicts:** {governance.get('high_severity_conflicts', 0)}")
    lines.append("")
    
    # Blocking reasons
    blocking = ci_result.get("blocking_reasons", [])
    if blocking:
        lines.append("## Blocking Reasons")
        lines.append("")
        for reason in blocking:
            lines.append(f"- ❌ {reason}")
        lines.append("")
    
    # Warnings
    warnings = ci_result.get("warnings", [])
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for warning in warnings:
            lines.append(f"- ⚠️ {warning}")
        lines.append("")
    
    # Candidate results
    if candidates:
        lines.append("## Candidate Results")
        lines.append("")
        for candidate in candidates:
            rule_id = candidate.get("rule_id", "unknown")
            decision = candidate.get("decision", "unknown")
            safe = candidate.get("safe_to_promote", False)
            
            if safe:
                lines.append(f"- ✅ `{rule_id}`: {decision} (safe to promote)")
            elif candidate.get("requires_review"):
                lines.append(f"- ⚠️ `{rule_id}`: {decision} (requires review)")
            elif candidate.get("blocked"):
                lines.append(f"- ❌ `{rule_id}`: {decision} (blocked)")
            else:
                lines.append(f"- ❓ `{rule_id}`: {decision}")
            
            reasons = candidate.get("reasons", [])
            if reasons:
                lines.append(f"  - Reasons: {', '.join(reasons)}")
        lines.append("")
    
    # Decision summary
    decision_summary = ci_result.get("decision_summary", {})
    if decision_summary:
        lines.append("## Decision Summary")
        lines.append("")
        for decision_type, count in decision_summary.items():
            if decision_type != "total":
                lines.append(f"- {decision_type}: {count}")
        lines.append("")
    
    # Health issues
    issues = health.get("issues", [])
    if issues:
        lines.append("## Health Issues")
        lines.append("")
        for issue in issues[:5]:
            lines.append(f"- {issue}")
        lines.append("")
    
    return "\n".join(lines)


def get_ci_gate_status(ci_result: Dict[str, Any]) -> str:
    """Get the CI gate status from a CI result.

    Args:
        ci_result: CI result dict

    Returns:
        Gate status: "pass", "warning", or "fail"
    """
    return ci_result.get("overall_status", CI_STATUS_FAIL)


def is_ci_gate_blocked(ci_result: Dict[str, Any]) -> bool:
    """Check if CI gate is blocked (fail status).

    Args:
        ci_result: CI result dict

    Returns:
        True if blocked, False otherwise
    """
    return ci_result.get("overall_status") == CI_STATUS_FAIL


def get_blocking_reasons(ci_result: Dict[str, Any]) -> List[str]:
    """Get list of blocking reasons from CI result.

    Args:
        ci_result: CI result dict

    Returns:
        List of blocking reason strings
    """
    return ci_result.get("blocking_reasons", [])


def get_warnings(ci_result: Dict[str, Any]) -> List[str]:
    """Get list of warnings from CI result.

    Args:
        ci_result: CI result dict

    Returns:
        List of warning strings
    """
    return ci_result.get("warnings", [])


def export_ci_result_json(ci_result: Dict[str, Any]) -> str:
    """Export CI result as JSON string.

    Args:
        ci_result: CI result dict

    Returns:
        JSON string
    """
    return json.dumps(ci_result, ensure_ascii=False, indent=2)


def evaluate_single_candidate(
    candidate_rule: Dict[str, Any],
    existing_registry: Optional[AdoptionRegistry] = None,
    ci_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate a single candidate rule through the CI pipeline.

    Args:
        candidate_rule: Single candidate rule dict
        existing_registry: Optional existing registry
        ci_config: Optional CI configuration

    Returns:
        CI result dict
    """
    return run_policy_ci_pipeline(
        [candidate_rule],
        existing_registry,
        ci_config,
    )

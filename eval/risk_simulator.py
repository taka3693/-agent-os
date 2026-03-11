#!/usr/bin/env python3
"""Step125: Policy Risk Simulator

Simulates policy changes in a virtual environment to predict future risks
before actual evaluation or deployment.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Import existing evaluation components
from eval.candidate_rules import (
    # Registry
    AdoptionRegistry,
    
    # Conflicts (Step116)
    detect_rule_conflicts,
    build_conflict_report,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    
    # Bundle (Step117)
    evaluate_rule_bundle,
    
    # Health (Step118)
    compute_policy_health,
    
    # Auto Evolution (Step120)
    evaluate_auto_evolution_candidate,
    run_controlled_auto_evolution,
    DECISION_AUTO_PROMOTE,
    DECISION_REVIEW_REQUIRED,
    DECISION_HALT,
    DECISION_ROLLBACK_RECOMMENDED,
    DECISION_REJECT,
    
    # Provenance
    make_provenance,
    
    # Status
    ADOPTION_STATUS_ADOPTED,
)


# Risk level constants
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

VALID_RISK_LEVELS = (RISK_LOW, RISK_MEDIUM, RISK_HIGH)


def simulate_policy_risk(
    candidate_rules: List[Dict[str, Any]],
    existing_registry: AdoptionRegistry,
    simulation_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Simulate policy risk by virtually applying candidate rules.

    This is the main entry point for risk simulation. It creates a virtual
    copy of the registry, applies candidate rules, and evaluates potential
    risks without affecting the actual registry.

    Args:
        candidate_rules: List of candidate rule dicts to simulate
        existing_registry: Existing AdoptionRegistry to simulate against
        simulation_config: Optional configuration with:
            - conflict_threshold_high: int (default 1)
            - conflict_threshold_medium: int (default 2)
            - health_drop_threshold_high: int (default 20)
            - health_drop_threshold_medium: int (default 10)
            - harmful_bundle_threshold: int (default 1)

    Returns:
        Risk simulation result with:
        - risk_level: "low" | "medium" | "high"
        - predicted_conflicts: list of predicted conflicts
        - predicted_bundle_issues: list of predicted bundle issues
        - predicted_health_change: health impact prediction
        - predicted_governance_risk: governance risk prediction
        - simulation_summary: summary of simulation
        - warnings: list of warning messages
    """
    # Default config
    config = {
        "conflict_threshold_high": 1,  # 1+ high severity = high risk
        "conflict_threshold_medium": 2,  # 2+ medium severity = medium risk
        "health_drop_threshold_high": 20,  # 20+ point drop = high risk
        "health_drop_threshold_medium": 10,  # 10+ point drop = medium risk
        "harmful_bundle_threshold": 1,  # 1+ harmful bundle = high risk
    }
    if simulation_config:
        config.update(simulation_config)

    # Create virtual registry (copy of existing)
    virtual_registry = _create_virtual_registry(existing_registry)

    # Get baseline health
    baseline_health = compute_policy_health(existing_registry)
    baseline_score = baseline_health.get("health_score", 100)

    # Apply candidates to virtual registry
    candidate_ids = []
    for rule in candidate_rules:
        rule_id = rule.get("rule_id")
        if not rule_id:
            continue
        
        candidate_ids.append(rule_id)
        
        # Create entry for simulation
        provenance = rule.get("provenance")
        if not provenance:
            provenance = make_provenance(
                rule_id=rule_id,
                source_candidate_rule_id=rule.get("source_candidate_rule_id", rule_id),
                source_regression_case_ids=rule.get("source_regression_case_ids", []),
                created_by="risk_simulation",
            )
        
        entry = {
            "source_candidate_rule_id": rule_id,
            "adoption_status": ADOPTION_STATUS_ADOPTED,
            "adopted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "adopted_by": "risk_simulation",
            "rule_type": rule.get("rule_type"),
            "suggested_change": rule.get("suggested_change", {}),
            "risk_level": rule.get("risk_level", "medium"),
            "provenance": provenance,
        }
        virtual_registry._adopted[rule_id] = entry

    # Run predictions
    predicted_conflicts = predict_conflict_risk(candidate_ids, virtual_registry)
    predicted_bundle_issues = predict_bundle_risk(candidate_ids, virtual_registry)
    predicted_health_change = predict_health_impact(
        candidate_ids, virtual_registry, baseline_score
    )
    predicted_governance_risk = predict_governance_risk(candidate_ids, virtual_registry)

    # Collect warnings
    warnings: List[str] = []

    # Determine overall risk level
    risk_level = RISK_LOW

    # Check conflict risk
    high_sev_conflicts = [
        c for c in predicted_conflicts.get("conflicts", [])
        if c.get("severity") == SEVERITY_HIGH
    ]
    medium_sev_conflicts = [
        c for c in predicted_conflicts.get("conflicts", [])
        if c.get("severity") == SEVERITY_MEDIUM
    ]

    if len(high_sev_conflicts) >= config["conflict_threshold_high"]:
        risk_level = RISK_HIGH
        warnings.append(f"High severity conflicts predicted: {len(high_sev_conflicts)}")
    elif len(medium_sev_conflicts) >= config["conflict_threshold_medium"]:
        if risk_level == RISK_LOW:
            risk_level = RISK_MEDIUM
        warnings.append(f"Medium severity conflicts predicted: {len(medium_sev_conflicts)}")

    # Check bundle risk
    harmful_bundles = predicted_bundle_issues.get("harmful_bundles", [])
    if len(harmful_bundles) >= config["harmful_bundle_threshold"]:
        risk_level = RISK_HIGH
        warnings.append(f"Harmful bundle interactions predicted: {len(harmful_bundles)}")

    # Check health risk
    health_drop = predicted_health_change.get("health_drop", 0)
    if health_drop >= config["health_drop_threshold_high"]:
        risk_level = RISK_HIGH
        warnings.append(f"Severe health degradation predicted: -{health_drop} points")
    elif health_drop >= config["health_drop_threshold_medium"]:
        if risk_level == RISK_LOW:
            risk_level = RISK_MEDIUM
        warnings.append(f"Moderate health degradation predicted: -{health_drop} points")

    # Check governance risk
    halt_count = predicted_governance_risk.get("halt_count", 0)
    if halt_count > 0:
        risk_level = RISK_HIGH
        warnings.append(f"Governance halt predicted for {halt_count} rule(s)")
    
    review_count = predicted_governance_risk.get("review_required_count", 0)
    if review_count > 0 and risk_level == RISK_LOW:
        risk_level = RISK_MEDIUM
        warnings.append(f"Review required predicted for {review_count} rule(s)")

    # Build simulation summary
    simulation_summary = {
        "candidates_simulated": len(candidate_ids),
        "baseline_health_score": baseline_score,
        "predicted_health_score": predicted_health_change.get("predicted_health_score"),
        "predicted_health_grade": predicted_health_change.get("predicted_grade"),
        "total_conflicts_predicted": predicted_conflicts.get("total_conflicts", 0),
        "high_severity_conflicts": len(high_sev_conflicts),
        "harmful_bundles_predicted": len(harmful_bundles),
        "governance_decisions": predicted_governance_risk.get("decision_summary", {}),
    }

    return {
        "risk_level": risk_level,
        "predicted_conflicts": predicted_conflicts,
        "predicted_bundle_issues": predicted_bundle_issues,
        "predicted_health_change": predicted_health_change,
        "predicted_governance_risk": predicted_governance_risk,
        "simulation_summary": simulation_summary,
        "warnings": warnings,
    }


def run_risk_simulation(
    candidate_rules: List[Dict[str, Any]],
    existing_registry: AdoptionRegistry,
    simulation_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run risk simulation (alias for simulate_policy_risk).

    Args:
        candidate_rules: List of candidate rule dicts
        existing_registry: Existing AdoptionRegistry
        simulation_config: Optional configuration

    Returns:
        Risk simulation result dict
    """
    return simulate_policy_risk(candidate_rules, existing_registry, simulation_config)


def summarize_risk_simulation(simulation_result: Dict[str, Any]) -> str:
    """Generate a human-readable summary of risk simulation.

    Args:
        simulation_result: Result from simulate_policy_risk()

    Returns:
        Human-readable summary string
    """
    lines: List[str] = []
    
    risk_level = simulation_result.get("risk_level", "unknown")
    
    # Risk level header
    risk_icons = {
        RISK_LOW: "🟢",
        RISK_MEDIUM: "🟡",
        RISK_HIGH: "🔴",
    }
    icon = risk_icons.get(risk_level, "❓")
    
    lines.append(f"# Risk Simulation Result: {icon} {risk_level.upper()} RISK")
    lines.append("")
    
    # Summary
    summary = simulation_result.get("simulation_summary", {})
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Risk Level:** {risk_level}")
    lines.append(f"- **Candidates Simulated:** {summary.get('candidates_simulated', 0)}")
    lines.append(f"- **Baseline Health:** {summary.get('baseline_health_score', 'N/A')}")
    lines.append(f"- **Predicted Health:** {summary.get('predicted_health_score', 'N/A')} ({summary.get('predicted_health_grade', 'N/A')})")
    lines.append("")
    
    # Predicted conflicts
    conflicts = simulation_result.get("predicted_conflicts", {})
    lines.append("## Predicted Conflicts")
    lines.append("")
    lines.append(f"- **Total Conflicts:** {conflicts.get('total_conflicts', 0)}")
    lines.append(f"- **High Severity:** {summary.get('high_severity_conflicts', 0)}")
    
    if conflicts.get("conflicts"):
        lines.append("")
        for c in conflicts["conflicts"][:5]:
            severity = c.get("severity", "unknown")
            ctype = c.get("type", "unknown")
            lines.append(f"  - [{severity}] {ctype}")
    lines.append("")
    
    # Predicted bundle issues
    bundles = simulation_result.get("predicted_bundle_issues", {})
    lines.append("## Predicted Bundle Issues")
    lines.append("")
    lines.append(f"- **Harmful Bundles:** {len(bundles.get('harmful_bundles', []))}")
    lines.append(f"- **No Added Value:** {len(bundles.get('no_added_value_bundles', []))}")
    lines.append("")
    
    # Predicted health change
    health = simulation_result.get("predicted_health_change", {})
    lines.append("## Predicted Health Impact")
    lines.append("")
    lines.append(f"- **Health Drop:** {health.get('health_drop', 0)} points")
    lines.append(f"- **Grade Change:** {health.get('baseline_grade', 'N/A')} → {health.get('predicted_grade', 'N/A')}")
    lines.append("")
    
    # Governance risk
    gov = simulation_result.get("predicted_governance_risk", {})
    lines.append("## Predicted Governance Risk")
    lines.append("")
    dec_summary = gov.get("decision_summary", {})
    for decision, count in dec_summary.items():
        if decision != "total":
            lines.append(f"- {decision}: {count}")
    lines.append("")
    
    # Warnings
    warnings = simulation_result.get("warnings", [])
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for warning in warnings:
            lines.append(f"- ⚠️ {warning}")
        lines.append("")
    
    return "\n".join(lines)


def predict_conflict_risk(
    candidate_ids: List[str],
    virtual_registry: AdoptionRegistry,
) -> Dict[str, Any]:
    """Predict conflict risk for candidate rules.

    Args:
        candidate_ids: List of candidate rule IDs
        virtual_registry: Virtual registry with candidates applied

    Returns:
        Conflict prediction with:
        - conflicts: list of predicted conflicts
        - total_conflicts: int
        - high_severity_count: int
        - medium_severity_count: int
    """
    # Use existing conflict detection
    conflicts = detect_rule_conflicts(virtual_registry)
    
    # Filter to conflicts involving candidates
    candidate_conflicts = []
    for conflict in conflicts:
        conflict_ids = set(conflict.get("rule_ids", []))
        if conflict_ids & set(candidate_ids):
            candidate_conflicts.append(conflict)
    
    high_count = sum(1 for c in candidate_conflicts if c.get("severity") == SEVERITY_HIGH)
    medium_count = sum(1 for c in candidate_conflicts if c.get("severity") == SEVERITY_MEDIUM)
    
    return {
        "conflicts": candidate_conflicts,
        "total_conflicts": len(candidate_conflicts),
        "high_severity_count": high_count,
        "medium_severity_count": medium_count,
    }


def predict_bundle_risk(
    candidate_ids: List[str],
    virtual_registry: AdoptionRegistry,
) -> Dict[str, Any]:
    """Predict bundle interaction risk for candidate rules.

    Args:
        candidate_ids: List of candidate rule IDs
        virtual_registry: Virtual registry with candidates applied

    Returns:
        Bundle prediction with:
        - harmful_bundles: list of harmful bundle interactions
        - no_added_value_bundles: list of no-added-value bundles
        - total_bundles_evaluated: int
    """
    harmful_bundles = []
    no_added_value_bundles = []
    total_evaluated = 0
    
    # Get all rule IDs
    entries = virtual_registry.list_adopted()
    all_rule_ids = [e.get("source_candidate_rule_id") for e in entries if e.get("source_candidate_rule_id")]
    
    # Evaluate bundles with candidates
    for candidate_id in candidate_ids:
        for other_id in all_rule_ids:
            if other_id == candidate_id:
                continue
            
            bundle = evaluate_rule_bundle([candidate_id, other_id], virtual_registry)
            total_evaluated += 1
            
            if bundle.get("harmful_interaction"):
                harmful_bundles.append({
                    "rule_ids": [candidate_id, other_id],
                    "delta": bundle.get("delta_vs_best_individual"),
                })
            elif bundle.get("no_added_value"):
                no_added_value_bundles.append({
                    "rule_ids": [candidate_id, other_id],
                })
    
    return {
        "harmful_bundles": harmful_bundles,
        "no_added_value_bundles": no_added_value_bundles,
        "total_bundles_evaluated": total_evaluated,
    }


def predict_health_impact(
    candidate_ids: List[str],
    virtual_registry: AdoptionRegistry,
    baseline_score: float,
) -> Dict[str, Any]:
    """Predict health impact of candidate rules.

    Args:
        candidate_ids: List of candidate rule IDs
        virtual_registry: Virtual registry with candidates applied
        baseline_score: Baseline health score before simulation

    Returns:
        Health prediction with:
        - baseline_health_score: float
        - predicted_health_score: float
        - health_drop: float
        - baseline_grade: str
        - predicted_grade: str
    """
    # Compute health with candidates
    health_report = compute_policy_health(virtual_registry)
    predicted_score = health_report.get("health_score", 100)
    
    # Calculate drop
    health_drop = baseline_score - predicted_score
    
    # Get grades
    baseline_grade = _score_to_grade(baseline_score)
    predicted_grade = health_report.get("grade", _score_to_grade(predicted_score))
    
    return {
        "baseline_health_score": baseline_score,
        "predicted_health_score": predicted_score,
        "health_drop": max(0, health_drop),
        "baseline_grade": baseline_grade,
        "predicted_grade": predicted_grade,
        "health_issues": health_report.get("issues", [])[:5],
    }


def predict_governance_risk(
    candidate_ids: List[str],
    virtual_registry: AdoptionRegistry,
) -> Dict[str, Any]:
    """Predict governance risk for candidate rules.

    Args:
        candidate_ids: List of candidate rule IDs
        virtual_registry: Virtual registry with candidates applied

    Returns:
        Governance prediction with:
        - decision_summary: dict of decision counts
        - halt_count: int
        - review_required_count: int
        - auto_promote_count: int
        - candidate_decisions: list of per-candidate decisions
    """
    # Run auto evolution on virtual registry
    evolution_report = run_controlled_auto_evolution(virtual_registry)
    
    # Filter to candidates
    candidate_decisions = []
    for decision in evolution_report.get("auto_evolution", []):
        if decision.get("rule_id") in candidate_ids:
            candidate_decisions.append(decision)
    
    # Count decisions
    halt_count = sum(1 for d in candidate_decisions if d.get("decision") == DECISION_HALT)
    review_count = sum(1 for d in candidate_decisions if d.get("decision") == DECISION_REVIEW_REQUIRED)
    auto_promote_count = sum(1 for d in candidate_decisions if d.get("decision") == DECISION_AUTO_PROMOTE)
    reject_count = sum(1 for d in candidate_decisions if d.get("decision") == DECISION_REJECT)
    rollback_count = sum(1 for d in candidate_decisions if d.get("decision") == DECISION_ROLLBACK_RECOMMENDED)
    
    decision_summary = {
        DECISION_AUTO_PROMOTE: auto_promote_count,
        DECISION_REVIEW_REQUIRED: review_count,
        DECISION_HALT: halt_count,
        DECISION_ROLLBACK_RECOMMENDED: rollback_count,
        DECISION_REJECT: reject_count,
        "total": len(candidate_decisions),
    }
    
    return {
        "decision_summary": decision_summary,
        "halt_count": halt_count,
        "review_required_count": review_count,
        "auto_promote_count": auto_promote_count,
        "candidate_decisions": candidate_decisions,
    }


def _create_virtual_registry(existing_registry: AdoptionRegistry) -> AdoptionRegistry:
    """Create a virtual copy of an existing registry.

    Args:
        existing_registry: Registry to copy

    Returns:
        New AdoptionRegistry with copied entries
    """
    virtual = AdoptionRegistry()
    
    for entry in existing_registry.list_adopted():
        rule_id = entry.get("source_candidate_rule_id")
        if rule_id:
            virtual._adopted[rule_id] = dict(entry)
    
    return virtual


def _score_to_grade(score: float) -> str:
    """Convert health score to grade.

    Args:
        score: Health score (0-100)

    Returns:
        Grade letter (A-F)
    """
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


def get_risk_level(simulation_result: Dict[str, Any]) -> str:
    """Get risk level from simulation result.

    Args:
        simulation_result: Result from simulate_policy_risk()

    Returns:
        Risk level: "low", "medium", or "high"
    """
    return simulation_result.get("risk_level", RISK_HIGH)


def is_high_risk(simulation_result: Dict[str, Any]) -> bool:
    """Check if simulation indicates high risk.

    Args:
        simulation_result: Result from simulate_policy_risk()

    Returns:
        True if high risk
    """
    return simulation_result.get("risk_level") == RISK_HIGH


def export_simulation_result_json(simulation_result: Dict[str, Any]) -> str:
    """Export simulation result as JSON string.

    Args:
        simulation_result: Result from simulate_policy_risk()

    Returns:
        JSON string
    """
    return json.dumps(simulation_result, ensure_ascii=False, indent=2)

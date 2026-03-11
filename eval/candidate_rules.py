#!/usr/bin/env python3
"""Step106/108: Auto-Tuning Candidate Rules + Policy Review Workflow

Step106: Analyzes benchmark diff / regression results and generates candidate
policy adjustment rules for human review. Does NOT modify actual policies.

Step108: Adds review workflow (proposed → reviewed → accepted/rejected)
with review metadata. Still does NOT auto-apply any policy changes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from collections import Counter


# ---------------------------------------------------------------------------
# Candidate rule schema
# ---------------------------------------------------------------------------

def make_candidate(
    candidate_rule_id: str,
    description: str,
    expected_effect: str,
    affected_cases: List[str],
    risk_level: str,  # low / medium / high
    recommendation: str,  # adopt / review / discard
    rule_type: str,  # failed_chain / partial_reinforce / orchestration / tier_threshold / budget_trim
    suggested_change: Dict[str, Any],
) -> Dict[str, Any]:
    """Create a candidate rule dict with initial review state 'proposed'."""
    return {
        "candidate_rule_id": candidate_rule_id,
        "description": description,
        "expected_effect": expected_effect,
        "affected_cases": affected_cases,
        "risk_level": risk_level,
        "recommendation": recommendation,
        "rule_type": rule_type,
        "suggested_change": suggested_change,
        # Step108: Review workflow fields
        "review_status": "proposed",
        "reviewer": None,
        "reviewed_at": None,
        "decision": None,
        "rationale": None,
    }


# ---------------------------------------------------------------------------
# Analyze regression report
# ---------------------------------------------------------------------------

def analyze_regressions(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract patterns from regression details.

    Returns list of pattern dicts with:
      - pattern_type
      - cases
      - field
      - baseline_val
      - latest_val
    """
    patterns: List[Dict[str, Any]] = []

    for rd in report.get("regression_details", []):
        cid = rd.get("case_id", "")
        for diff in rd.get("diffs", []):
            # Parse diff string like "selected_skill: baseline='research', latest='critique'"
            if ":" not in diff:
                continue
            field_part, vals_part = diff.split(":", 1)
            field = field_part.strip()
            # Try to extract baseline and latest values
            baseline_val = None
            latest_val = None
            if "baseline=" in vals_part and "latest=" in vals_part:
                try:
                    b_start = vals_part.index("baseline=") + len("baseline=")
                    b_end = vals_part.index(",", b_start)
                    baseline_val = vals_part[b_start:b_end].strip().strip("'\"")
                    l_start = vals_part.index("latest=") + len("latest=")
                    latest_val = vals_part[l_start:].strip().strip("'\"")
                except (ValueError, IndexError):
                    pass

            patterns.append({
                "pattern_type": "field_regression",
                "case_id": cid,
                "field": field,
                "baseline_val": baseline_val,
                "latest_val": latest_val,
            })

    return patterns


# ---------------------------------------------------------------------------
# Generate candidate rules from patterns
# ---------------------------------------------------------------------------

def generate_candidates(
    patterns: List[Dict[str, Any]],
    harness_summary: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Generate candidate rules from detected patterns.

    Args:
        patterns: Output from analyze_regressions()
        harness_summary: Full harness summary for context (optional)

    Returns:
        List of candidate rule dicts
    """
    candidates: List[Dict[str, Any]] = []
    rule_id = 0

    # Group patterns by field
    field_counts: Dict[str, List[Dict[str, Any]]] = {}
    for p in patterns:
        f = p.get("field", "unknown")
        field_counts.setdefault(f, []).append(p)

    # 1. Failed chain suppression threshold
    if "selected_skill" in field_counts:
        affected = list({p["case_id"] for p in field_counts["selected_skill"]})
        rule_id += 1
        candidates.append(make_candidate(
            candidate_rule_id=f"rule-{rule_id:03d}",
            description="失敗履歴のある skill chain を抑制閾値を下げる",
            expected_effect="高失敗率スキルの選択を回避し、成功率を向上",
            affected_cases=affected,
            risk_level="medium",
            recommendation="review",
            rule_type="failed_chain",
            suggested_change={
                "filter_failed_chains.threshold": 2,  # was 3
            },
        ))

    # 2. Partial reinforcement conditions
    if any(p.get("field") == "skill_chain_length" for p in patterns):
        affected = list({p["case_id"] for p in patterns if p.get("field") == "skill_chain_length"})
        rule_id += 1
        candidates.append(make_candidate(
            candidate_rule_id=f"rule-{rule_id:03d}",
            description="partial 多発時の critique/decision 補強条件を緩和",
            expected_effect="部分失敗時の品質向上フィードバックを強化",
            affected_cases=affected,
            risk_level="low",
            recommendation="adopt",
            rule_type="partial_reinforce",
            suggested_change={
                "reinforce_for_partials.threshold": 1,  # was 2
            },
        ))

    # 3. Orchestration permission conditions
    if "allow_orchestration" in field_counts:
        affected = list({p["case_id"] for p in field_counts["allow_orchestration"]})
        rule_id += 1
        candidates.append(make_candidate(
            candidate_rule_id=f"rule-{rule_id:03d}",
            description="orchestration 許可条件を厳格化",
            expected_effect="予算消費を抑えつつ複雑タスクのみ orchestration",
            affected_cases=affected,
            risk_level="medium",
            recommendation="review",
            rule_type="orchestration",
            suggested_change={
                "should_orchestrate.complexity": "complex",  # require complex
                "should_orchestrate.min_budget_remaining": 3,  # require more budget
            },
        ))

    # 4. Tier thresholds
    if "execution_policy_tier" in field_counts:
        tier_patterns = field_counts["execution_policy_tier"]

        # Count tier drifts
        tier_drifts = Counter()
        for p in tier_patterns:
            tier_drifts[(p.get("baseline_val"), p.get("latest_val"))] += 1

        added_tier_candidate = False

        # If many balanced→cheap drifts, suggest raising cheap threshold
        cheap_drifts = tier_drifts.get(("balanced", "cheap"), 0)
        if cheap_drifts >= 2:
            affected = list({
                p["case_id"] for p in tier_patterns
                if p.get("baseline_val") == "balanced" and p.get("latest_val") == "cheap"
            })
            rule_id += 1
            candidates.append(make_candidate(
                candidate_rule_id=f"rule-{rule_id:03d}",
                description="cheap tier 判定の予算閾値を引き上げ",
                expected_effect="過度な cheap 判定を抑制し品質維持",
                affected_cases=affected,
                risk_level="low",
                recommendation="adopt",
                rule_type="tier_threshold",
                suggested_change={
                    "select_policy_tier.budget_remaining_threshold": 3,  # was 2
                },
            ))
            added_tier_candidate = True

        # Generic fallback: any tier regression should produce at least one candidate
        if not added_tier_candidate and tier_patterns:
            affected = list({p["case_id"] for p in tier_patterns})
            rule_id += 1
            candidates.append(make_candidate(
                candidate_rule_id=f"rule-{rule_id:03d}",
                description="execution policy tier の判定閾値を再調整",
                expected_effect="tier drift を抑制し、cheap / balanced / thorough の選択を安定化",
                affected_cases=affected,
                risk_level="medium",
                recommendation="review",
                rule_type="tier_threshold",
                suggested_change={
                    "select_policy_tier.review_thresholds": True,
                },
            ))

    # 5. Budget trim conditions
    if any("budget" in p.get("field", "") for p in patterns):
        affected = list({p["case_id"] for p in patterns if "budget" in p.get("field", "")})
        rule_id += 1
        candidates.append(make_candidate(
            candidate_rule_id=f"rule-{rule_id:03d}",
            description="budget trim 条件を早期発動",
            expected_effect="予算枯渇前に安全な短縮チェーンへ切り替え",
            affected_cases=affected,
            risk_level="low",
            recommendation="review",
            rule_type="budget_trim",
            suggested_change={
                "trim_chain_for_budget.remaining_threshold": 3,  # was 2
            },
        ))

    return candidates


# ---------------------------------------------------------------------------
# Simulated result summary
# ---------------------------------------------------------------------------

def simulate_effect(
    candidates: List[Dict[str, Any]],
    harness_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate a simulated summary of expected effects.

    This does NOT actually apply rules — it estimates impact.

    Args:
        candidates: List of candidate rules
        harness_summary: Original harness run summary

    Returns:
        Simulated effect summary
    """
    total_cases = harness_summary.get("total", 0)
    affected_set = set()
    for c in candidates:
        affected_set.update(c.get("affected_cases", []))

    return {
        "total_candidates": len(candidates),
        "total_cases_analyzed": total_cases,
        "estimated_affected_cases": len(affected_set),
        "by_risk_level": {
            "low": sum(1 for c in candidates if c.get("risk_level") == "low"),
            "medium": sum(1 for c in candidates if c.get("risk_level") == "medium"),
            "high": sum(1 for c in candidates if c.get("risk_level") == "high"),
        },
        "by_recommendation": {
            "adopt": sum(1 for c in candidates if c.get("recommendation") == "adopt"),
            "review": sum(1 for c in candidates if c.get("recommendation") == "review"),
            "discard": sum(1 for c in candidates if c.get("recommendation") == "discard"),
        },
        "by_rule_type": dict(Counter(c.get("rule_type", "unknown") for c in candidates)),
    }


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def generate_candidate_report(
    regression_report: Dict[str, Any],
    harness_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a full candidate rules report from regression data.

    Args:
        regression_report: Output from compare_snapshots()
        harness_summary: Original harness summary for context

    Returns:
        Full report dict with candidates and simulated summary
    """
    patterns = analyze_regressions(regression_report)
    candidates = generate_candidates(patterns, harness_summary)
    simulation = simulate_effect(candidates, harness_summary or {"total": 0})

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regression_count": regression_report.get("regressions", 0),
        "pattern_count": len(patterns),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "simulation": simulation,
        "note": "This report is advisory only. No policies were modified.",
    }


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def report_to_json(report: Dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)


def report_to_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Auto-Tuning Candidate Rules Report",
        "",
        f"**Generated at:** {report.get('generated_at', 'N/A')}  ",
        f"**Regressions detected:** {report.get('regression_count', 0)}  ",
        f"**Patterns analyzed:** {report.get('pattern_count', 0)}  ",
        f"**Candidates generated:** {report.get('candidate_count', 0)}  ",
        "",
        "> ⚠️ **Note:** This report is advisory only. No policies were modified.",
        "",
    ]

    sim = report.get("simulation", {})
    if sim:
        lines += [
            "## Simulation Summary",
            "",
            f"- **Estimated affected cases:** {sim.get('estimated_affected_cases', 0)}",
            f"- **By risk level:** low={sim.get('by_risk_level', {}).get('low', 0)}, "
            f"medium={sim.get('by_risk_level', {}).get('medium', 0)}, "
            f"high={sim.get('by_risk_level', {}).get('high', 0)}",
            f"- **By recommendation:** adopt={sim.get('by_recommendation', {}).get('adopt', 0)}, "
            f"review={sim.get('by_recommendation', {}).get('review', 0)}, "
            f"discard={sim.get('by_recommendation', {}).get('discard', 0)}",
            "",
        ]

    candidates = report.get("candidates", [])
    if candidates:
        lines += ["## Candidates", ""]
        for c in candidates:
            risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(
                c.get("risk_level", "medium"), "🟡"
            )
            rec_icon = {"adopt": "✅", "review": "🔍", "discard": "❌"}.get(
                c.get("recommendation", "review"), "🔍"
            )
            lines += [
                f"### {risk_icon} {rec_icon} `{c['candidate_rule_id']}` — {c['description']}",
                "",
                f"- **Type:** `{c['rule_type']}`",
                f"- **Risk:** {c['risk_level']}",
                f"- **Recommendation:** {c['recommendation']}",
                f"- **Expected effect:** {c['expected_effect']}",
                f"- **Affected cases:** {', '.join(c['affected_cases'][:5])}"
                + ("..." if len(c['affected_cases']) > 5 else ""),
                f"- **Suggested change:** `{json.dumps(c['suggested_change'])}`",
                "",
            ]
    else:
        lines += ["## Result", "", "No candidate rules generated.", ""]

    return "\n".join(lines)


def save_report(
    report: Dict[str, Any],
    path: Path,
    fmt: str = "json",
) -> None:
    """Save candidate report to disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "markdown":
        path.write_text(report_to_markdown(report), encoding="utf-8")
    else:
        path.write_text(report_to_json(report), encoding="utf-8")


# ---------------------------------------------------------------------------
# Step108: Policy Review Workflow
# ---------------------------------------------------------------------------

REVIEW_STATUS_PROPOSED = "proposed"
REVIEW_STATUS_REVIEWED = "reviewed"
REVIEW_STATUS_ACCEPTED = "accepted"
REVIEW_STATUS_REJECTED = "rejected"

VALID_REVIEW_STATUSES = (
    REVIEW_STATUS_PROPOSED,
    REVIEW_STATUS_REVIEWED,
    REVIEW_STATUS_ACCEPTED,
    REVIEW_STATUS_REJECTED,
)


def review_candidate(
    candidate: Dict[str, Any],
    decision: str,
    reviewer: str,
    rationale: Optional[str] = None,
) -> Dict[str, Any]:
    """Update a candidate with review decision.

    Args:
        candidate: Candidate dict to update
        decision: One of 'accepted', 'rejected', 'reviewed'
        reviewer: Reviewer identifier (e.g., username)
        rationale: Optional reason for the decision

    Returns:
        Updated candidate dict

    Note:
        This does NOT modify any actual policy files.
    """
    if decision not in (REVIEW_STATUS_ACCEPTED, REVIEW_STATUS_REJECTED, REVIEW_STATUS_REVIEWED):
        raise ValueError(f"Invalid decision: {decision}")

    candidate = dict(candidate)
    candidate["review_status"] = decision
    candidate["reviewer"] = reviewer
    candidate["reviewed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidate["decision"] = decision
    candidate["rationale"] = rationale

    return candidate


def batch_review(
    candidates: List[Dict[str, Any]],
    decisions: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Apply review decisions to multiple candidates.

    Args:
        candidates: List of candidate dicts
        decisions: Dict mapping candidate_rule_id to
                   {"decision": str, "reviewer": str, "rationale": str}

    Returns:
        List of updated candidates
    """
    updated = []
    for c in candidates:
        cid = c.get("candidate_rule_id")
        if cid in decisions:
            d = decisions[cid]
            c = review_candidate(
                c,
                decision=d.get("decision", REVIEW_STATUS_REVIEWED),
                reviewer=d.get("reviewer", "unknown"),
                rationale=d.get("rationale"),
            )
        updated.append(c)
    return updated


def summarize_reviews(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate a summary of review status across all candidates.

    Args:
        candidates: List of candidate dicts (may have been reviewed)

    Returns:
        Summary dict with counts by status
    """
    total = len(candidates)
    by_status = {
        REVIEW_STATUS_PROPOSED: 0,
        REVIEW_STATUS_REVIEWED: 0,
        REVIEW_STATUS_ACCEPTED: 0,
        REVIEW_STATUS_REJECTED: 0,
    }
    by_risk_accepted = {"low": 0, "medium": 0, "high": 0}

    for c in candidates:
        status = c.get("review_status", REVIEW_STATUS_PROPOSED)
        if status in by_status:
            by_status[status] += 1
        if status == REVIEW_STATUS_ACCEPTED:
            risk = c.get("risk_level", "medium")
            if risk in by_risk_accepted:
                by_risk_accepted[risk] += 1

    return {
        "total": total,
        "by_status": by_status,
        "by_risk_accepted": by_risk_accepted,
        "pending": by_status[REVIEW_STATUS_PROPOSED],
        "completed": by_status[REVIEW_STATUS_ACCEPTED] + by_status[REVIEW_STATUS_REJECTED],
    }


def export_review_report(
    candidates: List[Dict[str, Any]],
    fmt: str = "json",
) -> str:
    """Export a review report in JSON or Markdown format.

    Args:
        candidates: List of candidate dicts
        fmt: 'json' or 'markdown'

    Returns:
        Report string
    """
    summary = summarize_reviews(candidates)

    if fmt == "markdown":
        lines = [
            "# Policy Review Report",
            "",
            f"**Total candidates:** {summary['total']}  ",
            f"**Pending:** {summary['pending']}  ",
            f"**Completed:** {summary['completed']}  ",
            "",
            "## Status Breakdown",
            "",
            f"- Proposed: {summary['by_status']['proposed']}",
            f"- Reviewed: {summary['by_status']['reviewed']}",
            f"- Accepted: {summary['by_status']['accepted']}",
            f"- Rejected: {summary['by_status']['rejected']}",
            "",
        ]

        if candidates:
            lines += ["## Candidates", ""]
            for c in candidates:
                status_icon = {
                    "proposed": "⏳",
                    "reviewed": "🔍",
                    "accepted": "✅",
                    "rejected": "❌",
                }.get(c.get("review_status", "proposed"), "❓")

                lines += [
                    f"### {status_icon} `{c['candidate_rule_id']}` — {c['description']}",
                    f"- **Status:** {c.get('review_status', 'proposed')}",
                    f"- **Risk:** {c.get('risk_level', 'unknown')}",
                ]
                if c.get("reviewer"):
                    lines += [
                        f"- **Reviewer:** {c['reviewer']}",
                        f"- **Reviewed at:** {c.get('reviewed_at', 'N/A')}",
                    ]
                if c.get("rationale"):
                    lines += [f"- **Rationale:** {c['rationale']}"]
                lines.append("")

        return "\n".join(lines)

    return json.dumps({
        "summary": summary,
        "candidates": candidates,
        "note": "This report is advisory only. No policies were modified.",
    }, ensure_ascii=False, indent=2)


def save_review_report(
    candidates: List[Dict[str, Any]],
    path: Path,
    fmt: str = "json",
) -> None:
    """Save a review report to disk.

    Args:
        candidates: List of candidate dicts
        path: Output file path
        fmt: 'json' or 'markdown'
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(export_review_report(candidates, fmt), encoding="utf-8")


# ---------------------------------------------------------------------------
# Step109/110: Controlled Rule Adoption + Rollback
# ---------------------------------------------------------------------------

ADOPTION_STATUS_ADOPTED = "adopted"
ADOPTION_STATUS_INACTIVE = "inactive"
ADOPTION_STATUS_ROLLED_BACK = "rolled_back"

VALID_ADOPTION_STATUSES = (
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_INACTIVE,
    ADOPTION_STATUS_ROLLED_BACK,
)


class AdoptionRegistry:
    """Registry for controlled adoption of accepted candidate rules.

    Does NOT automatically modify any production policy files.
    Tracks adoption status and supports rollback preparation.
    """

    def __init__(self):
        self._adopted: Dict[str, Dict[str, Any]] = {}

    def adopt(
        self,
        candidate: Dict[str, Any],
        adopted_by: str,
        notes: Optional[str] = None,
        provenance: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Adopt an accepted candidate rule into the registry.

        Args:
            candidate: Candidate dict (must have review_status='accepted')
            adopted_by: Who approved the adoption
            notes: Optional notes
            provenance: Optional provenance metadata (Step114)

        Returns:
            Adoption entry dict

        Raises:
            ValueError: If candidate is not accepted
        """
        if candidate.get("review_status") != REVIEW_STATUS_ACCEPTED:
            raise ValueError(
                f"Only accepted candidates can be adopted. "
                f"Status: {candidate.get('review_status')}"
            )

        rule_id = candidate.get("candidate_rule_id")

        # Step114: Create provenance if not provided
        if provenance is None:
            provenance = make_provenance(
                rule_id=rule_id,
                source_candidate_rule_id=rule_id,
                source_regression_case_ids=candidate.get("affected_cases", []),
                created_by="adoption",
            )

        entry = {
            "source_candidate_rule_id": rule_id,
            "adoption_status": ADOPTION_STATUS_ADOPTED,
            "adopted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "adopted_by": adopted_by,
            "notes": notes,
            "rule_type": candidate.get("rule_type"),
            "suggested_change": candidate.get("suggested_change"),
            "risk_level": candidate.get("risk_level"),
            "rollback_info": {
                "previous_state": None,
                "can_rollback": True,
            },
            # Step114: Provenance
            "provenance": provenance,
        }
        self._adopted[rule_id] = entry
        return entry

    def deactivate(self, rule_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """Mark an adopted rule as inactive (deactivated but not removed).

        Args:
            rule_id: Candidate rule ID to deactivate
            reason: Optional reason for deactivation

        Returns:
            Updated entry

        Raises:
            KeyError: If rule_id not in registry
        """
        if rule_id not in self._adopted:
            raise KeyError(f"Rule not in adoption registry: {rule_id}")

        entry = dict(self._adopted[rule_id])
        entry["adoption_status"] = ADOPTION_STATUS_INACTIVE
        entry["deactivated_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        entry["deactivation_reason"] = reason
        self._adopted[rule_id] = entry
        return entry

    def reactivate(self, rule_id: str) -> Dict[str, Any]:
        """Reactivate an inactive rule.

        Args:
            rule_id: Candidate rule ID to reactivate

        Returns:
            Updated entry
        """
        if rule_id not in self._adopted:
            raise KeyError(f"Rule not in adoption registry: {rule_id}")

        entry = dict(self._adopted[rule_id])
        entry["adoption_status"] = ADOPTION_STATUS_ADOPTED
        entry["reactivated_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self._adopted[rule_id] = entry
        return entry

    def rollback(
        self,
        rule_id: str,
        rolled_back_by: str,
        reason: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Rollback an adopted rule.

        Only rules in 'adopted' status can be rolled back.
        This is distinct from deactivate — it implies the rule was actively
        applied and needs to be reverted.

        Args:
            rule_id: Candidate rule ID to rollback
            rolled_back_by: Who initiated the rollback
            reason: Required reason for the rollback
            notes: Optional additional notes

        Returns:
            Updated entry with rollback metadata

        Raises:
            KeyError: If rule_id not in registry
            ValueError: If rule is not in 'adopted' status
        """
        if rule_id not in self._adopted:
            raise KeyError(f"Rule not in adoption registry: {rule_id}")

        entry = self._adopted[rule_id]
        if entry.get("adoption_status") != ADOPTION_STATUS_ADOPTED:
            raise ValueError(
                f"Only adopted rules can be rolled back. "
                f"Current status: {entry.get('adoption_status')}"
            )

        entry = dict(entry)
        entry["adoption_status"] = ADOPTION_STATUS_ROLLED_BACK
        entry["rolled_back_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        entry["rolled_back_by"] = rolled_back_by
        entry["rollback_reason"] = reason
        entry["rollback_notes"] = notes

        # Update rollback_info
        entry["rollback_info"] = {
            "previous_state": ADOPTION_STATUS_ADOPTED,
            "can_rollback": False,
            "rolled_back": True,
        }

        self._adopted[rule_id] = entry
        return entry

    def can_rollback(self, rule_id: str) -> bool:
        """Check if a rule can be rolled back.

        Args:
            rule_id: Candidate rule ID

        Returns:
            True if the rule can be rolled back
        """
        entry = self._adopted.get(rule_id)
        if not entry:
            return False
        return entry.get("adoption_status") == ADOPTION_STATUS_ADOPTED

    def get(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Get an adoption entry by rule ID."""
        return self._adopted.get(rule_id)

    def list_adopted(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all adopted rules, optionally filtered by status."""
        entries = list(self._adopted.values())
        if status:
            entries = [e for e in entries if e.get("adoption_status") == status]
        return entries

    def summarize(self) -> Dict[str, Any]:
        """Summarize the adoption registry."""
        total = len(self._adopted)
        by_status = {
            ADOPTION_STATUS_ADOPTED: 0,
            ADOPTION_STATUS_INACTIVE: 0,
            ADOPTION_STATUS_ROLLED_BACK: 0,
        }
        by_risk = {"low": 0, "medium": 0, "high": 0}

        for entry in self._adopted.values():
            s = entry.get("adoption_status")
            if s in by_status:
                by_status[s] += 1
            r = entry.get("risk_level")
            if r in by_risk:
                by_risk[r] += 1

        # Step114: Include provenance summary
        provenance_summary = summarize_provenance(list(self._adopted.values()))

        return {
            "total": total,
            "by_status": by_status,
            "by_risk": by_risk,
            "rollback_count": by_status[ADOPTION_STATUS_ROLLED_BACK],
            "provenance": provenance_summary,
        }

    def get_conflicts(
        self,
        promotion_manager: Optional[PromotionManager] = None,
    ) -> Dict[str, Any]:
        """Get conflict report for all rules in this registry.

        Args:
            promotion_manager: Optional PromotionManager for promotion info

        Returns:
            Conflict report dict with conflicts and summary
        """
        return build_conflict_report(self, promotion_manager)

    def get_bundle_evaluation(
        self,
        rule_ids: List[str],
        individual_results: Optional[Dict[str, float]] = None,
        promotion_manager: Optional[PromotionManager] = None,
    ) -> Dict[str, Any]:
        """Evaluate a bundle of rules together.

        Args:
            rule_ids: List of rule IDs to evaluate as a bundle
            individual_results: Optional pre-computed individual results
            promotion_manager: Optional PromotionManager for conflict context

        Returns:
            Bundle evaluation dict
        """
        return evaluate_rule_bundle(rule_ids, self, individual_results, promotion_manager)

    def get_health_score(
        self,
        promotion_manager: Optional[PromotionManager] = None,
    ) -> Dict[str, Any]:
        """Get policy health report for this registry.

        Args:
            promotion_manager: Optional PromotionManager for bundle context

        Returns:
            Health report dict with health_score, grade, breakdown, issues, summary
        """
        return compute_policy_health(self, promotion_manager)

    def get_lineage_graph(
        self,
        promotion_manager: Optional[PromotionManager] = None,
    ) -> Dict[str, Any]:
        """Get the lineage graph for all rules in this registry.

        Args:
            promotion_manager: Optional PromotionManager for promotion info

        Returns:
            Lineage graph dict with nodes, edges, roots, summary
        """
        return build_policy_lineage_graph(self, promotion_manager)

    def get_evolution_summary(
        self,
        promotion_manager: Optional[PromotionManager] = None,
    ) -> Dict[str, Any]:
        """Get the evolution summary for all rules in this registry.

        Args:
            promotion_manager: Optional PromotionManager for promotion info

        Returns:
            Evolution summary dict with lineage_graph, evolution_metrics, rollback_history
        """
        return get_policy_evolution_summary(self, promotion_manager)

    def get_review_queue(
        self,
        promotion_manager: Optional[PromotionManager] = None,
    ) -> Dict[str, Any]:
        """Get the prioritized review queue for all rules in this registry.

        Args:
            promotion_manager: Optional PromotionManager for additional context

        Returns:
            Review queue dict with review_queue and summary
        """
        return build_review_queue(self, promotion_manager)

    def get_auto_evolution_decision(
        self,
        rule_ids: Optional[List[str]] = None,
        promotion_manager: Optional[PromotionManager] = None,
    ) -> Dict[str, Any]:
        """Get controlled auto-evolution decisions for rules.

        Args:
            rule_ids: Optional list of rule IDs to evaluate. If None, evaluates all.
            promotion_manager: Optional PromotionManager for additional context

        Returns:
            Auto-evolution report dict with auto_evolution and summary
        """
        return run_controlled_auto_evolution(self, rule_ids, promotion_manager)

    def get_decision_explanation(
        self,
        rule_ids: Optional[List[str]] = None,
        promotion_manager: Optional[PromotionManager] = None,
    ) -> Dict[str, Any]:
        """Get explainable decision reports for rules.

        Args:
            rule_ids: Optional list of rule IDs to explain. If None, explains all.
            promotion_manager: Optional PromotionManager for additional context

        Returns:
            Explanation report dict with explanations and summary
        """
        return build_explainable_decision_report(self, rule_ids, promotion_manager)

    def get_governance_policy(self) -> Dict[str, Any]:
        """Get operational governance policy definitions.

        Returns:
            Governance policy dict with roles, guardrails, and metrics
        """
        return build_operational_governance_policy()

    def compute_operational_metrics(self) -> Dict[str, Any]:
        """Compute actual operational metrics from registry state.

        Returns:
            Metrics report dict with computed values
        """
        return compute_operational_metrics_report(self)

    def export(self, fmt: str = "json", include_lineage: bool = False, include_conflicts: bool = False, include_bundle_eval: bool = False, include_health: bool = False, include_review_queue: bool = False, include_auto_evolution: bool = False, include_explanations: bool = False, include_governance: bool = False, bundle_rule_ids: Optional[List[str]] = None, rule_ids_for_evolution: Optional[List[str]] = None, rule_ids_for_explanations: Optional[List[str]] = None, promotion_manager: Optional[PromotionManager] = None) -> str:
        """Export the registry in JSON or Markdown format.

        Args:
            fmt: 'json' or 'markdown'
            include_lineage: Whether to include lineage graph (Step115)
            include_conflicts: Whether to include conflict report (Step116)
            include_bundle_eval: Whether to include bundle evaluation (Step117)
            include_health: Whether to include health score (Step118)
            include_review_queue: Whether to include review queue (Step119)
            include_auto_evolution: Whether to include auto-evolution decisions (Step120)
            include_explanations: Whether to include explainable decision reports (Step122)
            include_governance: Whether to include operational governance policy (Step123)
            bundle_rule_ids: Rule IDs to evaluate as bundle (required if include_bundle_eval)
            rule_ids_for_evolution: Rule IDs to evaluate for auto-evolution (optional)
            rule_ids_for_explanations: Rule IDs to explain (optional)
            promotion_manager: Optional PromotionManager for lineage and conflict info

        Returns:
            Exported string
        """
        summary = self.summarize()

        if fmt == "markdown":
            lines = [
                "# Adoption Registry",
                "",
                f"**Total adopted:** {summary['total']}  ",
                f"**Active:** {summary['by_status']['adopted']}  ",
                f"**Inactive:** {summary['by_status']['inactive']}  ",
                f"**Rolled back:** {summary['by_status']['rolled_back']}  ",
                "",
            ]

            # Step114: Provenance summary
            prov = summary.get("provenance", {})
            if prov:
                lines += [
                    "## Provenance Summary",
                    "",
                    f"- **With provenance:** {prov.get('with_provenance', 0)}",
                    f"- **With parent:** {prov.get('with_parent', 0)}",
                    f"- **Unique regression cases:** {prov.get('unique_regression_case_count', 0)}",
                    f"- **Unique scenario packs:** {prov.get('unique_scenario_pack_count', 0)}",
                    "",
                ]

            # Step115: Lineage tree
            if include_lineage:
                lines += ["## Policy Lineage", ""]
                tree = render_policy_lineage_tree(self, promotion_manager, include_provenance=False)
                # Remove the header from tree since we already added one
                tree_lines = tree.split("\n")
                # Skip the first line (header) if present
                if tree_lines and tree_lines[0].startswith("# "):
                    tree_lines = tree_lines[1:]
                lines += tree_lines
                lines.append("")

            # Step116: Conflict report
            if include_conflicts:
                conflict_report = self.get_conflicts(promotion_manager)
                lines += ["## Conflict Report", ""]
                cs = conflict_report.get("summary", {})
                lines += [
                    f"- **Total conflicts:** {cs.get('total_conflicts', 0)}",
                    f"- **High severity:** {cs.get('high_severity', 0)}",
                    f"- **Has critical conflicts:** {cs.get('has_critical_conflicts', False)}",
                    "",
                ]
                conflicts = conflict_report.get("conflicts", [])
                if conflicts:
                    lines += ["### Detected Conflicts", ""]
                    for conflict in conflicts:
                        icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                            conflict.get("severity", "medium"), "❓"
                        )
                        lines += [
                            f"#### {icon} {conflict.get('type', 'unknown')}",
                            f"- **Rule IDs:** {', '.join(conflict.get('rule_ids', []))}",
                            f"- **Severity:** {conflict.get('severity', 'medium')}",
                            f"- **Reason:** {conflict.get('reason', 'N/A')}",
                            "",
                        ]
                else:
                    lines += ["_No conflicts detected._", ""]

            lines += ["## Entries", ""]

            for entry in self._adopted.values():
                status_icon = {
                    "adopted": "✅",
                    "inactive": "⏸️",
                    "rolled_back": "↩️",
                }.get(entry["adoption_status"], "❓")
                lines += [
                    f"### {status_icon} `{entry['source_candidate_rule_id']}`",
                    f"- **Status:** {entry['adoption_status']}",
                    f"- **Adopted by:** {entry.get('adopted_by', 'unknown')}",
                    f"- **Adopted at:** {entry.get('adopted_at', 'N/A')}",
                    f"- **Risk:** {entry.get('risk_level', 'unknown')}",
                ]
                if entry.get("notes"):
                    lines += [f"- **Notes:** {entry['notes']}"]

                # Step114: Provenance details
                prov = entry.get("provenance")
                if prov:
                    lines += [f"- **Version:** {prov.get('rule_version', 1)}"]
                    if prov.get("parent_rule_id"):
                        lines += [f"- **Parent:** `{prov['parent_rule_id']}`"]
                    if prov.get("source_regression_case_ids"):
                        lines += [f"- **Source cases:** {', '.join(prov['source_regression_case_ids'][:3])}"]
                    if prov.get("source_scenario_packs"):
                        lines += [f"- **Scenario packs:** {', '.join(prov['source_scenario_packs'][:3])}"]

                if entry.get("adoption_status") == ADOPTION_STATUS_ROLLED_BACK:
                    lines += [
                        f"- **Rolled back at:** {entry.get('rolled_back_at', 'N/A')}",
                        f"- **Rolled back by:** {entry.get('rolled_back_by', 'unknown')}",
                        f"- **Rollback reason:** {entry.get('rollback_reason', 'N/A')}",
                    ]
                    if entry.get("rollback_notes"):
                        lines += [f"- **Rollback notes:** {entry['rollback_notes']}"]
                lines.append("")

            lines += [
                "---",
                "",
                "> Note: This registry is for controlled adoption tracking only.",
                "> No production policies are automatically modified.",
            ]
            return "\n".join(lines)

        # JSON export
        result = {
            "summary": summary,
            "entries": list(self._adopted.values()),
            "note": "Controlled adoption registry. No automatic policy modifications.",
        }

        # Step115: Include lineage graph if requested
        if include_lineage:
            result["lineage"] = self.get_lineage_graph(promotion_manager)

        # Step116: Include conflict report if requested
        if include_conflicts:
            result["conflicts"] = self.get_conflicts(promotion_manager)

        # Step117: Include bundle evaluation if requested
        if include_bundle_eval and bundle_rule_ids:
            result["bundle_evaluation"] = self.get_bundle_evaluation(
                bundle_rule_ids, None, promotion_manager
            )

        # Step118: Include health score if requested
        if include_health:
            result["health"] = self.get_health_score(promotion_manager)

        # Step119: Include review queue if requested
        if include_review_queue:
            result["review_queue"] = self.get_review_queue(promotion_manager)

        # Step120: Include auto-evolution decisions if requested
        if include_auto_evolution:
            result["auto_evolution"] = self.get_auto_evolution_decision(
                rule_ids_for_evolution, promotion_manager
            )

        # Step122: Include explainable decision reports if requested
        if include_explanations:
            result["explanations"] = self.get_decision_explanation(
                rule_ids_for_explanations, promotion_manager
            )

        # Step123: Include operational governance policy if requested
        if include_governance:
            result["governance"] = self.get_governance_policy()
            result["operational_metrics"] = self.compute_operational_metrics()

        return json.dumps(result, ensure_ascii=False, indent=2)

    def save(self, path: Path, fmt: str = "json") -> None:
        """Save the registry to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.export(fmt), encoding="utf-8")

    def load(self, path: Path) -> None:
        """Load registry from a JSON file."""
        path = Path(path)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        for entry in data.get("entries", []):
            rule_id = entry.get("source_candidate_rule_id")
            if rule_id:
                self._adopted[rule_id] = entry


# Convenience functions for direct use without class

def create_adoption_registry() -> AdoptionRegistry:
    """Create a new empty adoption registry."""
    return AdoptionRegistry()


def can_adopt(candidate: Dict[str, Any]) -> bool:
    """Check if a candidate is eligible for adoption."""
    return candidate.get("review_status") == REVIEW_STATUS_ACCEPTED


# ---------------------------------------------------------------------------
# Step111: Shadow Evaluation for Adopted Rules
# ---------------------------------------------------------------------------

def can_shadow_evaluate(entry: Dict[str, Any]) -> bool:
    """Check if an adoption entry is eligible for shadow evaluation.

    Only 'adopted' status entries can be shadow evaluated.
    """
    return entry.get("adoption_status") == ADOPTION_STATUS_ADOPTED


def compare_shadow_vs_baseline(
    baseline_summary: Dict[str, Any],
    shadow_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare shadow evaluation results against baseline.

    Args:
        baseline_summary: Harness summary with baseline policy
        shadow_summary: Harness summary with shadow (candidate) policy

    Returns:
        Comparison result with changed_cases, regressions, improvements, neutral_cases
    """
    baseline_cases = {c["case_id"]: c for c in baseline_summary.get("cases", [])}
    shadow_cases = {c["case_id"]: c for c in shadow_summary.get("cases", [])}

    changed_cases: List[Dict[str, Any]] = []
    regressions: List[Dict[str, Any]] = []
    improvements: List[Dict[str, Any]] = []
    neutral_cases: List[str] = []

    all_ids = set(baseline_cases) | set(shadow_cases)

    for cid in sorted(all_ids):
        base = baseline_cases.get(cid, {})
        shadow = shadow_cases.get(cid, {})

        base_result = base.get("result", {})
        shadow_result = shadow.get("result", {})

        # Compare key fields
        diffs = []
        is_regression = False
        is_improvement = False

        for field in ("execution_policy_tier", "allow_orchestration", "selected_skill"):
            b_val = base_result.get(field)
            s_val = shadow_result.get(field)
            if b_val != s_val:
                diffs.append({
                    "field": field,
                    "baseline": b_val,
                    "shadow": s_val,
                })
                # Heuristic: tier downgrade = regression, upgrade = improvement
                if field == "execution_policy_tier":
                    tier_order = {"cheap": 0, "balanced": 1, "thorough": 2}
                    b_tier = tier_order.get(b_val, 1)
                    s_tier = tier_order.get(s_val, 1)
                    if s_tier < b_tier:
                        is_regression = True
                    elif s_tier > b_tier:
                        is_improvement = True
                elif field == "allow_orchestration":
                    if b_val and not s_val:
                        is_regression = True
                    elif not b_val and s_val:
                        is_improvement = True

        if diffs:
            changed_case = {
                "case_id": cid,
                "diffs": diffs,
                "is_regression": is_regression,
                "is_improvement": is_improvement,
            }
            changed_cases.append(changed_case)
            if is_regression and not is_improvement:
                regressions.append(changed_case)
            elif is_improvement and not is_regression:
                improvements.append(changed_case)
        else:
            neutral_cases.append(cid)

    return {
        "total_baseline": len(baseline_cases),
        "total_shadow": len(shadow_cases),
        "changed_count": len(changed_cases),
        "regression_count": len(regressions),
        "improvement_count": len(improvements),
        "neutral_count": len(neutral_cases),
        "changed_cases": changed_cases,
        "regressions": regressions,
        "improvements": improvements,
        "neutral_cases": neutral_cases,
        "ok": len(regressions) == 0,
    }


class ShadowEvaluator:
    """Shadow evaluation for adopted rules before production activation.

    Compares baseline policy results against shadow (with adopted rule) results.
    Does NOT modify any production policies.
    """

    def __init__(self, registry: AdoptionRegistry):
        self.registry = registry
        self._shadow_results: Dict[str, Dict[str, Any]] = {}

    def evaluate(
        self,
        rule_id: str,
        baseline_summary: Dict[str, Any],
        shadow_summary: Dict[str, Any],
        shadowed_by: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run shadow evaluation for an adopted rule.

        Args:
            rule_id: Candidate rule ID to evaluate
            baseline_summary: Harness results with baseline policy
            shadow_summary: Harness results with shadow policy
            shadowed_by: Who ran the shadow evaluation
            notes: Optional notes

        Returns:
            Shadow evaluation result

        Raises:
            ValueError: If rule is not in 'adopted' status
            KeyError: If rule not in registry
        """
        entry = self.registry.get(rule_id)
        if not entry:
            raise KeyError(f"Rule not in adoption registry: {rule_id}")

        if not can_shadow_evaluate(entry):
            raise ValueError(
                f"Only adopted rules can be shadow evaluated. "
                f"Status: {entry.get('adoption_status')}"
            )

        comparison = compare_shadow_vs_baseline(baseline_summary, shadow_summary)

        result = {
            "source_candidate_rule_id": rule_id,
            "shadowed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "shadowed_by": shadowed_by,
            "compared_against_baseline": True,
            "notes": notes,
            "comparison": comparison,
        }

        self._shadow_results[rule_id] = result
        return result

    def get(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Get shadow evaluation result for a rule."""
        return self._shadow_results.get(rule_id)

    def list_evaluated(self) -> List[Dict[str, Any]]:
        """List all shadow evaluation results."""
        return list(self._shadow_results.values())

    def summarize(self) -> Dict[str, Any]:
        """Summarize all shadow evaluations."""
        total = len(self._shadow_results)
        regressions = sum(
            1 for r in self._shadow_results.values()
            if r.get("comparison", {}).get("regression_count", 0) > 0
        )
        improvements = sum(
            1 for r in self._shadow_results.values()
            if r.get("comparison", {}).get("improvement_count", 0) > 0
        )
        all_ok = all(
            r.get("comparison", {}).get("ok", True)
            for r in self._shadow_results.values()
        )

        return {
            "total_evaluated": total,
            "with_regressions": regressions,
            "with_improvements": improvements,
            "all_ok": all_ok,
        }

    def export(self, fmt: str = "json") -> str:
        """Export shadow evaluation results."""
        summary = self.summarize()

        if fmt == "markdown":
            lines = [
                "# Shadow Evaluation Report",
                "",
                f"**Total evaluated:** {summary['total_evaluated']}  ",
                f"**With regressions:** {summary['with_regressions']}  ",
                f"**With improvements:** {summary['with_improvements']}  ",
                f"**All OK:** {'✅ Yes' if summary['all_ok'] else '❌ No'}  ",
                "",
            ]

            for result in self._shadow_results.values():
                comp = result.get("comparison", {})
                status_icon = "✅" if comp.get("ok", True) else "⚠️"
                lines += [
                    f"## {status_icon} `{result['source_candidate_rule_id']}`",
                    f"- **Shadowed at:** {result.get('shadowed_at', 'N/A')}",
                    f"- **Shadowed by:** {result.get('shadowed_by', 'unknown')}",
                    f"- **Changed cases:** {comp.get('changed_count', 0)}",
                    f"- **Regressions:** {comp.get('regression_count', 0)}",
                    f"- **Improvements:** {comp.get('improvement_count', 0)}",
                ]
                if result.get("notes"):
                    lines += [f"- **Notes:** {result['notes']}"]

                if comp.get("regressions"):
                    lines += ["", "### Regressions", ""]
                    for rc in comp["regressions"]:
                        lines += [f"- `{rc['case_id']}`: {rc['diffs']}"]

                if comp.get("improvements"):
                    lines += ["", "### Improvements", ""]
                    for ic in comp["improvements"]:
                        lines += [f"- `{ic['case_id']}`: {ic['diffs']}"]

                lines.append("")

            lines += [
                "---",
                "",
                "> Note: Shadow evaluation does not modify production policies.",
            ]
            return "\n".join(lines)

        return json.dumps({
            "summary": summary,
            "results": list(self._shadow_results.values()),
            "note": "Shadow evaluation does not modify production policies.",
        }, ensure_ascii=False, indent=2)

    def save(self, path: Path, fmt: str = "json") -> None:
        """Save shadow evaluation results to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.export(fmt), encoding="utf-8")

    def load(self, path: Path) -> None:
        """Load shadow evaluation results from a JSON file."""
        path = Path(path)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        for result in data.get("results", []):
            rule_id = result.get("source_candidate_rule_id")
            if rule_id:
                self._shadow_results[rule_id] = result


def create_shadow_evaluator(registry: AdoptionRegistry) -> ShadowEvaluator:
    """Create a shadow evaluator for the given registry."""
    return ShadowEvaluator(registry)


# ---------------------------------------------------------------------------
# Step112: Gated Promotion Workflow
# ---------------------------------------------------------------------------

PROMOTION_STATUS_ELIGIBLE = "eligible_for_promotion"
PROMOTION_STATUS_PROMOTED = "promoted"
PROMOTION_STATUS_BLOCKED = "blocked"

VALID_PROMOTION_STATUSES = (
    PROMOTION_STATUS_ELIGIBLE,
    PROMOTION_STATUS_PROMOTED,
    PROMOTION_STATUS_BLOCKED,
)

# Default gate conditions
DEFAULT_MAX_REGRESSIONS = 0
DEFAULT_MIN_IMPROVEMENTS = 1


def can_promote(shadow_result: Dict[str, Any]) -> bool:
    """Check if a shadow evaluation result is eligible for promotion.

    A rule can be promoted only if:
    - It has been shadow evaluated
    - It is not already promoted or blocked

    Args:
        shadow_result: Shadow evaluation result from ShadowEvaluator

    Returns:
        True if the rule can be promoted
    """
    if not shadow_result:
        return False
    promo_status = shadow_result.get("promotion_status")
    return promo_status is None or promo_status == PROMOTION_STATUS_ELIGIBLE


def evaluate_promotion_gates(
    shadow_result: Dict[str, Any],
    max_regressions: int = DEFAULT_MAX_REGRESSIONS,
    min_improvements: int = DEFAULT_MIN_IMPROVEMENTS,
) -> Dict[str, Any]:
    """Evaluate gate conditions for promotion.

    Args:
        shadow_result: Shadow evaluation result from ShadowEvaluator
        max_regressions: Maximum allowed regressions (default 0)
        min_improvements: Minimum required improvements (default 1)

    Returns:
        Gate evaluation result with:
        - passed: bool
        - promotion_status: eligible_for_promotion | blocked
        - gate_results: dict with individual gate checks
        - gate_config: dict with gate parameters used
    """
    comparison = shadow_result.get("comparison", {})
    regression_count = comparison.get("regression_count", 0)
    improvement_count = comparison.get("improvement_count", 0)

    # Check individual gates
    regressions_ok = regression_count <= max_regressions
    improvements_ok = improvement_count >= min_improvements

    passed = regressions_ok and improvements_ok

    if passed:
        promotion_status = PROMOTION_STATUS_ELIGIBLE
    else:
        promotion_status = PROMOTION_STATUS_BLOCKED

    return {
        "passed": passed,
        "promotion_status": promotion_status,
        "gate_results": {
            "regressions_ok": regressions_ok,
            "improvements_ok": improvements_ok,
        },
        "gate_config": {
            "max_regressions": max_regressions,
            "min_improvements": min_improvements,
            "actual_regressions": regression_count,
            "actual_improvements": improvement_count,
        },
    }


class PromotionManager:
    """Manages gated promotion workflow for shadow-evaluated rules.

    Does NOT modify any production policies.
    """

    def __init__(
        self,
        shadow_evaluator: ShadowEvaluator,
        max_regressions: int = DEFAULT_MAX_REGRESSIONS,
        min_improvements: int = DEFAULT_MIN_IMPROVEMENTS,
    ):
        self.shadow_evaluator = shadow_evaluator
        self.max_regressions = max_regressions
        self.min_improvements = min_improvements
        self._promotion_records: Dict[str, Dict[str, Any]] = {}

    def evaluate_for_promotion(
        self,
        rule_id: str,
        max_regressions: Optional[int] = None,
        min_improvements: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Evaluate a rule's eligibility for promotion.

        Args:
            rule_id: Candidate rule ID to evaluate
            max_regressions: Override max regressions (optional)
            min_improvements: Override min improvements (optional)

        Returns:
            Promotion evaluation result

        Raises:
            KeyError: If rule has not been shadow evaluated
        """
        shadow_result = self.shadow_evaluator.get(rule_id)
        if not shadow_result:
            raise KeyError(
                f"Rule has not been shadow evaluated: {rule_id}. "
                f"Only shadow-evaluated rules can be evaluated for promotion."
            )

        max_reg = max_regressions if max_regressions is not None else self.max_regressions
        min_imp = min_improvements if min_improvements is not None else self.min_improvements

        gate_result = evaluate_promotion_gates(
            shadow_result,
            max_regressions=max_reg,
            min_improvements=min_imp,
        )

        # Update shadow result with promotion status
        shadow_result["promotion_status"] = gate_result["promotion_status"]
        shadow_result["gate_evaluation"] = gate_result

        return gate_result

    def promote(
        self,
        rule_id: str,
        promoted_by: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Promote a rule to 'promoted' status.

        Args:
            rule_id: Candidate rule ID to promote
            promoted_by: Who approved the promotion
            reason: Optional reason for promotion

        Returns:
            Promotion record

        Raises:
            KeyError: If rule has not been shadow evaluated
            ValueError: If rule is not eligible for promotion
        """
        shadow_result = self.shadow_evaluator.get(rule_id)
        if not shadow_result:
            raise KeyError(
                f"Rule has not been shadow evaluated: {rule_id}. "
                f"Only shadow-evaluated rules can be promoted."
            )

        # Check current promotion status
        promo_status = shadow_result.get("promotion_status")
        if promo_status == PROMOTION_STATUS_PROMOTED:
            raise ValueError(f"Rule is already promoted: {rule_id}")

        if promo_status == PROMOTION_STATUS_BLOCKED:
            raise ValueError(
                f"Rule is blocked from promotion: {rule_id}. "
                f"Gate conditions not met."
            )

        # If not yet evaluated, evaluate now
        if promo_status is None or promo_status == PROMOTION_STATUS_ELIGIBLE:
            gate_result = self.evaluate_for_promotion(rule_id)
            if not gate_result["passed"]:
                raise ValueError(
                    f"Rule is blocked from promotion: {rule_id}. "
                    f"Gate conditions not met."
                )

        # Create promotion record
        record = {
            "source_candidate_rule_id": rule_id,
            "promotion_status": PROMOTION_STATUS_PROMOTED,
            "promoted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "promoted_by": promoted_by,
            "promotion_reason": reason,
            "gate_evaluation": shadow_result.get("gate_evaluation"),
            "shadow_evaluation": shadow_result.get("comparison"),
        }

        # Update shadow result
        shadow_result["promotion_status"] = PROMOTION_STATUS_PROMOTED
        shadow_result["promotion_record"] = record

        self._promotion_records[rule_id] = record
        return record

    def block(
        self,
        rule_id: str,
        blocked_by: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Explicitly block a rule from promotion.

        Args:
            rule_id: Candidate rule ID to block
            blocked_by: Who blocked the rule
            reason: Required reason for blocking

        Returns:
            Block record

        Raises:
            KeyError: If rule has not been shadow evaluated
            ValueError: If rule is already promoted
        """
        shadow_result = self.shadow_evaluator.get(rule_id)
        if not shadow_result:
            raise KeyError(
                f"Rule has not been shadow evaluated: {rule_id}. "
                f"Only shadow-evaluated rules can be blocked."
            )

        if shadow_result.get("promotion_status") == PROMOTION_STATUS_PROMOTED:
            raise ValueError(f"Cannot block a promoted rule: {rule_id}")

        record = {
            "source_candidate_rule_id": rule_id,
            "promotion_status": PROMOTION_STATUS_BLOCKED,
            "blocked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "blocked_by": blocked_by,
            "block_reason": reason,
        }

        shadow_result["promotion_status"] = PROMOTION_STATUS_BLOCKED
        shadow_result["block_record"] = record

        self._promotion_records[rule_id] = record
        return record

    def get(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Get promotion record for a rule."""
        return self._promotion_records.get(rule_id)

    def get_shadow_result(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Get shadow result (with promotion info) for a rule."""
        return self.shadow_evaluator.get(rule_id)

    def list_promotable(self) -> List[str]:
        """List rule IDs that are eligible for promotion."""
        result = []
        for rule_id, sr in self.shadow_evaluator._shadow_results.items():
            promo_status = sr.get("promotion_status")
            if promo_status == PROMOTION_STATUS_ELIGIBLE or promo_status is None:
                # Check if actually eligible
                gate = sr.get("gate_evaluation")
                if gate and gate.get("passed"):
                    result.append(rule_id)
        return result

    def list_blocked(self) -> List[str]:
        """List rule IDs that are blocked from promotion."""
        result = []
        for rule_id, sr in self.shadow_evaluator._shadow_results.items():
            if sr.get("promotion_status") == PROMOTION_STATUS_BLOCKED:
                result.append(rule_id)
        return result

    def list_promoted(self) -> List[str]:
        """List rule IDs that have been promoted."""
        result = []
        for rule_id, sr in self.shadow_evaluator._shadow_results.items():
            if sr.get("promotion_status") == PROMOTION_STATUS_PROMOTED:
                result.append(rule_id)
        return result

    def summarize(self) -> Dict[str, Any]:
        """Summarize promotion status across all rules."""
        total = len(self.shadow_evaluator._shadow_results)
        by_status = {
            PROMOTION_STATUS_ELIGIBLE: 0,
            PROMOTION_STATUS_PROMOTED: 0,
            PROMOTION_STATUS_BLOCKED: 0,
            "not_evaluated": 0,
        }

        for sr in self.shadow_evaluator._shadow_results.values():
            status = sr.get("promotion_status")
            if status in by_status:
                by_status[status] += 1
            else:
                by_status["not_evaluated"] += 1

        return {
            "total_shadow_evaluated": total,
            "by_promotion_status": by_status,
            "eligible_count": len(self.list_promotable()),
            "blocked_count": len(self.list_blocked()),
            "promoted_count": len(self.list_promoted()),
            "gate_config": {
                "max_regressions": self.max_regressions,
                "min_improvements": self.min_improvements,
            },
        }

    def export(self, fmt: str = "json") -> str:
        """Export promotion status in JSON or Markdown format."""
        summary = self.summarize()

        if fmt == "markdown":
            lines = [
                "# Promotion Workflow Report",
                "",
                f"**Total shadow evaluated:** {summary['total_shadow_evaluated']}  ",
                f"**Eligible for promotion:** {summary['eligible_count']}  ",
                f"**Blocked:** {summary['blocked_count']}  ",
                f"**Promoted:** {summary['promoted_count']}  ",
                "",
                "## Gate Configuration",
                "",
                f"- **Max regressions:** {summary['gate_config']['max_regressions']}",
                f"- **Min improvements:** {summary['gate_config']['min_improvements']}",
                "",
            ]

            # List by status
            promoted = self.list_promoted()
            if promoted:
                lines += ["## Promoted Rules", ""]
                for rule_id in promoted:
                    rec = self._promotion_records.get(rule_id, {})
                    lines += [
                        f"### ✅ `{rule_id}`",
                        f"- **Promoted at:** {rec.get('promoted_at', 'N/A')}",
                        f"- **Promoted by:** {rec.get('promoted_by', 'unknown')}",
                    ]
                    if rec.get("promotion_reason"):
                        lines += [f"- **Reason:** {rec['promotion_reason']}"]
                    lines.append("")

            blocked = self.list_blocked()
            if blocked:
                lines += ["## Blocked Rules", ""]
                for rule_id in blocked:
                    rec = self._promotion_records.get(rule_id, {})
                    lines += [
                        f"### 🚫 `{rule_id}`",
                        f"- **Blocked at:** {rec.get('blocked_at', 'N/A')}",
                        f"- **Blocked by:** {rec.get('blocked_by', 'unknown')}",
                        f"- **Reason:** {rec.get('block_reason', 'N/A')}",
                    ]
                    lines.append("")

            eligible = self.list_promotable()
            if eligible:
                lines += ["## Eligible for Promotion", ""]
                for rule_id in eligible:
                    sr = self.shadow_evaluator.get(rule_id)
                    gate = sr.get("gate_evaluation", {}) if sr else {}
                    lines += [
                        f"- 🟢 `{rule_id}`",
                        f"  - Regressions: {gate.get('gate_config', {}).get('actual_regressions', 'N/A')}",
                        f"  - Improvements: {gate.get('gate_config', {}).get('actual_improvements', 'N/A')}",
                    ]
                lines.append("")

            lines += [
                "---",
                "",
                "> Note: This workflow does not modify production policies.",
            ]
            return "\n".join(lines)

        return json.dumps({
            "summary": summary,
            "promotion_records": list(self._promotion_records.values()),
            "shadow_results": list(self.shadow_evaluator._shadow_results.values()),
            "note": "Promotion workflow does not modify production policies.",
        }, ensure_ascii=False, indent=2)

    def save(self, path: Path, fmt: str = "json") -> None:
        """Save promotion data to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.export(fmt), encoding="utf-8")

    def load(self, path: Path) -> None:
        """Load promotion data from a JSON file."""
        path = Path(path)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))

        # Restore promotion records
        for record in data.get("promotion_records", []):
            rule_id = record.get("source_candidate_rule_id")
            if rule_id:
                self._promotion_records[rule_id] = record

        # Restore shadow results with promotion info
        for sr in data.get("shadow_results", []):
            rule_id = sr.get("source_candidate_rule_id")
            if rule_id:
                self.shadow_evaluator._shadow_results[rule_id] = sr


def create_promotion_manager(
    shadow_evaluator: ShadowEvaluator,
    max_regressions: int = DEFAULT_MAX_REGRESSIONS,
    min_improvements: int = DEFAULT_MIN_IMPROVEMENTS,
) -> PromotionManager:
    """Create a promotion manager for the given shadow evaluator."""
    return PromotionManager(
        shadow_evaluator,
        max_regressions=max_regressions,
        min_improvements=min_improvements,
    )


# ---------------------------------------------------------------------------
# Step114: Rule Provenance Tracking
# ---------------------------------------------------------------------------

def make_provenance(
    rule_id: str,
    source_candidate_rule_id: Optional[str] = None,
    source_regression_case_ids: Optional[List[str]] = None,
    source_benchmark_snapshot: Optional[str] = None,
    source_scenario_packs: Optional[List[str]] = None,
    created_by: str = "candidate_generation",
    parent_rule_id: Optional[str] = None,
    rule_version: int = 1,
) -> Dict[str, Any]:
    """Create a provenance metadata dict for a rule.

    Args:
        rule_id: The rule identifier
        source_candidate_rule_id: Original candidate rule ID (None for initial generation)
        source_regression_case_ids: List of regression case IDs that triggered this rule
        source_benchmark_snapshot: Benchmark snapshot identifier
        source_scenario_packs: List of scenario pack names
        created_by: Who/what created this rule
        parent_rule_id: Parent rule ID for versioned rules
        rule_version: Version number (starts at 1)

    Returns:
        Provenance dict
    """
    return {
        "rule_id": rule_id,
        "source_candidate_rule_id": source_candidate_rule_id,
        "source_regression_case_ids": source_regression_case_ids or [],
        "source_benchmark_snapshot": source_benchmark_snapshot,
        "source_scenario_packs": source_scenario_packs or [],
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "created_by": created_by,
        "rule_version": rule_version,
        "parent_rule_id": parent_rule_id,
    }


def get_rule_lineage(
    rule_id: str,
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
) -> List[Dict[str, Any]]:
    """Get the lineage/chain of a rule from candidate to current state.

    Args:
        rule_id: The rule ID to trace
        registry: AdoptionRegistry containing the rule
        promotion_manager: Optional PromotionManager for promotion info

    Returns:
        List of lineage entries from earliest to latest, each containing:
        - stage: "candidate" | "adopted" | "shadow_evaluated" | "promoted" | "rolled_back"
        - rule_id: str
        - provenance: dict
        - timestamp: str
        - status: str (adoption/promotion status)
    """
    lineage: List[Dict[str, Any]] = []

    entry = registry.get(rule_id)
    if not entry:
        return lineage

    # Get provenance from entry
    provenance = entry.get("provenance")

    # Stage 1: Candidate (if we have provenance)
    if provenance:
        lineage.append({
            "stage": "candidate",
            "rule_id": rule_id,
            "provenance": provenance,
            "timestamp": provenance.get("created_at", ""),
            "status": "generated",
        })

    # Stage 2: Adopted
    lineage.append({
        "stage": "adopted",
        "rule_id": rule_id,
        "provenance": provenance,
        "timestamp": entry.get("adopted_at", ""),
        "status": entry.get("adoption_status", ""),
    })

    # Stage 3: Shadow evaluated (if available via promotion_manager)
    if promotion_manager:
        shadow_result = promotion_manager.get_shadow_result(rule_id)
        if shadow_result:
            lineage.append({
                "stage": "shadow_evaluated",
                "rule_id": rule_id,
                "provenance": provenance,
                "timestamp": shadow_result.get("shadowed_at", ""),
                "status": shadow_result.get("promotion_status", ""),
            })

            # Stage 4: Promoted
            if shadow_result.get("promotion_status") == PROMOTION_STATUS_PROMOTED:
                promo_record = promotion_manager.get(rule_id)
                lineage.append({
                    "stage": "promoted",
                    "rule_id": rule_id,
                    "provenance": provenance,
                    "timestamp": promo_record.get("promoted_at", "") if promo_record else "",
                    "status": PROMOTION_STATUS_PROMOTED,
                })

    # Stage: Rolled back
    if entry.get("adoption_status") == ADOPTION_STATUS_ROLLED_BACK:
        lineage.append({
            "stage": "rolled_back",
            "rule_id": rule_id,
            "provenance": provenance,
            "timestamp": entry.get("rolled_back_at", ""),
            "status": ADOPTION_STATUS_ROLLED_BACK,
        })

    return lineage


def summarize_provenance(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize provenance info across multiple registry entries.

    Args:
        entries: List of registry entries (from registry.list_adopted())

    Returns:
        Summary dict with provenance statistics
    """
    total = len(entries)
    with_provenance = 0
    by_source_type: Dict[str, int] = {}
    by_version: Dict[int, int] = {}
    with_parent = 0
    regression_case_ids: List[str] = []
    scenario_packs: List[str] = []

    for entry in entries:
        prov = entry.get("provenance")
        if prov:
            with_provenance += 1

            # Count by created_by (source type)
            created_by = prov.get("created_by", "unknown")
            by_source_type[created_by] = by_source_type.get(created_by, 0) + 1

            # Count by version
            version = prov.get("rule_version", 1)
            by_version[version] = by_version.get(version, 0) + 1

            # Count with parent
            if prov.get("parent_rule_id"):
                with_parent += 1

            # Collect regression case IDs
            regression_case_ids.extend(prov.get("source_regression_case_ids", []))

            # Collect scenario packs
            scenario_packs.extend(prov.get("source_scenario_packs", []))

    return {
        "total": total,
        "with_provenance": with_provenance,
        "without_provenance": total - with_provenance,
        "by_source_type": by_source_type,
        "by_version": by_version,
        "with_parent": with_parent,
        "unique_regression_case_count": len(set(regression_case_ids)),
        "unique_scenario_pack_count": len(set(scenario_packs)),
    }


# ---------------------------------------------------------------------------
# Step115: Policy Lineage Visualization
# ---------------------------------------------------------------------------

def build_policy_lineage_graph(
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Build a lineage graph for all rules in the registry.

    Args:
        registry: AdoptionRegistry containing rules
        promotion_manager: Optional PromotionManager for promotion info

    Returns:
        Graph dict with:
        - nodes: List of rule nodes with id, status, stage, provenance, rollback_info
        - edges: List of edges with from, to, type (parent/derived)
        - roots: List of rule_ids with no parent
        - summary: Summary statistics
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_ids: set = set()

    # Collect all entries
    entries = registry.list_adopted()

    # Build nodes
    for entry in entries:
        rule_id = entry.get("source_candidate_rule_id")
        if not rule_id:
            continue

        node_ids.add(rule_id)
        prov = entry.get("provenance", {})

        # Determine current stage
        stage = "adopted"
        status = entry.get("adoption_status", "")

        if status == ADOPTION_STATUS_ROLLED_BACK:
            stage = "rolled_back"
        elif promotion_manager:
            shadow = promotion_manager.get_shadow_result(rule_id)
            if shadow:
                promo_status = shadow.get("promotion_status", "")
                if promo_status == PROMOTION_STATUS_PROMOTED:
                    stage = "promoted"
                elif promo_status == PROMOTION_STATUS_ELIGIBLE:
                    stage = "shadow_evaluated"
                elif promo_status == PROMOTION_STATUS_BLOCKED:
                    stage = "shadow_evaluated"
                elif shadow.get("shadowed_at"):
                    stage = "shadow_evaluated"

        node = {
            "rule_id": rule_id,
            "status": status or "unknown",
            "stage": stage,
            "provenance": prov,
            "source_candidate_rule_id": prov.get("source_candidate_rule_id"),
            "parent_rule_id": prov.get("parent_rule_id"),
            "rule_version": prov.get("rule_version", 1),
            "created_at": prov.get("created_at", ""),
            "created_by": prov.get("created_by", "unknown"),
            "rollback_info": entry.get("rollback_info", {}),
        }

        # Add rollback details if rolled back
        if status == ADOPTION_STATUS_ROLLED_BACK:
            node["rolled_back_at"] = entry.get("rolled_back_at", "")
            node["rolled_back_by"] = entry.get("rolled_back_by", "")
            node["rollback_reason"] = entry.get("rollback_reason", "")

        nodes.append(node)

        # Build parent edge
        parent_id = prov.get("parent_rule_id")
        if parent_id:
            edges.append({
                "from": parent_id,
                "to": rule_id,
                "type": "parent",
            })

    # Identify roots (no parent or parent not in graph)
    roots = []
    for node in nodes:
        parent_id = node.get("parent_rule_id")
        if not parent_id or parent_id not in node_ids:
            roots.append(node["rule_id"])

    # Build summary
    by_stage: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    rollback_count = 0

    for node in nodes:
        stage = node.get("stage", "unknown")
        by_stage[stage] = by_stage.get(stage, 0) + 1

        status = node.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

        if node.get("stage") == "rolled_back":
            rollback_count += 1

    return {
        "nodes": nodes,
        "edges": edges,
        "roots": roots,
        "summary": {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "root_count": len(roots),
            "by_stage": by_stage,
            "by_status": by_status,
            "rollback_count": rollback_count,
        },
    }


def render_policy_lineage_tree(
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
    include_provenance: bool = False,
) -> str:
    """Render a human-readable tree view of policy lineage.

    Args:
        registry: AdoptionRegistry containing rules
        promotion_manager: Optional PromotionManager for promotion info
        include_provenance: Whether to include provenance details

    Returns:
        Multi-line string representing the lineage tree
    """
    graph = build_policy_lineage_graph(registry, promotion_manager)

    lines: List[str] = []
    lines.append("# Policy Lineage Tree")
    lines.append("")

    # Summary
    summary = graph["summary"]
    lines.append(f"**Total rules:** {summary['total_nodes']}")
    lines.append(f"**Roots:** {summary['root_count']}")
    lines.append(f"**Rollbacks:** {summary['rollback_count']}")
    lines.append("")

    # Status icons
    status_icons = {
        "adopted": "✅",
        "promoted": "🚀",
        "shadow_evaluated": "🔍",
        "rolled_back": "↩️",
        "inactive": "⏸️",
        "unknown": "❓",
    }

    # Build children map
    children_map: Dict[str, List[str]] = {}
    for edge in graph["edges"]:
        parent = edge["from"]
        child = edge["to"]
        children_map.setdefault(parent, []).append(child)

    # Node lookup
    node_map = {n["rule_id"]: n for n in graph["nodes"]}

    # Render tree recursively
    def render_node(rule_id: str, prefix: str = "", is_last: bool = True) -> None:
        node = node_map.get(rule_id)
        if not node:
            return

        status = node.get("status", "unknown")
        stage = node.get("stage", "unknown")
        icon = status_icons.get(stage, "❓")

        connector = "└── " if is_last else "├── "
        line_prefix = prefix + connector

        status_str = f"[{stage}]" if stage != status else f"[{status}]"
        lines.append(f"{line_prefix}{icon} `{rule_id}` {status_str}")

        # Optionally include provenance
        if include_provenance and node.get("provenance"):
            prov = node["provenance"]
            prov_prefix = prefix + ("    " if is_last else "│   ")

            if prov.get("source_regression_case_ids"):
                cases = prov["source_regression_case_ids"][:3]
                lines.append(f"{prov_prefix}├─ cases: {', '.join(cases)}")

            if prov.get("source_scenario_packs"):
                packs = prov["source_scenario_packs"][:3]
                lines.append(f"{prov_prefix}├─ packs: {', '.join(packs)}")

            if prov.get("rule_version", 1) > 1:
                lines.append(f"{prov_prefix}├─ version: {prov['rule_version']}")

        # Render rollback info
        if stage == "rolled_back":
            rollback_prefix = prefix + ("    " if is_last else "│   ")
            reason = node.get("rollback_reason", "N/A")
            lines.append(f"{rollback_prefix}└─ rollback reason: {reason}")

        # Render children
        children = children_map.get(rule_id, [])
        child_prefix = prefix + ("    " if is_last else "│   ")
        for i, child_id in enumerate(children):
            is_last_child = (i == len(children) - 1)
            render_node(child_id, child_prefix, is_last_child)

    # Render from roots
    roots = graph["roots"]
    if roots:
        lines.append("## Lineage Tree")
        lines.append("")
        for i, root_id in enumerate(roots):
            is_last_root = (i == len(roots) - 1)
            render_node(root_id, "", is_last_root)
            if i < len(roots) - 1:
                lines.append("")
    else:
        lines.append("_No rules in registry._")

    return "\n".join(lines)


def get_policy_evolution_summary(
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Get a summary of policy evolution across the registry.

    Args:
        registry: AdoptionRegistry containing rules
        promotion_manager: Optional PromotionManager for promotion info

    Returns:
        Evolution summary dict with:
        - lineage_graph: The full lineage graph
        - evolution_metrics: Metrics about policy evolution
        - rollback_history: List of rollback events
    """
    graph = build_policy_lineage_graph(registry, promotion_manager)

    # Collect rollback history
    rollback_history: List[Dict[str, Any]] = []
    for node in graph["nodes"]:
        if node.get("stage") == "rolled_back":
            rollback_history.append({
                "rule_id": node["rule_id"],
                "rolled_back_at": node.get("rolled_back_at", ""),
                "rolled_back_by": node.get("rolled_back_by", ""),
                "rollback_reason": node.get("rollback_reason", ""),
            })

    # Sort by rollback time
    rollback_history.sort(key=lambda x: x.get("rolled_back_at", ""), reverse=True)

    # Evolution metrics
    summary = graph["summary"]
    evolution_metrics = {
        "total_rules": summary["total_nodes"],
        "active_rules": summary["by_status"].get(ADOPTION_STATUS_ADOPTED, 0),
        "promoted_rules": summary["by_stage"].get("promoted", 0),
        "rolled_back_rules": summary["rollback_count"],
        "lineage_depth": _calculate_max_depth(graph),
        "rollback_rate": (
            summary["rollback_count"] / summary["total_nodes"]
            if summary["total_nodes"] > 0 else 0
        ),
    }

    return {
        "lineage_graph": graph,
        "evolution_metrics": evolution_metrics,
        "rollback_history": rollback_history,
    }


def _calculate_max_depth(graph: Dict[str, Any]) -> int:
    """Calculate the maximum depth of the lineage tree."""
    children_map: Dict[str, List[str]] = {}
    for edge in graph["edges"]:
        parent = edge["from"]
        child = edge["to"]
        children_map.setdefault(parent, []).append(child)

    roots = graph["roots"]

    def depth(rule_id: str) -> int:
        children = children_map.get(rule_id, [])
        if not children:
            return 1
        return 1 + max(depth(c) for c in children)

    if not roots:
        return 0

    return max(depth(r) for r in roots)





# ---------------------------------------------------------------------------
# Step116: Rule Conflict Detection
# ---------------------------------------------------------------------------

# Conflict type constants
CONFLICT_OVERLAPPING_APPLICABILITY = "overlapping_applicability"
CONFLICT_PREREQUISITE = "prerequisite_conflict"
CONFLICT_ROLLBACK_REINTRODUCTION = "rollback_lineage_reintroduction"
CONFLICT_INCONSISTENT_PROVENANCE = "inconsistent_provenance"

VALID_CONFLICT_TYPES = (
    CONFLICT_OVERLAPPING_APPLICABILITY,
    CONFLICT_PREREQUISITE,
    CONFLICT_ROLLBACK_REINTRODUCTION,
    CONFLICT_INCONSISTENT_PROVENANCE,
)

# Severity levels
SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

VALID_SEVERITIES = (SEVERITY_LOW, SEVERITY_MEDIUM, SEVERITY_HIGH)


def detect_rule_conflicts(
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
) -> List[Dict[str, Any]]:
    """Detect conflicts among rules in the registry.

    Args:
        registry: AdoptionRegistry containing rules
        promotion_manager: Optional PromotionManager for promotion info

    Returns:
        List of conflict dicts, Each conflict has:
        - type: conflict type constant
        - rule_ids: list of involved rule IDs
        - severity: low/medium/high
        - reason: human-readable explanation
    """
    conflicts: List[Dict[str, Any]] = []
    entries = registry.list_adopted()
    
    if not entries:
        return conflicts
    
    # Build lookup maps
    entry_map = {e.get("source_candidate_rule_id"): e for e in entries}
    rule_ids = set(entry_map.keys())
    
    # Get lineage graph for rollback lineage detection
    lineage_graph = build_policy_lineage_graph(registry, promotion_manager)
    node_map = {n["rule_id"]: n for n in lineage_graph["nodes"]}
    
    # Track rolled-back lineages
    rolled_back_ids = set()
    rolled_back_lineage_ids = set()
    
    for node in lineage_graph["nodes"]:
        if node.get("stage") == "rolled_back":
            rolled_back_ids.add(node["rule_id"])
    
    # Find all descendants of rolled-back rules
    children_map: Dict[str, List[str]] = {}
    for edge in lineage_graph["edges"]:
        parent = edge["from"]
        child = edge["to"]
        children_map.setdefault(parent, []).append(child)
    
    def get_all_descendants(rule_id: str) -> set:
        """Recursively get all descendants of a rule."""
        descendants = set()
        children = children_map.get(rule_id, [])
        for child in children:
            descendants.add(child)
            descendants.update(get_all_descendants(child))
        return descendants
    
    for rb_id in rolled_back_ids:
        rolled_back_lineage_ids.add(rb_id)
        rolled_back_lineage_ids.update(get_all_descendants(rb_id))
    
    # 1. Detect overlapping applicability conflicts
    conflicts.extend(_detect_overlapping_applicability(entries, entry_map))
    
    # 2. Detect prerequisite conflicts
    conflicts.extend(_detect_prerequisite_conflicts(entries, entry_map))
    
    # 3. Detect rollback lineage reintroduction
    conflicts.extend(_detect_rollback_reintroduction(
        entries, entry_map, rolled_back_ids, rolled_back_lineage_ids
    ))
    
    # 4. Detect inconsistent provenance
    conflicts.extend(_detect_inconsistent_provenance(entries, entry_map, node_map))
    
    return conflicts


def _detect_overlapping_applicability(
    entries: List[Dict[str, Any]],
    entry_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Detect rules with overlapping applicability but different outcomes."""
    conflicts: List[Dict[str, Any]] = []
    
    # Group by rule_type and affected_cases overlap
    for i, entry_a in enumerate(entries):
        rule_id_a = entry_a.get("source_candidate_rule_id")
        if not rule_id_a:
            continue
        
        change_a = entry_a.get("suggested_change", {})
        type_a = entry_a.get("rule_type", "")
        cases_a = set(entry_a.get("provenance", {}).get("source_regression_case_ids", []))
        
        for j, entry_b in enumerate(entries[i+1:], start=i+1):
            rule_id_b = entry_b.get("source_candidate_rule_id")
            if not rule_id_b:
                continue
            
            change_b = entry_b.get("suggested_change", {})
            type_b = entry_b.get("rule_type", "")
            cases_b = set(entry_b.get("provenance", {}).get("source_regression_case_ids", []))
            
            # Check for overlap
            same_type = type_a == type_b and type_a != ""
            case_overlap = bool(cases_a & cases_b)
            
            if not (same_type or case_overlap):
                continue
            
            # Check for conflicting changes
            change_conflict = False
            for key in set(change_a.keys()) & set(change_b.keys()):
                if change_a.get(key) != change_b.get(key):
                    change_conflict = True
                    break
            
            if change_conflict:
                conflicts.append({
                    "type": CONFLICT_OVERLAPPING_APPLICABILITY,
                    "rule_ids": [rule_id_a, rule_id_b],
                    "severity": SEVERITY_HIGH,
                    "reason": f"Rules have overlapping applicability (type={type_a}, cases_overlap={case_overlap}) but different suggested changes",
                    "details": {
                        "rule_type": type_a,
                        "case_overlap": list(cases_a & cases_b)[:5] if cases_a & cases_b else [],
                        "conflicting_keys": list(set(change_a.keys()) & set(change_b.keys())),
                    },
                })
    
    return conflicts


def _detect_prerequisite_conflicts(
    entries: List[Dict[str, Any]],
    entry_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Detect rules that break each other's prerequisites.
    
    This is a heuristic check based on rule_type interactions.
    """
    conflicts: List[Dict[str, Any]] = []
    
    # Known problematic type combinations
    # These are heuristics - in a real system you'd have explicit prerequisite declarations
    type_interactions = {
        # Orchestration rules may conflict with budget_trim rules
        ("orchestration", "budget_trim"): "orchestration rule may conflict with budget_trim's resource constraints",
        # Tier threshold changes may conflict with failed_chain suppression
        ("tier_threshold", "failed_chain"): "tier_threshold may override failed_chain's suppression logic",
    }
    
    type_to_entries: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        rt = entry.get("rule_type", "")
        if rt:
            type_to_entries.setdefault(rt, []).append(entry)
    
    for (type_a, type_b), reason in type_interactions.items():
        entries_a = type_to_entries.get(type_a, [])
        entries_b = type_to_entries.get(type_b, [])
        
        for entry_a in entries_a:
            rule_id_a = entry_a.get("source_candidate_rule_id")
            if not rule_id_a:
                continue
            
            for entry_b in entries_b:
                rule_id_b = entry_b.get("source_candidate_rule_id")
                if not rule_id_b:
                    continue
                
                # Check if they affect the same cases
                cases_a = set(entry_a.get("provenance", {}).get("source_regression_case_ids", []))
                cases_b = set(entry_b.get("provenance", {}).get("source_regression_case_ids", []))
                
                if cases_a & cases_b:
                    conflicts.append({
                        "type": CONFLICT_PREREQUISITE,
                        "rule_ids": [rule_id_a, rule_id_b],
                        "severity": SEVERITY_MEDIUM,
                        "reason": reason,
                        "details": {
                            "interaction": f"{type_a} <-> {type_b}",
                            "case_overlap": list(cases_a & cases_b)[:3],
                        },
                    })
    
    return conflicts


def _detect_rollback_reintroduction(
    entries: List[Dict[str, Any]],
    entry_map: Dict[str, Dict[str, Any]],
    rolled_back_ids: set,
    rolled_back_lineage_ids: set,
) -> List[Dict[str, Any]]:
    """Detect rules that reintroduce rolled-back lineages."""
    conflicts: List[Dict[str, Any]] = []
    
    for entry in entries:
        rule_id = entry.get("source_candidate_rule_id")
        if not rule_id:
            continue
        
        # Check if this rule is itself rolled back
        if rule_id in rolled_back_ids:
            conflicts.append({
                "type": CONFLICT_ROLLBACK_REINTRODUCTION,
                "rule_ids": [rule_id],
                "severity": SEVERITY_HIGH,
                "reason": f"Rule {rule_id} is rolled back but still in active registry",
                "details": {
                    "status": entry.get("adoption_status"),
                },
            })
            continue
        
        # Check if this rule derives from a rolled-back lineage
        prov = entry.get("provenance", {})
        parent_id = prov.get("parent_rule_id")
        
        if parent_id and parent_id in rolled_back_lineage_ids:
            conflicts.append({
                "type": CONFLICT_ROLLBACK_REINTRODUCTION,
                "rule_ids": [rule_id, parent_id],
                "severity": SEVERITY_HIGH,
                "reason": f"Rule {rule_id} derives from rolled-back lineage (parent: {parent_id})",
                "details": {
                    "parent_id": parent_id,
                    "parent_status": "rolled_back",
                },
            })
    
    return conflicts


def _detect_inconsistent_provenance(
    entries: List[Dict[str, Any]],
    entry_map: Dict[str, Dict[str, Any]],
    node_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Detect rules with inconsistent provenance/parent relationships."""
    conflicts: List[Dict[str, Any]] = []
    
    for entry in entries:
        rule_id = entry.get("source_candidate_rule_id")
        if not rule_id:
            continue
        
        prov = entry.get("provenance", {})
        node = node_map.get(rule_id, {})
        
        # Check for missing provenance
        if not prov:
            conflicts.append({
                "type": CONFLICT_INCONSISTENT_PROVENANCE,
                "rule_ids": [rule_id],
                "severity": SEVERITY_LOW,
                "reason": f"Rule {rule_id} has no provenance metadata",
                "details": {},
            })
            continue
        
        # Check for source_candidate_rule_id mismatch
        source_id = prov.get("source_candidate_rule_id")
        if source_id and source_id != rule_id:
            # This is actually OK - it means the rule was derived from another candidate
            # Only report if the source doesn't exist in the registry
            if source_id not in entry_map:
                conflicts.append({
                    "type": CONFLICT_INCONSISTENT_PROVENANCE,
                    "rule_ids": [rule_id],
                    "severity": SEVERITY_MEDIUM,
                    "reason": f"Rule {rule_id} references non-existent source candidate {source_id}",
                    "details": {
                        "source_candidate_rule_id": source_id,
                    },
                })
        
        # Check for parent_rule_id consistency
        parent_id = prov.get("parent_rule_id")
        if parent_id:
            parent_entry = entry_map.get(parent_id)
            if not parent_entry:
                conflicts.append({
                    "type": CONFLICT_INCONSISTENT_PROVENANCE,
                    "rule_ids": [rule_id],
                    "severity": SEVERITY_MEDIUM,
                    "reason": f"Rule {rule_id} references non-existent parent {parent_id}",
                    "details": {
                        "parent_rule_id": parent_id,
                    },
                })
            else:
                # Check version consistency
                parent_prov = parent_entry.get("provenance", {})
                parent_version = parent_prov.get("rule_version", 1)
                current_version = prov.get("rule_version", 1)
                
                if current_version <= parent_version:
                    conflicts.append({
                        "type": CONFLICT_INCONSISTENT_PROVENANCE,
                        "rule_ids": [rule_id, parent_id],
                        "severity": SEVERITY_LOW,
                        "reason": f"Rule {rule_id} version ({current_version}) should be greater than parent version ({parent_version})",
                        "details": {
                            "rule_version": current_version,
                            "parent_version": parent_version,
                        },
                    })
    
    return conflicts


def build_conflict_report(
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Build a comprehensive conflict report for all rules in the registry.

    Args:
        registry: AdoptionRegistry containing rules
        promotion_manager: Optional PromotionManager for promotion info

    Returns:
        Conflict report dict with:
        - conflicts: list of conflict dicts
        - summary: summary statistics
    """
    conflicts = detect_rule_conflicts(registry, promotion_manager)
    
    # Build summary
    by_type: Dict[str, int] = {}
    by_severity: Dict[str, int] = {
        SEVERITY_LOW: 0,
        SEVERITY_MEDIUM: 0,
        SEVERITY_HIGH: 0,
    }
    
    for conflict in conflicts:
        ct = conflict.get("type", "unknown")
        by_type[ct] = by_type.get(ct, 0) + 1
        
        sev = conflict.get("severity", SEVERITY_MEDIUM)
        if sev in by_severity:
            by_severity[sev] += 1
    
    return {
        "conflicts": conflicts,
        "summary": {
            "total_conflicts": len(conflicts),
            "by_type": by_type,
            "by_severity": by_severity,
            "high_severity": by_severity[SEVERITY_HIGH],
            "has_critical_conflicts": by_severity[SEVERITY_HIGH] > 0,
        },
    }


def get_policy_conflicts(
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Get policy conflicts (alias for build_conflict_report).

    Args:
        registry: AdoptionRegistry containing rules
        promotion_manager: Optional PromotionManager for promotion info

    Returns:
        Conflict report dict
    """
    return build_conflict_report(registry, promotion_manager)


# ---------------------------------------------------------------------------
# Step117: Rule Bundle Evaluation
# ---------------------------------------------------------------------------

def evaluate_rule_bundle(
    rule_ids: List[str],
    registry: AdoptionRegistry,
    individual_results: Optional[Dict[str, float]] = None,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Evaluate a bundle of rules together and compare with individual results.

    Args:
        rule_ids: List of rule IDs to evaluate as a bundle
        registry: AdoptionRegistry containing the rules
        individual_results: Optional pre-computed individual rule results
            (rule_id -> score). If None, uses placeholder logic.
        promotion_manager: Optional PromotionManager for additional context

    Returns:
        Bundle evaluation dict with:
        - bundle_rule_ids: list of rule IDs in bundle
        - per_rule_results: individual results per rule
        - bundle_result: combined result for bundle
        - delta_vs_best_individual: improvement over best individual
        - harmful_interaction: bool (bundle worse than best individual)
        - no_added_value: bool (bundle no better than best individual)
    """
    if not rule_ids:
        return {
            "bundle_rule_ids": [],
            "per_rule_results": {},
            "bundle_result": 0.0,
            "delta_vs_best_individual": 0.0,
            "harmful_interaction": False,
            "no_added_value": True,
        }

    # Get individual results (placeholder: use provided or derive from shadow results)
    per_rule_results: Dict[str, float] = {}
    for rule_id in rule_ids:
        if individual_results and rule_id in individual_results:
            per_rule_results[rule_id] = individual_results[rule_id]
        else:
            # Placeholder: derive from shadow evaluation if available
            entry = registry.get(rule_id)
            if entry:
                # Use risk_level as a proxy for score (low=0.0, medium=0.5, high=0.0)
                risk = entry.get("risk_level", "medium")
                score = {"low": 0.7, "medium": 0.5, "high": 0.3}.get(risk, 0.5)
                per_rule_results[rule_id] = score
            else:
                per_rule_results[rule_id] = 0.5

    # Calculate bundle result (average of individual)
    if per_rule_results:
        bundle_result = sum(per_rule_results.values()) / len(per_rule_results)
    else:
        bundle_result = 0.0

    # Find best individual result
    best_individual = max(per_rule_results.values()) if per_rule_results else 0.0

    # Calculate delta
    delta_vs_best_individual = bundle_result - best_individual

    # Determine harmful_interaction and no_added_value
    # Using small epsilon to avoid floating point issues
    epsilon = 0.01
    harmful_interaction = delta_vs_best_individual < -epsilon
    no_added_value = abs(delta_vs_best_individual) < epsilon

    # Get conflicts within bundle if Step116 available
    detected_conflicts = []
    if promotion_manager:
        try:
            conflict_report = build_conflict_report(registry, promotion_manager)
            for conflict in conflict_report.get("conflicts", []):
                conflict_ids = set(conflict.get("rule_ids", []))
                if conflict_ids & set(rule_ids):
                    detected_conflicts.append(conflict)
        except Exception:
            pass

    return {
        "bundle_rule_ids": list(rule_ids),
        "per_rule_results": per_rule_results,
        "bundle_result": bundle_result,
        "delta_vs_best_individual": round(delta_vs_best_individual, 4),
        "harmful_interaction": harmful_interaction,
        "no_added_value": no_added_value,
        "detected_conflicts": detected_conflicts,
    }


# ---------------------------------------------------------------------------
# Step118: Policy Health Scoring
# ---------------------------------------------------------------------------

def compute_policy_health(
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Compute overall health score for the policy registry.

    Args:
        registry: AdoptionRegistry containing rules
        promotion_manager: Optional PromotionManager for bundle context

    Returns:
        Health report dict with:
        - health_score: 0-100 score
        - grade: A/B/C/D/F
        - breakdown: score breakdown by category
        - issues: list of detected issues
        - summary: summary statistics
    """
    entries = registry.list_adopted()
    total_rules = len(entries)

    if total_rules == 0:
        return {
            "health_score": 100,
            "grade": "A",
            "breakdown": {},
            "issues": [],
            "summary": {
                "total_rules": 0,
                "rules_with_provenance": 0,
                "rolled_back_rules": 0,
                "conflicts": 0,
                "harmful_bundles": 0,
            },
        }

    issues: List[str] = []
    breakdown: Dict[str, int] = {}

    # A. Provenance completeness (max 20 points)
    rules_with_provenance = 0
    missing_provenance_count = 0
    for entry in entries:
        prov = entry.get("provenance")
        if prov and prov.get("rule_id"):
            rules_with_provenance += 1
        else:
            missing_provenance_count += 1

    provenance_score = 20
    if missing_provenance_count > 0:
        provenance_score = max(0, 20 - missing_provenance_count * 2)
        issues.append(f"{missing_provenance_count} rules missing provenance")
    breakdown["provenance_completeness"] = provenance_score

    # B. Lineage health (max 20 points)
    lineage_conflicts = [
        c for c in detect_rule_conflicts(registry, promotion_manager)
        if c.get("type") == CONFLICT_INCONSISTENT_PROVENANCE
    ]
    lineage_score = 20
    if len(lineage_conflicts) > 0:
        lineage_score = max(0, 20 - len(lineage_conflicts) * 3)
        issues.append(f"{len(lineage_conflicts)} lineage/provenance inconsistencies")
    breakdown["lineage_health"] = lineage_score

    # C. Conflict health (max 20 points)
    conflict_report = build_conflict_report(registry, promotion_manager)
    conflicts = conflict_report.get("conflicts", [])
    high_sev = sum(1 for c in conflicts if c.get("severity") == SEVERITY_HIGH)
    med_sev = sum(1 for c in conflicts if c.get("severity") == SEVERITY_MEDIUM)

    conflict_score = 20
    if high_sev > 0:
        conflict_score = max(0, conflict_score - high_sev * 5)
        issues.append(f"{high_sev} high severity conflict(s)")
    if med_sev > 0:
        conflict_score = max(0, conflict_score - med_sev * 2)
    breakdown["conflict_health"] = conflict_score

    # D. Rollback health (max 20 points)
    rolled_back = [e for e in entries if e.get("adoption_status") == ADOPTION_STATUS_ROLLED_BACK]
    rollback_reintro = [
        c for c in conflicts
        if c.get("type") == CONFLICT_ROLLBACK_REINTRODUCTION
    ]

    rollback_score = 20
    if len(rolled_back) > 0:
        rollback_score = max(0, rollback_score - len(rolled_back) * 3)
    if len(rollback_reintro) > 0:
        rollback_score = max(0, rollback_score - len(rollback_reintro) * 5)
        issues.append(f"{len(rollback_reintro)} rollback lineage reintroduction(s)")
    breakdown["rollback_health"] = rollback_score

    # E. Bundle health (max 20 points)
    # Evaluate bundles for all rule combinations (2 rules at a time)
    harmful_bundles = 0
    beneficial_bundles = 0
    rule_ids = [e.get("source_candidate_rule_id") for e in entries if e.get("source_candidate_rule_id")]

    for i in range(len(rule_ids)):
        for j in range(i + 1, len(rule_ids)):
            bundle_eval = evaluate_rule_bundle([rule_ids[i], rule_ids[j]], registry, None, promotion_manager)
            if bundle_eval.get("harmful_interaction"):
                harmful_bundles += 1
            elif not bundle_eval.get("no_added_value"):
                beneficial_bundles += 1

    bundle_score = 20
    if harmful_bundles > 0:
        bundle_score = max(0, bundle_score - harmful_bundles * 4)
        issues.append(f"{harmful_bundles} harmful bundle interaction(s)")
    if beneficial_bundles > 0:
        bundle_score = min(20, bundle_score + min(beneficial_bundles, 3) * 2)
    breakdown["bundle_health"] = bundle_score

    # Total score
    health_score = sum(breakdown.values())

    # Grade
    if health_score >= 90:
        grade = "A"
    elif health_score >= 80:
        grade = "B"
    elif health_score >= 70:
        grade = "C"
    elif health_score >= 60:
        grade = "D"
    else:
        grade = "F"

    return {
        "health_score": health_score,
        "grade": grade,
        "breakdown": breakdown,
        "issues": issues,
        "summary": {
            "total_rules": total_rules,
            "rules_with_provenance": rules_with_provenance,
            "rolled_back_rules": len(rolled_back),
            "conflicts": len(conflicts),
            "harmful_bundles": harmful_bundles,
            "beneficial_bundles": beneficial_bundles,
        },
    }


def get_policy_health(
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Get policy health report (alias for compute_policy_health).

    Args:
        registry: AdoptionRegistry containing rules
        promotion_manager: Optional PromotionManager for bundle context

    Returns:
        Health report dict
    """
    return compute_policy_health(registry, promotion_manager)


# ---------------------------------------------------------------------------
# Step119: Auto-Review Queue
# ---------------------------------------------------------------------------

# Priority level constants
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"

VALID_PRIORITY_LEVELS = (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)

# Priority score thresholds
PRIORITY_THRESHOLD_HIGH = 70
PRIORITY_THRESHOLD_MEDIUM = 40


def compute_review_priority(
    rule_id: str,
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Compute review priority score and reasons for a single rule.

    Args:
        rule_id: The rule ID to evaluate
        registry: AdoptionRegistry containing the rule
        promotion_manager: Optional PromotionManager for additional context

    Returns:
        Priority dict with:
        - rule_id: str
        - priority_score: 0-100
        - priority_level: high/medium/low
        - reasons: list of human-readable reasons
        - signals: dict with detailed signal counts
    """
    entry = registry.get(rule_id)
    if not entry:
        return {
            "rule_id": rule_id,
            "priority_score": 0,
            "priority_level": PRIORITY_LOW,
            "reasons": ["rule not found in registry"],
            "signals": {},
        }

    score = 0
    reasons: List[str] = []
    signals: Dict[str, Any] = {}

    # Get lineage graph
    lineage_graph = build_policy_lineage_graph(registry, promotion_manager)
    node_map = {n["rule_id"]: n for n in lineage_graph["nodes"]}

    # Get conflicts
    conflicts = detect_rule_conflicts(registry, promotion_manager)
    rule_conflicts = [c for c in conflicts if rule_id in c.get("rule_ids", [])]

    # Get health report for context
    health_report = compute_policy_health(registry, promotion_manager)

    # === A. Provenance Risk ===
    prov = entry.get("provenance", {})

    # A1. Missing provenance (heavy)
    if not prov or not prov.get("rule_id"):
        score += 30
        reasons.append("missing provenance")
        signals["missing_provenance"] = True
    else:
        signals["missing_provenance"] = False

        # A2. Source candidate rule ID mismatch (medium-heavy)
        source_id = prov.get("source_candidate_rule_id")
        if source_id and source_id != rule_id:
            # Check if source exists
            if not registry.get(source_id):
                score += 20
                reasons.append("source_candidate_rule_id references non-existent rule")

        # A3. Parent rule ID broken (medium-heavy)
        parent_id = prov.get("parent_rule_id")
        if parent_id:
            if not registry.get(parent_id):
                score += 20
                reasons.append("parent_rule_id references non-existent rule")

    # === B. Lineage Risk ===
    node = node_map.get(rule_id, {})

    # B1. Orphan rule (no parent but has version > 1) (medium)
    if prov.get("rule_version", 1) > 1 and not prov.get("parent_rule_id"):
        score += 15
        reasons.append("orphan rule with version > 1")

    # B2. Deep lineage (medium)
    lineage_depth = _get_lineage_depth(rule_id, lineage_graph)
    signals["lineage_depth"] = lineage_depth
    if lineage_depth > 3:
        score += min(lineage_depth * 5, 20)
        reasons.append(f"deep lineage (depth={lineage_depth})")

    # === C. Conflict Risk ===
    high_sev_conflicts = [c for c in rule_conflicts if c.get("severity") == SEVERITY_HIGH]
    med_sev_conflicts = [c for c in rule_conflicts if c.get("severity") == SEVERITY_MEDIUM]
    low_sev_conflicts = [c for c in rule_conflicts if c.get("severity") == SEVERITY_LOW]

    signals["conflict_count"] = len(rule_conflicts)
    signals["high_severity_conflict_count"] = len(high_sev_conflicts)

    # C1. High severity conflict (heavy)
    if high_sev_conflicts:
        score += 25
        reasons.append("involved in high severity conflict")

    # C2. Medium severity conflict (medium)
    if med_sev_conflicts:
        score += 10
        reasons.append("involved in medium severity conflict")

    # C3. Rollback lineage reintroduction (heavy)
    rollback_reintro = [c for c in rule_conflicts if c.get("type") == CONFLICT_ROLLBACK_REINTRODUCTION]
    if rollback_reintro:
        score += 25
        reasons.append("rollback lineage reintroduction")

    # === D. Rollback Risk ===
    signals["has_rollback_history"] = entry.get("adoption_status") == ADOPTION_STATUS_ROLLED_BACK

    # D1. Currently rolled back (medium-heavy)
    if entry.get("adoption_status") == ADOPTION_STATUS_ROLLED_BACK:
        score += 20
        reasons.append("currently rolled back")

        # D2. Major rollback reason (medium)
        reason_text = entry.get("rollback_reason", "").lower()
        major_keywords = ["critical", "severe", "major", "breaking", "data loss", "security"]
        if any(kw in reason_text for kw in major_keywords):
            score += 15
            reasons.append("major rollback reason")

    # === E. Bundle Risk ===
    entries = registry.list_adopted()
    rule_ids = [e.get("source_candidate_rule_id") for e in entries if e.get("source_candidate_rule_id")]

    harmful_bundle_count = 0
    no_added_value_count = 0

    for other_id in rule_ids:
        if other_id == rule_id:
            continue
        bundle_eval = evaluate_rule_bundle([rule_id, other_id], registry, None, promotion_manager)
        if bundle_eval.get("harmful_interaction"):
            harmful_bundle_count += 1
        elif bundle_eval.get("no_added_value"):
            no_added_value_count += 1

    signals["harmful_bundle_count"] = harmful_bundle_count
    signals["no_added_value_bundle_count"] = no_added_value_count

    # E1. Harmful bundle involvement (medium-heavy)
    if harmful_bundle_count > 0:
        score += min(harmful_bundle_count * 10, 25)
        reasons.append(f"involved in {harmful_bundle_count} harmful bundle(s)")

    # E2. Only no_added_value bundles (light)
    if no_added_value_count > 0 and harmful_bundle_count == 0:
        score += 5
        reasons.append("no added value in bundle interactions")

    # === F. Health Risk ===
    # Check if this rule is a major contributor to health issues
    if rule_id in [r.get("rule_id") for r in node_map.values() if not r.get("provenance")]:
        if health_report.get("health_score", 100) < 80:
            score += 10
            reasons.append("contributing to low policy health")

    # Cap score at 100
    score = min(score, 100)

    # Determine priority level
    if score >= PRIORITY_THRESHOLD_HIGH:
        priority_level = PRIORITY_HIGH
    elif score >= PRIORITY_THRESHOLD_MEDIUM:
        priority_level = PRIORITY_MEDIUM
    else:
        priority_level = PRIORITY_LOW

    return {
        "rule_id": rule_id,
        "priority_score": score,
        "priority_level": priority_level,
        "reasons": reasons,
        "signals": signals,
    }


def _get_lineage_depth(rule_id: str, lineage_graph: Dict[str, Any]) -> int:
    """Calculate lineage depth for a rule (ancestors count)."""
    depth = 0
    node_map = {n["rule_id"]: n for n in lineage_graph["nodes"]}

    current = node_map.get(rule_id)
    visited = {rule_id}

    while current:
        parent_id = current.get("parent_rule_id")
        if not parent_id or parent_id in visited:
            break
        visited.add(parent_id)
        depth += 1
        current = node_map.get(parent_id)

    return depth


def build_review_queue(
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Build a prioritized review queue for all rules in the registry.

    Args:
        registry: AdoptionRegistry containing rules
        promotion_manager: Optional PromotionManager for additional context

    Returns:
        Review queue dict with:
        - review_queue: list of priority items sorted by priority_score desc
        - summary: summary statistics
    """
    entries = registry.list_adopted()
    review_queue: List[Dict[str, Any]] = []

    for entry in entries:
        rule_id = entry.get("source_candidate_rule_id")
        if not rule_id:
            continue

        priority = compute_review_priority(rule_id, registry, promotion_manager)

        # Only include rules with non-zero priority (need review)
        if priority["priority_score"] > 0 or priority["reasons"]:
            review_queue.append(priority)

    # Sort by priority_score descending, then by rule_id for stability
    review_queue.sort(key=lambda x: (-x["priority_score"], x["rule_id"]))

    # Build summary
    high_count = sum(1 for r in review_queue if r["priority_level"] == PRIORITY_HIGH)
    medium_count = sum(1 for r in review_queue if r["priority_level"] == PRIORITY_MEDIUM)
    low_count = sum(1 for r in review_queue if r["priority_level"] == PRIORITY_LOW)

    return {
        "review_queue": review_queue,
        "summary": {
            "total_review_items": len(review_queue),
            "high_priority": high_count,
            "medium_priority": medium_count,
            "low_priority": low_count,
        },
    }


def get_review_queue(
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Get the review queue (alias for build_review_queue).

    Args:
        registry: AdoptionRegistry containing rules
        promotion_manager: Optional PromotionManager for additional context

    Returns:
        Review queue dict
    """
    return build_review_queue(registry, promotion_manager)


# ---------------------------------------------------------------------------
# Step120: Controlled Auto-Evolution Loop
# ---------------------------------------------------------------------------

# Decision type constants
DECISION_AUTO_PROMOTE = "auto_promote"
DECISION_REVIEW_REQUIRED = "review_required"
DECISION_HALT = "halt"
DECISION_ROLLBACK_RECOMMENDED = "rollback_recommended"
DECISION_REJECT = "reject"
DECISION_NO_ACTION = "no_action"

VALID_DECISIONS = (
    DECISION_AUTO_PROMOTE,
    DECISION_REVIEW_REQUIRED,
    DECISION_HALT,
    DECISION_ROLLBACK_RECOMMENDED,
    DECISION_REJECT,
    DECISION_NO_ACTION,
)

# Confidence levels
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

# Thresholds for auto-evolution decisions
HEALTH_THRESHOLD_HALT = 50
HEALTH_THRESHOLD_CAUTION = 70
PRIORITY_THRESHOLD_REVIEW = 40
PRIORITY_THRESHOLD_HALT = 80


def evaluate_auto_evolution_candidate(
    rule_id: str,
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
    health_report: Optional[Dict[str, Any]] = None,
    conflict_report: Optional[Dict[str, Any]] = None,
    review_priority: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate a single rule for auto-evolution decision.

    Args:
        rule_id: The rule ID to evaluate
        registry: AdoptionRegistry containing the rule
        promotion_manager: Optional PromotionManager for additional context
        health_report: Optional pre-computed health report
        conflict_report: Optional pre-computed conflict report
        review_priority: Optional pre-computed review priority

    Returns:
        Decision dict with:
        - rule_id: str
        - decision: auto_promote / review_required / halt / rollback_recommended / reject / no_action
        - confidence: high / medium / low
        - reasons: list of human-readable reasons
        - signals: dict with detailed signal values
    """
    entry = registry.get(rule_id)
    if not entry:
        return {
            "rule_id": rule_id,
            "decision": DECISION_REJECT,
            "confidence": CONFIDENCE_HIGH,
            "reasons": ["rule not found in registry"],
            "signals": {},
        }

    reasons: List[str] = []
    signals: Dict[str, Any] = {}
    confidence = CONFIDENCE_HIGH

    # Get or compute supporting data
    if health_report is None:
        health_report = compute_policy_health(registry, promotion_manager)
    if conflict_report is None:
        conflict_report = build_conflict_report(registry, promotion_manager)
    if review_priority is None:
        review_priority = compute_review_priority(rule_id, registry, promotion_manager)

    # Get rule-specific conflicts
    rule_conflicts = [
        c for c in conflict_report.get("conflicts", [])
        if rule_id in c.get("rule_ids", [])
    ]

    # Get lineage graph
    lineage_graph = build_policy_lineage_graph(registry, promotion_manager)
    node_map = {n["rule_id"]: n for n in lineage_graph["nodes"]}
    node = node_map.get(rule_id, {})

    # === Collect signals ===
    prov = entry.get("provenance", {})
    signals["has_provenance"] = bool(prov and prov.get("rule_id"))
    signals["adoption_status"] = entry.get("adoption_status", "unknown")
    signals["health_score"] = health_report.get("health_score", 100)
    signals["review_priority_score"] = review_priority.get("priority_score", 0)
    signals["review_priority_level"] = review_priority.get("priority_level", PRIORITY_LOW)

    # Conflict signals
    high_sev_conflicts = [c for c in rule_conflicts if c.get("severity") == SEVERITY_HIGH]
    med_sev_conflicts = [c for c in rule_conflicts if c.get("severity") == SEVERITY_MEDIUM]
    rollback_reintro = [c for c in rule_conflicts if c.get("type") == CONFLICT_ROLLBACK_REINTRODUCTION]

    signals["conflict_count"] = len(rule_conflicts)
    signals["high_severity_conflict_count"] = len(high_sev_conflicts)
    signals["medium_severity_conflict_count"] = len(med_sev_conflicts)
    signals["has_rollback_reintroduction"] = len(rollback_reintro) > 0

    # Bundle signals
    entries = registry.list_adopted()
    rule_ids = [e.get("source_candidate_rule_id") for e in entries if e.get("source_candidate_rule_id")]
    
    harmful_bundle_count = 0
    no_added_value_count = 0
    for other_id in rule_ids:
        if other_id == rule_id:
            continue
        bundle_eval = evaluate_rule_bundle([rule_id, other_id], registry, None, promotion_manager)
        if bundle_eval.get("harmful_interaction"):
            harmful_bundle_count += 1
        elif bundle_eval.get("no_added_value"):
            no_added_value_count += 1

    signals["harmful_bundle_count"] = harmful_bundle_count
    signals["no_added_value_bundle_count"] = no_added_value_count

    # Lineage signals
    signals["lineage_depth"] = _get_lineage_depth(rule_id, lineage_graph)
    signals["has_broken_lineage"] = False
    if prov.get("parent_rule_id") and not registry.get(prov.get("parent_rule_id")):
        signals["has_broken_lineage"] = True

    # === Decision logic (conservative - err on the side of caution) ===

    # Decision: REJECT - Rule is ineligible
    if not signals["has_provenance"]:
        return {
            "rule_id": rule_id,
            "decision": DECISION_REJECT,
            "confidence": CONFIDENCE_HIGH,
            "reasons": ["missing provenance - cannot auto-evolve"],
            "signals": signals,
        }

    # Already rolled back - typically no_action or review_required
    if entry.get("adoption_status") == ADOPTION_STATUS_ROLLED_BACK:
        return {
            "rule_id": rule_id,
            "decision": DECISION_NO_ACTION,
            "confidence": CONFIDENCE_HIGH,
            "reasons": ["already rolled back - no action needed"],
            "signals": signals,
        }

    # Decision: HALT - System-wide or critical issues
    halt_reasons = []

    # H1. System health too low
    if signals["health_score"] < HEALTH_THRESHOLD_HALT:
        halt_reasons.append("system health score too low for auto-promotion")
        confidence = CONFIDENCE_MEDIUM

    # H2. High severity conflict
    if signals["high_severity_conflict_count"] > 0:
        halt_reasons.append("involved in high severity conflict(s)")

    # H3. Rollback lineage reintroduction
    if signals["has_rollback_reintroduction"]:
        halt_reasons.append("rollback lineage reintroduction detected")

    # H4. Broken lineage
    if signals["has_broken_lineage"]:
        halt_reasons.append("broken lineage (parent not found)")

    # H5. Very high review priority (someone needs to review this first)
    if signals["review_priority_score"] >= PRIORITY_THRESHOLD_HALT:
        halt_reasons.append("very high review priority - requires manual review")

    if halt_reasons:
        return {
            "rule_id": rule_id,
            "decision": DECISION_HALT,
            "confidence": confidence,
            "reasons": halt_reasons,
            "signals": signals,
        }

    # Decision: ROLLBACK_RECOMMENDED - Already promoted/adopted but harmful
    if signals["adoption_status"] in (ADOPTION_STATUS_ADOPTED, "promoted"):
        rollback_reasons = []

        # R1. Harmful bundles with adopted rule
        if signals["harmful_bundle_count"] >= 2:
            rollback_reasons.append("multiple harmful bundle interactions")

        # R2. Health deteriorating due to this rule
        if signals["health_score"] < HEALTH_THRESHOLD_CAUTION and signals["harmful_bundle_count"] > 0:
            rollback_reasons.append("contributing to low health with harmful bundles")

        # R3. High review priority for adopted rule
        if signals["review_priority_score"] >= PRIORITY_THRESHOLD_HALT:
            rollback_reasons.append("high review priority for active rule")

        if rollback_reasons:
            return {
                "rule_id": rule_id,
                "decision": DECISION_ROLLBACK_RECOMMENDED,
                "confidence": CONFIDENCE_MEDIUM,
                "reasons": rollback_reasons,
                "signals": signals,
            }

    # Decision: REVIEW_REQUIRED - Needs human review before promotion
    review_reasons = []

    # R1. Medium severity conflicts
    if signals["medium_severity_conflict_count"] > 0:
        review_reasons.append("involved in medium severity conflict(s)")

    # R2. Some bundle concerns
    if signals["harmful_bundle_count"] > 0:
        review_reasons.append("involved in harmful bundle(s)")

    # R3. Many no-added-value bundles
    if signals["no_added_value_bundle_count"] >= 2:
        review_reasons.append("multiple no-added-value bundle interactions")

    # R4. Moderate review priority
    if signals["review_priority_score"] >= PRIORITY_THRESHOLD_REVIEW:
        review_reasons.append("moderate review priority")

    # R5. Health score caution zone
    if signals["health_score"] < HEALTH_THRESHOLD_CAUTION:
        review_reasons.append("health score in caution zone")

    # R6. Deep lineage
    if signals["lineage_depth"] > 2:
        review_reasons.append("deep lineage - review recommended")

    if review_reasons:
        return {
            "rule_id": rule_id,
            "decision": DECISION_REVIEW_REQUIRED,
            "confidence": CONFIDENCE_MEDIUM,
            "reasons": review_reasons,
            "signals": signals,
        }

    # Decision: AUTO_PROMOTE - Safe to promote automatically
    auto_promote_reasons = []

    # All checks passed
    if signals["has_provenance"]:
        auto_promote_reasons.append("provenance complete")

    if signals["high_severity_conflict_count"] == 0:
        auto_promote_reasons.append("no high severity conflicts")

    if not signals["has_rollback_reintroduction"]:
        auto_promote_reasons.append("no rollback lineage issues")

    if signals["harmful_bundle_count"] == 0:
        auto_promote_reasons.append("no harmful bundles")

    if signals["review_priority_score"] < PRIORITY_THRESHOLD_REVIEW:
        auto_promote_reasons.append("low review priority")

    if signals["health_score"] >= HEALTH_THRESHOLD_CAUTION:
        auto_promote_reasons.append("health score acceptable")

    return {
        "rule_id": rule_id,
        "decision": DECISION_AUTO_PROMOTE,
        "confidence": CONFIDENCE_HIGH,
        "reasons": auto_promote_reasons,
        "signals": signals,
    }


def run_controlled_auto_evolution(
    registry: AdoptionRegistry,
    rule_ids: Optional[List[str]] = None,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Run controlled auto-evolution analysis for specified rules.

    This is a decision/recommendation engine - it does NOT automatically
    promote or rollback any rules. It provides recommendations based on
    conservative, explainable criteria.

    Args:
        registry: AdoptionRegistry containing rules
        rule_ids: Optional list of rule IDs to evaluate. If None, evaluates all.
        promotion_manager: Optional PromotionManager for additional context

    Returns:
        Auto-evolution report dict with:
        - auto_evolution: list of decision items
        - summary: summary statistics by decision type
    """
    # Pre-compute shared reports for efficiency
    health_report = compute_policy_health(registry, promotion_manager)
    conflict_report = build_conflict_report(registry, promotion_manager)

    # Get rule IDs to evaluate
    if rule_ids is None:
        entries = registry.list_adopted()
        rule_ids = [e.get("source_candidate_rule_id") for e in entries if e.get("source_candidate_rule_id")]

    auto_evolution: List[Dict[str, Any]] = []

    for rule_id in rule_ids:
        if not rule_id:
            continue

        decision = evaluate_auto_evolution_candidate(
            rule_id,
            registry,
            promotion_manager,
            health_report,
            conflict_report,
        )
        auto_evolution.append(decision)

    # Sort by decision priority (halt > rollback > review > auto_promote > no_action > reject)
    decision_order = {
        DECISION_HALT: 0,
        DECISION_ROLLBACK_RECOMMENDED: 1,
        DECISION_REVIEW_REQUIRED: 2,
        DECISION_AUTO_PROMOTE: 3,
        DECISION_NO_ACTION: 4,
        DECISION_REJECT: 5,
    }
    auto_evolution.sort(key=lambda x: (decision_order.get(x["decision"], 99), x["rule_id"]))

    # Build summary
    summary = {
        DECISION_AUTO_PROMOTE: 0,
        DECISION_REVIEW_REQUIRED: 0,
        DECISION_HALT: 0,
        DECISION_ROLLBACK_RECOMMENDED: 0,
        DECISION_REJECT: 0,
        DECISION_NO_ACTION: 0,
    }

    for item in auto_evolution:
        decision = item.get("decision")
        if decision in summary:
            summary[decision] += 1

    return {
        "auto_evolution": auto_evolution,
        "summary": summary,
    }


def build_auto_evolution_report(
    registry: AdoptionRegistry,
    rule_ids: Optional[List[str]] = None,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Build auto-evolution report (alias for run_controlled_auto_evolution).

    Args:
        registry: AdoptionRegistry containing rules
        rule_ids: Optional list of rule IDs to evaluate
        promotion_manager: Optional PromotionManager for additional context

    Returns:
        Auto-evolution report dict
    """
    return run_controlled_auto_evolution(registry, rule_ids, promotion_manager)


def get_auto_evolution_decision(
    registry: AdoptionRegistry,
    rule_ids: Optional[List[str]] = None,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Get auto-evolution decisions (alias for run_controlled_auto_evolution).

    Args:
        registry: AdoptionRegistry containing rules
        rule_ids: Optional list of rule IDs to evaluate
        promotion_manager: Optional PromotionManager for additional context

    Returns:
        Auto-evolution report dict
    """
    return run_controlled_auto_evolution(registry, rule_ids, promotion_manager)


# ---------------------------------------------------------------------------
# Step122: Explainable Decision Report
# ---------------------------------------------------------------------------

def _generate_human_summary(
    decision: str,
    reasons: List[str],
    signals: Dict[str, Any],
) -> str:
    """Generate a human-readable summary for a decision.

    Args:
        decision: The decision type
        reasons: List of reasons for the decision
        signals: Signal values

    Returns:
        Human-readable summary string
    """
    if decision == DECISION_AUTO_PROMOTE:
        return "provenance完備、重大conflictなし、health安定のためauto_promote判定"
    
    elif decision == DECISION_REVIEW_REQUIRED:
        if signals.get("conflict_count", 0) > 0:
            return "conflict検出のためreview_required判定"
        elif signals.get("harmful_bundle_count", 0) > 0:
            return "harmful bundle関与のためreview_required判定"
        elif signals.get("lineage_depth", 0) > 2:
            return "深いlineageのためreview_required判定"
        elif signals.get("no_added_value_bundle_count", 0) >= 2:
            return "複数no_added_value bundleのためreview_required判定"
        else:
            return "中程度の懸念があるためreview_required判定"
    
    elif decision == DECISION_HALT:
        if signals.get("has_rollback_reintroduction"):
            return "rollback系統再導入検出のためhalt判定"
        elif signals.get("high_severity_conflict_count", 0) > 0:
            return "高重大度conflict検出のためhalt判定"
        elif signals.get("has_broken_lineage"):
            return "lineage破損のためhalt判定"
        elif signals.get("health_score", 100) < HEALTH_THRESHOLD_HALT:
            return f"health score ({signals.get('health_score', 0)})が停止閾値未満のためhalt判定"
        elif signals.get("review_priority_score", 0) >= PRIORITY_THRESHOLD_HALT:
            return "非常に高いreview優先度のためhalt判定"
        else:
            return "重大な問題検出のためhalt判定"
    
    elif decision == DECISION_ROLLBACK_RECOMMENDED:
        if signals.get("harmful_bundle_count", 0) >= 2:
            return "複数harmful bundle関与のためrollback推奨"
        elif signals.get("health_score", 100) < HEALTH_THRESHOLD_CAUTION:
            return "health悪化に寄与しているためrollback推奨"
        else:
            return "採用済みruleに重大な問題があるためrollback推奨"
    
    elif decision == DECISION_REJECT:
        if not signals.get("has_provenance", True):
            return "provenance欠損のためreject判定"
        else:
            return "不適格のためreject判定"
    
    elif decision == DECISION_NO_ACTION:
        if signals.get("adoption_status") == "rolled_back":
            return "既にrolled_back状態のためno_action判定"
        else:
            return "対象外のためno_action判定"
    
    else:
        return f"decision={decision}"


def build_decision_explanation(
    rule_id: str,
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Build a comprehensive, explainable decision report for a single rule.

    Args:
        rule_id: The rule ID to explain
        registry: AdoptionRegistry containing the rule
        promotion_manager: Optional PromotionManager for additional context

    Returns:
        Explanation dict with:
        - rule_id: str
        - decision: str
        - confidence: str
        - reasons: list
        - signals: dict
        - provenance: provenance summary
        - lineage: lineage summary
        - conflicts: conflict summary
        - bundle: bundle summary
        - health: health summary
        - review: review priority summary
        - human_summary: str
    """
    entry = registry.get(rule_id)
    if not entry:
        return {
            "rule_id": rule_id,
            "decision": DECISION_REJECT,
            "confidence": CONFIDENCE_HIGH,
            "reasons": ["rule not found in registry"],
            "signals": {},
            "provenance": {},
            "lineage": {},
            "conflicts": {},
            "bundle": {},
            "health": {},
            "review": {},
            "human_summary": "ruleがregistryに存在しないためreject判定",
        }

    # Get the base decision
    decision_result = evaluate_auto_evolution_candidate(rule_id, registry, promotion_manager)
    
    # Extract components
    prov = entry.get("provenance", {})
    
    # Build provenance summary
    provenance_summary = {}
    if prov:
        provenance_summary = {
            "source_candidate_rule_id": prov.get("source_candidate_rule_id"),
            "parent_rule_id": prov.get("parent_rule_id"),
            "created_by": prov.get("created_by"),
            "rule_version": prov.get("rule_version", 1),
            "source_regression_case_count": len(prov.get("source_regression_case_ids", [])),
        }
    
    # Build lineage summary
    lineage_graph = build_policy_lineage_graph(registry, promotion_manager)
    node_map = {n["rule_id"]: n for n in lineage_graph["nodes"]}
    node = node_map.get(rule_id, {})
    lineage_depth = _get_lineage_depth(rule_id, lineage_graph) if node else 0
    
    # Check for rolled-back in lineage
    rolled_back_in_lineage = False
    current = node
    visited = {rule_id}
    while current:
        parent_id = current.get("parent_rule_id")
        if not parent_id or parent_id in visited:
            break
        visited.add(parent_id)
        parent_node = node_map.get(parent_id)
        if parent_node and parent_node.get("stage") == "rolled_back":
            rolled_back_in_lineage = True
            break
        current = parent_node
    
    lineage_summary = {
        "depth": lineage_depth,
        "rolled_back_in_lineage": rolled_back_in_lineage,
        "has_parent": bool(prov.get("parent_rule_id")),
    }
    
    # Build conflict summary
    conflicts = detect_rule_conflicts(registry, promotion_manager)
    rule_conflicts = [c for c in conflicts if rule_id in c.get("rule_ids", [])]
    high_sev_conflicts = [c for c in rule_conflicts if c.get("severity") == SEVERITY_HIGH]
    
    conflict_summary = {
        "total": len(rule_conflicts),
        "high_severity": len(high_sev_conflicts),
        "types": list(set(c.get("type", "unknown") for c in rule_conflicts)),
    }
    
    # Build bundle summary
    entries = registry.list_adopted()
    rule_ids = [e.get("source_candidate_rule_id") for e in entries if e.get("source_candidate_rule_id")]
    
    harmful_count = 0
    no_added_value_count = 0
    for other_id in rule_ids:
        if other_id == rule_id:
            continue
        bundle_eval = evaluate_rule_bundle([rule_id, other_id], registry, None, promotion_manager)
        if bundle_eval.get("harmful_interaction"):
            harmful_count += 1
        elif bundle_eval.get("no_added_value"):
            no_added_value_count += 1
    
    bundle_summary = {
        "harmful_interaction": harmful_count > 0,
        "harmful_bundle_count": harmful_count,
        "no_added_value_bundle_count": no_added_value_count,
    }
    
    # Build health summary
    health_report = compute_policy_health(registry, promotion_manager)
    health_issues = health_report.get("issues", [])
    
    health_summary = {
        "grade": health_report.get("grade"),
        "score": health_report.get("health_score"),
        "issues": health_issues[:5],  # Limit to first 5 issues
    }
    
    # Build review summary
    review_priority = compute_review_priority(rule_id, registry, promotion_manager)
    
    review_summary = {
        "priority_score": review_priority.get("priority_score", 0),
        "priority_level": review_priority.get("priority_level", PRIORITY_LOW),
    }
    
    # Generate human summary
    human_summary = _generate_human_summary(
        decision_result["decision"],
        decision_result["reasons"],
        decision_result["signals"],
    )
    
    return {
        "rule_id": rule_id,
        "decision": decision_result["decision"],
        "confidence": decision_result["confidence"],
        "reasons": decision_result["reasons"],
        "signals": decision_result["signals"],
        "provenance": provenance_summary,
        "lineage": lineage_summary,
        "conflicts": conflict_summary,
        "bundle": bundle_summary,
        "health": health_summary,
        "review": review_summary,
        "human_summary": human_summary,
    }


def build_explainable_decision_report(
    registry: AdoptionRegistry,
    rule_ids: Optional[List[str]] = None,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Build explainable decision reports for multiple rules.

    Args:
        registry: AdoptionRegistry containing rules
        rule_ids: Optional list of rule IDs to explain. If None, explains all.
        promotion_manager: Optional PromotionManager for additional context

    Returns:
        Report dict with:
        - explanations: list of explanation dicts
        - summary: summary statistics by decision type
    """
    if rule_ids is None:
        entries = registry.list_adopted()
        rule_ids = [e.get("source_candidate_rule_id") for e in entries if e.get("source_candidate_rule_id")]
    
    explanations: List[Dict[str, Any]] = []
    
    for rule_id in rule_ids:
        if not rule_id:
            continue
        explanation = build_decision_explanation(rule_id, registry, promotion_manager)
        explanations.append(explanation)
    
    # Sort by decision priority
    decision_order = {
        DECISION_HALT: 0,
        DECISION_ROLLBACK_RECOMMENDED: 1,
        DECISION_REVIEW_REQUIRED: 2,
        DECISION_AUTO_PROMOTE: 3,
        DECISION_NO_ACTION: 4,
        DECISION_REJECT: 5,
    }
    explanations.sort(key=lambda x: (decision_order.get(x["decision"], 99), x["rule_id"]))
    
    # Build summary
    summary = {
        DECISION_AUTO_PROMOTE: 0,
        DECISION_REVIEW_REQUIRED: 0,
        DECISION_HALT: 0,
        DECISION_ROLLBACK_RECOMMENDED: 0,
        DECISION_REJECT: 0,
        DECISION_NO_ACTION: 0,
        "total": len(explanations),
    }
    
    for exp in explanations:
        decision = exp.get("decision")
        if decision in summary:
            summary[decision] += 1
    
    return {
        "explanations": explanations,
        "summary": summary,
    }


def get_decision_explanation(
    registry: AdoptionRegistry,
    rule_ids: Optional[List[str]] = None,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Get decision explanations (alias for build_explainable_decision_report).

    Args:
        registry: AdoptionRegistry containing rules
        rule_ids: Optional list of rule IDs to explain
        promotion_manager: Optional PromotionManager for additional context

    Returns:
        Explanation report dict
    """
    return build_explainable_decision_report(registry, rule_ids, promotion_manager)


# ---------------------------------------------------------------------------
# Step123: Operational Governance Layer
# ---------------------------------------------------------------------------

# Role name constants
ROLE_POLICY_MAINTAINER = "policy_maintainer"
ROLE_SAFETY_REVIEWER = "safety_reviewer"
ROLE_SYSTEM_AUDITOR = "system_auditor"
ROLE_OPERATOR = "operator"

VALID_ROLES = (
    ROLE_POLICY_MAINTAINER,
    ROLE_SAFETY_REVIEWER,
    ROLE_SYSTEM_AUDITOR,
    ROLE_OPERATOR,
)


def get_governance_roles() -> List[Dict[str, Any]]:
    """Get defined human governance roles.

    Returns:
        List of role definitions with:
        - role_name: str
        - responsibilities: list
        - can_approve: list
        - can_block: list
        - review_scope: str
    """
    return [
        {
            "role_name": ROLE_POLICY_MAINTAINER,
            "responsibilities": [
                "review policy change proposals",
                "approve low-risk rule adoptions",
                "monitor policy health trends",
                "maintain policy documentation",
            ],
            "can_approve": [
                "review_required -> adopted",
                "low-risk promotion",
                "minor rule updates",
            ],
            "can_block": [
                "unsafe promotions",
                "rules without provenance",
                "conflicting rule adoptions",
            ],
            "review_scope": "policy evolution and maintenance",
        },
        {
            "role_name": ROLE_SAFETY_REVIEWER,
            "responsibilities": [
                "review high-risk rule changes",
                "approve rollback decisions",
                "assess conflict severity",
                "validate safety-critical changes",
            ],
            "can_approve": [
                "rollback_recommended decisions",
                "halt -> review_required transitions",
                "high severity conflict resolutions",
            ],
            "can_block": [
                "any promotion on safety grounds",
                "rules affecting critical paths",
            ],
            "review_scope": "safety-critical policy decisions",
        },
        {
            "role_name": ROLE_SYSTEM_AUDITOR,
            "responsibilities": [
                "audit policy evolution history",
                "verify governance compliance",
                "review operational metrics",
                "investigate anomalies",
            ],
            "can_approve": [
                "audit reports",
                "compliance certifications",
            ],
            "can_block": [
                "non-compliant promotions",
                "policy changes without audit trail",
            ],
            "review_scope": "governance compliance and audit",
        },
        {
            "role_name": ROLE_OPERATOR,
            "responsibilities": [
                "execute approved promotions",
                "monitor system health",
                "respond to halt conditions",
                "escalate critical issues",
            ],
            "can_approve": [
                "routine maintenance operations",
            ],
            "can_block": [
                "operations during unstable periods",
            ],
            "review_scope": "day-to-day operations",
        },
    ]


def get_promotion_guardrails() -> List[Dict[str, Any]]:
    """Get defined promotion guardrails.

    Returns:
        List of guardrail definitions with:
        - name: str
        - condition: str
        - action: str
        - rationale: str
    """
    return [
        {
            "name": "no_auto_promote_without_provenance",
            "condition": "provenance missing or incomplete",
            "action": "reject auto_promote, require review_required or reject",
            "rationale": "rules without provenance cannot be safely tracked or audited",
        },
        {
            "name": "no_auto_promote_on_high_conflict",
            "condition": "high severity conflict present",
            "action": "halt auto_promote, require halt decision",
            "rationale": "high severity conflicts indicate unsafe rule interactions",
        },
        {
            "name": "no_auto_promote_on_rollback_lineage",
            "condition": "rollback lineage reintroduction detected",
            "action": "halt auto_promote, require halt decision",
            "rationale": "rules from rolled-back lineages have known issues",
        },
        {
            "name": "no_auto_promote_on_harmful_bundle",
            "condition": "harmful bundle interaction detected",
            "action": "block auto_promote, require review_required",
            "rationale": "harmful interactions can cause unintended policy degradation",
        },
        {
            "name": "promoted_requires_human_review",
            "condition": "rule transition to promoted status",
            "action": "require human approval before promotion",
            "rationale": "promotions affect production policy and need human oversight",
        },
        {
            "name": "halt_cannot_auto_clear",
            "condition": "rule in halt state",
            "action": "require explicit human action to clear halt",
            "rationale": "halt indicates serious issues requiring investigation",
        },
        {
            "name": "rollback_requires_confirmation",
            "condition": "rollback_recommended decision",
            "action": "require human confirmation before rollback execution",
            "rationale": "rollbacks have significant impact and need explicit approval",
        },
        {
            "name": "low_risk_only_for_auto_promote",
            "condition": "risk_level not low",
            "action": "require review_required for medium/high risk rules",
            "rationale": "only low-risk rules are candidates for automatic promotion",
        },
    ]


def get_operational_metrics() -> List[Dict[str, Any]]:
    """Get defined operational metrics for policy evolution monitoring.

    Returns:
        List of metric definitions with:
        - metric_name: str
        - description: str
        - interpretation: str
        - risk_signal: str (low/medium/high)
    """
    return [
        {
            "metric_name": "health_score_trend",
            "description": "tracks policy health score over time",
            "interpretation": "falling trend indicates policy degradation; stable or rising is healthy",
            "risk_signal": "medium",
            "calculation": "compare health_score across time periods",
        },
        {
            "metric_name": "conflict_rate",
            "description": "ratio of rules with detected conflicts",
            "interpretation": "high rate indicates policy inconsistency or rule interaction issues",
            "risk_signal": "high",
            "calculation": "rules_with_conflicts / total_rules",
        },
        {
            "metric_name": "rollback_rate",
            "description": "ratio of rolled-back rules to total adopted rules",
            "interpretation": "high rate suggests quality issues in rule generation or review",
            "risk_signal": "high",
            "calculation": "rolled_back_rules / total_adopted_rules",
        },
        {
            "metric_name": "auto_promote_ratio",
            "description": "ratio of auto_promote decisions to total decisions",
            "interpretation": "too high may indicate lax criteria; too low may indicate overly conservative policy",
            "risk_signal": "low",
            "calculation": "auto_promote_count / total_decisions",
        },
        {
            "metric_name": "review_required_ratio",
            "description": "ratio of review_required decisions to total decisions",
            "interpretation": "indicates how many rules need human attention",
            "risk_signal": "medium",
            "calculation": "review_required_count / total_decisions",
        },
        {
            "metric_name": "halt_ratio",
            "description": "ratio of halt decisions to total decisions",
            "interpretation": "high ratio indicates systemic issues requiring investigation",
            "risk_signal": "high",
            "calculation": "halt_count / total_decisions",
        },
        {
            "metric_name": "harmful_bundle_ratio",
            "description": "ratio of rules involved in harmful bundle interactions",
            "interpretation": "indicates rule interaction quality",
            "risk_signal": "high",
            "calculation": "rules_in_harmful_bundles / total_rules",
        },
        {
            "metric_name": "provenance_completeness",
            "description": "ratio of rules with complete provenance",
            "interpretation": "low completeness indicates tracking and audit issues",
            "risk_signal": "medium",
            "calculation": "rules_with_provenance / total_rules",
        },
    ]


def build_operational_governance_policy() -> Dict[str, Any]:
    """Build comprehensive operational governance policy.

    Returns:
        Governance policy dict with:
        - roles: list of governance role definitions
        - guardrails: list of promotion guardrail definitions
        - metrics: list of operational metric definitions
    """
    return {
        "roles": get_governance_roles(),
        "guardrails": get_promotion_guardrails(),
        "metrics": get_operational_metrics(),
    }


def get_governance_policy() -> Dict[str, Any]:
    """Get governance policy (alias for build_operational_governance_policy).

    Returns:
        Governance policy dict
    """
    return build_operational_governance_policy()


def compute_operational_metrics_report(
    registry: AdoptionRegistry,
    promotion_manager: Optional[PromotionManager] = None,
) -> Dict[str, Any]:
    """Compute actual operational metrics values from registry state.

    Args:
        registry: AdoptionRegistry containing rules
        promotion_manager: Optional PromotionManager for additional context

    Returns:
        Metrics report dict with computed values
    """
    entries = registry.list_adopted()
    total_rules = len(entries)
    
    if total_rules == 0:
        return {
            "metrics": {},
            "summary": {
                "total_rules": 0,
                "note": "empty registry",
            },
        }
    
    # Compute health
    health_report = compute_policy_health(registry, promotion_manager)
    
    # Compute conflicts
    conflict_report = build_conflict_report(registry, promotion_manager)
    rules_with_conflicts = set()
    for conflict in conflict_report.get("conflicts", []):
        for rule_id in conflict.get("rule_ids", []):
            rules_with_conflicts.add(rule_id)
    
    # Compute rollbacks
    rolled_back_rules = sum(
        1 for e in entries if e.get("adoption_status") == ADOPTION_STATUS_ROLLED_BACK
    )
    
    # Compute provenance completeness
    rules_with_provenance = sum(
        1 for e in entries if e.get("provenance") and e.get("provenance").get("rule_id")
    )
    
    # Compute harmful bundles
    rule_ids = [e.get("source_candidate_rule_id") for e in entries if e.get("source_candidate_rule_id")]
    rules_in_harmful_bundles = set()
    for i, rule_id in enumerate(rule_ids):
        for other_id in rule_ids[i + 1:]:
            bundle = evaluate_rule_bundle([rule_id, other_id], registry, None, promotion_manager)
            if bundle.get("harmful_interaction"):
                rules_in_harmful_bundles.add(rule_id)
                rules_in_harmful_bundles.add(other_id)
    
    # Compute decision distribution
    evolution_report = run_controlled_auto_evolution(registry, None, promotion_manager)
    decision_summary = evolution_report.get("summary", {})
    total_decisions = sum(decision_summary.values())
    
    # Build metrics report
    metrics = {
        "health_score": health_report.get("health_score", 100),
        "health_grade": health_report.get("grade", "A"),
        "conflict_rate": round(len(rules_with_conflicts) / total_rules, 4) if total_rules > 0 else 0,
        "rollback_rate": round(rolled_back_rules / total_rules, 4) if total_rules > 0 else 0,
        "provenance_completeness": round(rules_with_provenance / total_rules, 4) if total_rules > 0 else 0,
        "harmful_bundle_ratio": round(len(rules_in_harmful_bundles) / total_rules, 4) if total_rules > 0 else 0,
        "total_rules": total_rules,
        "rules_with_conflicts": len(rules_with_conflicts),
        "rolled_back_rules": rolled_back_rules,
        "rules_with_provenance": rules_with_provenance,
    }
    
    if total_decisions > 0:
        metrics["auto_promote_ratio"] = round(
            decision_summary.get(DECISION_AUTO_PROMOTE, 0) / total_decisions, 4
        )
        metrics["review_required_ratio"] = round(
            decision_summary.get(DECISION_REVIEW_REQUIRED, 0) / total_decisions, 4
        )
        metrics["halt_ratio"] = round(
            decision_summary.get(DECISION_HALT, 0) / total_decisions, 4
        )
    
    return {
        "metrics": metrics,
        "summary": {
            "total_rules": total_rules,
            "health_grade": health_report.get("grade", "A"),
            "has_issues": health_report.get("health_score", 100) < 80,
        },
    }

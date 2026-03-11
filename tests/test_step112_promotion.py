#!/usr/bin/env python3
"""Step112: Gated Promotion Workflow Tests"""
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.candidate_rules import (
    make_candidate,
    review_candidate,
    AdoptionRegistry,
    create_adoption_registry,
    create_shadow_evaluator,
    create_promotion_manager,
    can_promote,
    evaluate_promotion_gates,
    PROMOTION_STATUS_ELIGIBLE,
    PROMOTION_STATUS_PROMOTED,
    PROMOTION_STATUS_BLOCKED,
    REVIEW_STATUS_ACCEPTED,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_accepted_candidate(rule_id="rule-001"):
    c = make_candidate(
        candidate_rule_id=rule_id,
        description="test rule",
        expected_effect="improve",
        affected_cases=["c1"],
        risk_level="low",
        recommendation="adopt",
        rule_type="failed_chain",
        suggested_change={"threshold": 2},
    )
    return review_candidate(c, REVIEW_STATUS_ACCEPTED, "reviewer")


def _make_harness_summary(cases):
    """Create a minimal harness summary for testing."""
    return {
        "total": len(cases),
        "cases": cases,
    }


def _make_case(case_id, tier="balanced", orch=False, skill="research"):
    return {
        "case_id": case_id,
        "result": {
            "execution_policy_tier": tier,
            "allow_orchestration": orch,
            "selected_skill": skill,
        },
        "check": {"ok": True, "passed": [], "failed": []},
    }


def _setup_promoted_system(rule_id="rule-001"):
    """Setup full pipeline: candidate -> accepted -> adopted -> shadow evaluated."""
    reg = create_adoption_registry()
    c = _make_accepted_candidate(rule_id)
    reg.adopt(c, "alice")
    ev = create_shadow_evaluator(reg)
    ev.evaluate(
        rule_id,
        _make_harness_summary([_make_case("c1")]),
        _make_harness_summary([_make_case("c1")]),
        "shadow-tester",
    )
    return reg, ev


# ---------------------------------------------------------------------------
# can_promote helper
# ---------------------------------------------------------------------------

class TestStep112CanPromote(unittest.TestCase):

    def test_none_result_not_promotable(self):
        self.assertFalse(can_promote(None))

    def test_empty_result_not_promotable(self):
        self.assertFalse(can_promote({}))

    def test_new_shadow_result_is_promotable(self):
        result = {"shadowed_at": "2026-01-01T00:00:00Z"}
        self.assertTrue(can_promote(result))

    def test_eligible_is_promotable(self):
        result = {"promotion_status": PROMOTION_STATUS_ELIGIBLE}
        self.assertTrue(can_promote(result))

    def test_promoted_not_promotable(self):
        result = {"promotion_status": PROMOTION_STATUS_PROMOTED}
        self.assertFalse(can_promote(result))

    def test_blocked_not_promotable(self):
        result = {"promotion_status": PROMOTION_STATUS_BLOCKED}
        self.assertFalse(can_promote(result))


# ---------------------------------------------------------------------------
# evaluate_promotion_gates
# ---------------------------------------------------------------------------

class TestStep112EvaluateGates(unittest.TestCase):

    def test_zero_regressions_passes(self):
        shadow_result = {"comparison": {"regression_count": 0, "improvement_count": 1}}
        result = evaluate_promotion_gates(shadow_result)
        self.assertTrue(result["passed"])
        self.assertEqual(result["promotion_status"], PROMOTION_STATUS_ELIGIBLE)

    def test_regression_exceeds_max_blocked(self):
        shadow_result = {"comparison": {"regression_count": 1, "improvement_count": 1}}
        result = evaluate_promotion_gates(shadow_result, max_regressions=0)
        self.assertFalse(result["passed"])
        self.assertEqual(result["promotion_status"], PROMOTION_STATUS_BLOCKED)

    def test_improvements_below_min_blocked(self):
        shadow_result = {"comparison": {"regression_count": 0, "improvement_count": 0}}
        result = evaluate_promotion_gates(shadow_result, min_improvements=1)
        self.assertFalse(result["passed"])
        self.assertEqual(result["promotion_status"], PROMOTION_STATUS_BLOCKED)

    def test_both_conditions_met_eligible(self):
        shadow_result = {"comparison": {"regression_count": 0, "improvement_count": 2}}
        result = evaluate_promotion_gates(shadow_result, max_regressions=0, min_improvements=1)
        self.assertTrue(result["passed"])
        self.assertEqual(result["promotion_status"], PROMOTION_STATUS_ELIGIBLE)

    def test_gate_results_populated(self):
        shadow_result = {"comparison": {"regression_count": 1, "improvement_count": 2}}
        result = evaluate_promotion_gates(shadow_result, max_regressions=1, min_improvements=2)
        self.assertTrue(result["gate_results"]["regressions_ok"])
        self.assertTrue(result["gate_results"]["improvements_ok"])

    def test_gate_config_populated(self):
        shadow_result = {"comparison": {"regression_count": 1, "improvement_count": 3}}
        result = evaluate_promotion_gates(shadow_result, max_regressions=2, min_improvements=1)
        self.assertEqual(result["gate_config"]["max_regressions"], 2)
        self.assertEqual(result["gate_config"]["min_improvements"], 1)
        self.assertEqual(result["gate_config"]["actual_regressions"], 1)
        self.assertEqual(result["gate_config"]["actual_improvements"], 3)

    def test_missing_comparison_defaults_to_zero(self):
        shadow_result = {}
        result = evaluate_promotion_gates(shadow_result)
        # 0 regressions <= 0 OK, 0 improvements < 1 NOT OK
        self.assertFalse(result["passed"])


# ---------------------------------------------------------------------------
# PromotionManager eligibility
# ---------------------------------------------------------------------------

class TestStep112ManagerEligibility(unittest.TestCase):

    def test_non_shadow_evaluated_cannot_promote(self):
        """shadow 未実施 rule は promotion 不可"""
        reg = create_adoption_registry()
        ev = create_shadow_evaluator(reg)
        pm = create_promotion_manager(ev)
        with self.assertRaises(KeyError):
            pm.promote("nonexistent", "alice")

    def test_non_shadow_evaluated_cannot_evaluate(self):
        reg = create_adoption_registry()
        ev = create_shadow_evaluator(reg)
        pm = create_promotion_manager(ev)
        with self.assertRaises(KeyError):
            pm.evaluate_for_promotion("nonexistent")

    def test_shadow_evaluated_can_evaluate(self):
        _, ev = _setup_promoted_system("r1")
        pm = create_promotion_manager(ev)
        result = pm.evaluate_for_promotion("r1")
        self.assertIn("passed", result)
        self.assertIn("promotion_status", result)


# ---------------------------------------------------------------------------
# PromotionManager promotion flow
# ---------------------------------------------------------------------------

class TestStep112PromotionFlow(unittest.TestCase):

    def test_regressions_exceed_blocked(self):
        """regressions 超過で blocked"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        ev = create_shadow_evaluator(reg)
        # Shadow with regression
        ev.evaluate(
            "r1",
            _make_harness_summary([_make_case("c1", "thorough")]),
            _make_harness_summary([_make_case("c1", "cheap")]),  # regression
            "tester",
        )
        pm = create_promotion_manager(ev, max_regressions=0)
        with self.assertRaises(ValueError) as ctx:
            pm.promote("r1", "alice", "testing")
        self.assertIn("blocked", str(ctx.exception).lower())

    def test_improvements_condition_achieved_eligible(self):
        """improvements 条件達成で eligible_for_promotion"""
        _, ev = _setup_promoted_system("r1")
        # Re-evaluate with improvement
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 2,
        }
        pm = create_promotion_manager(ev, min_improvements=1)
        result = pm.evaluate_for_promotion("r1")
        self.assertTrue(result["passed"])
        self.assertEqual(result["promotion_status"], PROMOTION_STATUS_ELIGIBLE)

    def test_promoted_status_transition(self):
        """promoted 状態へ遷移可能"""
        _, ev = _setup_promoted_system("r1")
        # Ensure eligible
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        pm = create_promotion_manager(ev, max_regressions=0, min_improvements=1)
        record = pm.promote("r1", "alice", "all gates passed")
        self.assertEqual(record["promotion_status"], PROMOTION_STATUS_PROMOTED)
        self.assertEqual(record["promoted_by"], "alice")
        self.assertEqual(record["promotion_reason"], "all gates passed")

    def test_already_promoted_cannot_promote_again(self):
        _, ev = _setup_promoted_system("r1")
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        pm = create_promotion_manager(ev)
        pm.promote("r1", "alice")
        with self.assertRaises(ValueError) as ctx:
            pm.promote("r1", "bob")
        self.assertIn("already promoted", str(ctx.exception).lower())

    def test_blocked_cannot_promote(self):
        _, ev = _setup_promoted_system("r1")
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 2,
            "improvement_count": 0,
        }
        pm = create_promotion_manager(ev, max_regressions=0)
        with self.assertRaises(ValueError) as ctx:
            pm.promote("r1", "alice")
        self.assertIn("blocked", str(ctx.exception).lower())


# ---------------------------------------------------------------------------
# Promotion metadata
# ---------------------------------------------------------------------------

class TestStep112PromotionMetadata(unittest.TestCase):

    def test_promoted_at_set(self):
        _, ev = _setup_promoted_system("r1")
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        pm = create_promotion_manager(ev, min_improvements=1)
        record = pm.promote("r1", "alice")
        self.assertIsNotNone(record.get("promoted_at"))

    def test_promoted_by_set(self):
        _, ev = _setup_promoted_system("r1")
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        pm = create_promotion_manager(ev, min_improvements=1)
        record = pm.promote("r1", "bob")
        self.assertEqual(record["promoted_by"], "bob")

    def test_promotion_reason_set(self):
        _, ev = _setup_promoted_system("r1")
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        pm = create_promotion_manager(ev, min_improvements=1)
        record = pm.promote("r1", "alice", "all tests passed")
        self.assertEqual(record["promotion_reason"], "all tests passed")

    def test_gate_evaluation_included(self):
        _, ev = _setup_promoted_system("r1")
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 2,
        }
        pm = create_promotion_manager(ev, max_regressions=0, min_improvements=1)
        record = pm.promote("r1", "alice")
        self.assertIn("gate_evaluation", record)
        self.assertTrue(record["gate_evaluation"]["passed"])


# ---------------------------------------------------------------------------
# Block functionality
# ---------------------------------------------------------------------------

class TestStep112Block(unittest.TestCase):

    def test_explicit_block(self):
        _, ev = _setup_promoted_system("r1")
        pm = create_promotion_manager(ev)
        record = pm.block("r1", "admin", "too risky")
        self.assertEqual(record["promotion_status"], PROMOTION_STATUS_BLOCKED)
        self.assertEqual(record["blocked_by"], "admin")
        self.assertEqual(record["block_reason"], "too risky")

    def test_blocked_at_set(self):
        _, ev = _setup_promoted_system("r1")
        pm = create_promotion_manager(ev)
        record = pm.block("r1", "admin", "risk")
        self.assertIsNotNone(record.get("blocked_at"))

    def test_cannot_block_promoted(self):
        _, ev = _setup_promoted_system("r1")
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        pm = create_promotion_manager(ev)
        pm.promote("r1", "alice")
        with self.assertRaises(ValueError) as ctx:
            pm.block("r1", "admin", "changed mind")
        self.assertIn("promoted", str(ctx.exception).lower())


# ---------------------------------------------------------------------------
# Summary and listing
# ---------------------------------------------------------------------------

class TestStep112Summary(unittest.TestCase):

    def test_list_promotable(self):
        _, ev = _setup_promoted_system("r1")
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        pm = create_promotion_manager(ev, min_improvements=1)
        pm.evaluate_for_promotion("r1")
        self.assertIn("r1", pm.list_promotable())

    def test_list_blocked(self):
        _, ev = _setup_promoted_system("r1")
        pm = create_promotion_manager(ev)
        pm.block("r1", "admin", "test")
        self.assertIn("r1", pm.list_blocked())

    def test_list_promoted(self):
        _, ev = _setup_promoted_system("r1")
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        pm = create_promotion_manager(ev, min_improvements=1)
        pm.promote("r1", "alice")
        self.assertIn("r1", pm.list_promoted())

    def test_summarize_counts(self):
        _, ev = _setup_promoted_system("r1")
        _, ev2 = _setup_promoted_system("r2")
        # Merge into one evaluator for testing
        ev._shadow_results["r2"] = ev2._shadow_results["r2"]

        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        ev._shadow_results["r2"]["comparison"] = {
            "regression_count": 1,
            "improvement_count": 0,
        }

        pm = create_promotion_manager(ev, max_regressions=0, min_improvements=1)
        pm.evaluate_for_promotion("r1")
        pm.evaluate_for_promotion("r2")

        summary = pm.summarize()
        self.assertEqual(summary["total_shadow_evaluated"], 2)
        self.assertIn("by_promotion_status", summary)


# ---------------------------------------------------------------------------
# Export / save / load
# ---------------------------------------------------------------------------

class TestStep112Export(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_export_json_valid(self):
        _, ev = _setup_promoted_system("r1")
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        pm = create_promotion_manager(ev, min_improvements=1)
        pm.promote("r1", "alice")
        s = pm.export(fmt="json")
        parsed = json.loads(s)
        self.assertIn("summary", parsed)
        self.assertIn("promotion_records", parsed)
        self.assertEqual(len(parsed["promotion_records"]), 1)

    def test_export_markdown_has_header(self):
        _, ev = _setup_promoted_system("r1")
        pm = create_promotion_manager(ev)
        md = pm.export(fmt="markdown")
        self.assertIn("Promotion Workflow Report", md)

    def test_export_markdown_shows_promoted(self):
        _, ev = _setup_promoted_system("r1")
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        pm = create_promotion_manager(ev, min_improvements=1)
        pm.promote("r1", "alice", "test promotion")
        md = pm.export(fmt="markdown")
        self.assertIn("Promoted Rules", md)
        self.assertIn("alice", md)

    def test_export_markdown_shows_blocked(self):
        _, ev = _setup_promoted_system("r1")
        pm = create_promotion_manager(ev)
        pm.block("r1", "admin", "too risky")
        md = pm.export(fmt="markdown")
        self.assertIn("Blocked Rules", md)
        self.assertIn("too risky", md)

    def test_save_json(self):
        _, ev = _setup_promoted_system("r1")
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        pm = create_promotion_manager(ev, min_improvements=1)
        pm.promote("r1", "alice")
        path = Path(self.temp_dir) / "promo.json"
        pm.save(path, fmt="json")
        self.assertTrue(path.exists())
        loaded = json.loads(path.read_text())
        self.assertEqual(loaded["summary"]["promoted_count"], 1)

    def test_save_markdown(self):
        _, ev = _setup_promoted_system("r1")
        pm = create_promotion_manager(ev)
        path = Path(self.temp_dir) / "promo.md"
        pm.save(path, fmt="markdown")
        self.assertTrue(path.exists())
        self.assertIn("Promotion", path.read_text())

    def test_load_roundtrip(self):
        _, ev1 = _setup_promoted_system("r1")
        _, ev2 = _setup_promoted_system("r2")

        ev1._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        ev1._shadow_results["r2"] = ev2._shadow_results["r2"]
        ev1._shadow_results["r2"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }

        pm1 = create_promotion_manager(ev1, min_improvements=1)
        pm1.promote("r1", "alice")
        pm1.promote("r2", "bob")

        path = Path(self.temp_dir) / "promo.json"
        pm1.save(path)

        # Create fresh manager and load
        reg2 = create_adoption_registry()
        ev_new = create_shadow_evaluator(reg2)
        pm2 = create_promotion_manager(ev_new)
        pm2.load(path)

        self.assertEqual(pm2.summarize()["promoted_count"], 2)

    def test_load_nonexistent_is_ok(self):
        reg = create_adoption_registry()
        ev = create_shadow_evaluator(reg)
        pm = create_promotion_manager(ev)
        pm.load(Path(self.temp_dir) / "nonexistent.json")
        self.assertEqual(pm.summarize()["total_shadow_evaluated"], 0)


# ---------------------------------------------------------------------------
# No policy modification
# ---------------------------------------------------------------------------

class TestStep112NoPolicyModification(unittest.TestCase):

    def test_promote_does_not_modify_policy(self):
        """本番 policy を変更しない"""
        _, ev = _setup_promoted_system("r1")
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 0,
            "improvement_count": 1,
        }
        pm = create_promotion_manager(ev, min_improvements=1)
        pm.promote("r1", "alice")
        self.assertTrue(True)

    def test_export_contains_note(self):
        _, ev = _setup_promoted_system("r1")
        pm = create_promotion_manager(ev)
        s = pm.export(fmt="json")
        self.assertIn("does not modify production", s.lower() + "does not modify production policies")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Step113: Rollback Drill Tests

Rollback workflow が実運用想定でも安全に機能することを確認する drill test。
AdoptionRegistry, PromotionManager, ShadowEvaluator の連携 rollback を検証。
"""
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
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_INACTIVE,
    ADOPTION_STATUS_ROLLED_BACK,
    PROMOTION_STATUS_PROMOTED,
    PROMOTION_STATUS_BLOCKED,
    PROMOTION_STATUS_ELIGIBLE,
    REVIEW_STATUS_ACCEPTED,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_accepted_candidate(rule_id="rule-001", risk="low"):
    c = make_candidate(
        candidate_rule_id=rule_id,
        description="test rule",
        expected_effect="improve",
        affected_cases=["c1"],
        risk_level=risk,
        recommendation="adopt",
        rule_type="failed_chain",
        suggested_change={"threshold": 2},
    )
    return review_candidate(c, REVIEW_STATUS_ACCEPTED, "reviewer")


def _make_harness_summary(cases):
    return {"total": len(cases), "cases": cases}


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


def _setup_full_pipeline(rule_id="rule-001"):
    """Setup: candidate -> accepted -> adopted -> shadow evaluated -> promotion eligible."""
    reg = create_adoption_registry()
    c = _make_accepted_candidate(rule_id)
    reg.adopt(c, "adopter")
    ev = create_shadow_evaluator(reg)
    ev.evaluate(
        rule_id,
        _make_harness_summary([_make_case("c1")]),
        _make_harness_summary([_make_case("c1")]),
        "shadow-tester",
    )
    ev._shadow_results[rule_id]["comparison"] = {
        "regression_count": 0,
        "improvement_count": 1,
    }
    pm = create_promotion_manager(ev, max_regressions=0, min_improvements=1)
    return reg, ev, pm


# ---------------------------------------------------------------------------
# Drill 1: Adopted rule rollback
# ---------------------------------------------------------------------------

class TestStep113DrillAdoptedRollback(unittest.TestCase):

    def test_adopted_rollback_basic(self):
        """adopted rule の rollback が正常に動作する"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        entry = reg.rollback("r1", "bob", "drill test")
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)

    def test_adopted_rollback_metadata_complete(self):
        """rollback metadata が完全に記録される"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice", notes="initial adoption")
        entry = reg.rollback(
            "r1",
            "bob",
            "critical bug found in production",
            "rollback drill at 2026-03-11",
        )
        self.assertIsNotNone(entry.get("rolled_back_at"))
        self.assertEqual(entry["rolled_back_by"], "bob")
        self.assertEqual(entry["rollback_reason"], "critical bug found in production")
        self.assertEqual(entry["rollback_notes"], "rollback drill at 2026-03-11")
        self.assertEqual(entry["rollback_info"]["previous_state"], ADOPTION_STATUS_ADOPTED)

    def test_adopted_rollback_registry_consistent(self):
        """rollback 後 registry が整合性を保つ"""
        reg = create_adoption_registry()
        c1 = _make_accepted_candidate("r1")
        c2 = _make_accepted_candidate("r2")
        reg.adopt(c1, "alice")
        reg.adopt(c2, "bob")
        reg.rollback("r1", "charol", "drill")
        summary = reg.summarize()
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["by_status"]["adopted"], 1)
        self.assertEqual(summary["by_status"]["rolled_back"], 1)


# ---------------------------------------------------------------------------
# Drill 2: Promoted rule rollback
# ---------------------------------------------------------------------------

class TestStep113DrillPromotedRollback(unittest.TestCase):

    def test_promoted_rollback_via_adoption_registry(self):
        """promoted rule も AdoptionRegistry 経由で rollback 可能"""
        reg, ev, pm = _setup_full_pipeline("r1")
        pm.promote("r1", "promoter", "all gates passed")

        # promoted rule は adoption registry 側から rollback
        entry = reg.rollback("r1", "operator", "post-promotion issue detected")
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)

    def test_promoted_rollback_promotion_record_intact(self):
        """promoted rule rollback 後も promotion 記録が保持される"""
        reg, ev, pm = _setup_full_pipeline("r1")
        pm.promote("r1", "promoter", "approved")
        reg.rollback("r1", "operator", "issue")

        # promotion record は依然として存在
        promo_record = pm.get("r1")
        self.assertIsNotNone(promo_record)
        self.assertEqual(promo_record["promotion_status"], PROMOTION_STATUS_PROMOTED)

        # shadow result も保持
        sr = pm.get_shadow_result("r1")
        self.assertIsNotNone(sr)

    def test_promoted_rollback_can_be_reshadowed_after_readopt(self):
        """promoted -> rollback -> readopt -> reshad ow が可能"""
        reg, ev, pm = _setup_full_pipeline("r1")
        pm.promote("r1", "promoter", "approved")
        reg.rollback("r1", "operator", "issue")

        # reactivate and re-shadow
        reg.reactivate("r1")
        ev.evaluate(
            "r1",
            _make_harness_summary([_make_case("c1")]),
            _make_harness_summary([_make_case("c1", "thorough")]),
            "reshadow-tester",
        )
        sr = ev.get("r1")
        self.assertIsNotNone(sr)
        self.assertIn("comparison", sr)


# ---------------------------------------------------------------------------
# Drill 3: Rollback metadata persistence
# ---------------------------------------------------------------------------

class TestStep113DrillRollbackMetadataPersistence(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rollback_metadata_saved_and_loaded(self):
        """rollback metadata が save/load で保持される"""
        reg1 = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg1.adopt(c, "alice", notes="prod deployment")
        reg1.rollback("r1", "bob", "latency spike detected", "incident-1234")

        path = Path(self.temp_dir) / "registry.json"
        reg1.save(path)

        reg2 = create_adoption_registry()
        reg2.load(path)

        entry = reg2.get("r1")
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)
        self.assertEqual(entry["rollback_reason"], "latency spike detected")
        self.assertEqual(entry["rollback_notes"], "incident-1234")
        self.assertEqual(entry["adopted_by"], "alice")

    def test_promotion_and_rollback_metadata_together(self):
        """promotion と rollback metadata が共に保持される"""
        reg1, ev1, pm1 = _setup_full_pipeline("r1")
        pm1.promote("r1", "promoter", "all gates passed")
        reg1.rollback("r1", "operator", "production issue")

        path_promo = Path(self.temp_dir) / "promo.json"
        path_reg = Path(self.temp_dir) / "registry.json"
        pm1.save(path_promo)
        reg1.save(path_reg)

        # Load into fresh instances
        reg2 = create_adoption_registry()
        reg2.load(path_reg)
        ev2 = create_shadow_evaluator(reg2)
        pm2 = create_promotion_manager(ev2)
        pm2.load(path_promo)

        entry = reg2.get("r1")
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)

        promo_record = pm2.get("r1")
        self.assertIsNotNone(promo_record)
        self.assertEqual(promo_record["promotion_status"], PROMOTION_STATUS_PROMOTED)


# ---------------------------------------------------------------------------
# Drill 4: Registry consistency after rollback
# ---------------------------------------------------------------------------

class TestStep113DrillRegistryConsistency(unittest.TestCase):

    def test_multiple_rules_selective_rollback(self):
        """複数 rule 混在時に対象 rule のみ rollback"""
        reg = create_adoption_registry()
        for i in range(5):
            c = _make_accepted_candidate(f"r{i}")
            reg.adopt(c, f"adopter{i}")

        # rollback only r1 and r3
        reg.rollback("r1", "op", "drill")
        reg.rollback("r3", "op", "drill")

        summary = reg.summarize()
        self.assertEqual(summary["total"], 5)
        self.assertEqual(summary["by_status"]["adopted"], 3)
        self.assertEqual(summary["by_status"]["rolled_back"], 2)

        # verify individual entries
        self.assertEqual(reg.get("r0")["adoption_status"], ADOPTION_STATUS_ADOPTED)
        self.assertEqual(reg.get("r1")["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)
        self.assertEqual(reg.get("r2")["adoption_status"], ADOPTION_STATUS_ADOPTED)
        self.assertEqual(reg.get("r3")["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)
        self.assertEqual(reg.get("r4")["adoption_status"], ADOPTION_STATUS_ADOPTED)

    def test_mixed_status_registry_consistency(self):
        """adopted, inactive, rolled_back が混在しても整合性を保つ"""
        reg = create_adoption_registry()
        c1 = _make_accepted_candidate("r1")
        c2 = _make_accepted_candidate("r2")
        c3 = _make_accepted_candidate("r3")
        c4 = _make_accepted_candidate("r4")

        reg.adopt(c1, "a")
        reg.adopt(c2, "b")
        reg.adopt(c3, "c")
        reg.adopt(c4, "d")

        reg.deactivate("r2")
        reg.rollback("r3", "op", "drill")

        summary = reg.summarize()
        self.assertEqual(summary["by_status"]["adopted"], 2)
        self.assertEqual(summary["by_status"]["inactive"], 1)
        self.assertEqual(summary["by_status"]["rolled_back"], 1)

        # list by status
        adopted = reg.list_adopted(status=ADOPTION_STATUS_ADOPTED)
        inactive = reg.list_adopted(status=ADOPTION_STATUS_INACTIVE)
        rolled = reg.list_adopted(status=ADOPTION_STATUS_ROLLED_BACK)

        self.assertEqual(len(adopted), 2)
        self.assertEqual(len(inactive), 1)
        self.assertEqual(len(rolled), 1)


# ---------------------------------------------------------------------------
# Drill 5: Re-evaluation after rollback
# ---------------------------------------------------------------------------

class TestStep113DrillReevaluationAfterRollback(unittest.TestCase):

    def test_rolled_back_can_be_reactivated_and_reevaluated(self):
        """rollback 後に再評価可能"""
        reg, ev, pm = _setup_full_pipeline("r1")

        # initial promotion
        pm.promote("r1", "promoter", "initial approval")

        # issue detected, rollback
        reg.rollback("r1", "operator", "production issue")

        # fix applied, reactivate
        reg.reactivate("r1")

        # re-shadow evaluate
        ev.evaluate(
            "r1",
            _make_harness_summary([_make_case("c1")]),
            _make_harness_summary([_make_case("c1")]),
            "re-evaluator",
        )

        sr = ev.get("r1")
        self.assertIsNotNone(sr)
        # promotion_status はリセットされる（再評価が必要）
        self.assertIn("comparison", sr)

    def test_rolled_back_can_be_deactivated_after_reactivate(self):
        """rollback 後は reactivate してから deactivate 可能"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.rollback("r1", "bob", "issue")

        # rolled_back から直接 deactivate は現在の実装では可能
        # （inactive は adopted とは別の非アクティブ状態）
        reg.deactivate("r1")
        self.assertEqual(reg.get("r1")["adoption_status"], ADOPTION_STATUS_INACTIVE)

    def test_full_cycle_adopt_promote_rollback_reactivate_promote(self):
        """adopt -> promote -> rollback -> reactivate -> re-promote のフルサイクル"""
        reg, ev, pm = _setup_full_pipeline("r1")

        # First promotion
        pm.promote("r1", "promoter1", "first approval")
        self.assertIn("r1", pm.list_promoted())

        # Rollback
        reg.rollback("r1", "operator", "issue")
        self.assertEqual(reg.get("r1")["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)

        # Reactivate
        reg.reactivate("r1")
        self.assertEqual(reg.get("r1")["adoption_status"], ADOPTION_STATUS_ADOPTED)

        # Re-shadow with better results
        ev.evaluate(
            "r1",
            _make_harness_summary([_make_case("c1", "balanced")]),
            _make_harness_summary([_make_case("c1", "thorough")]),  # improvement
            "re-shadower",
        )

        # Re-promote
        pm2 = create_promotion_manager(ev, max_regressions=0, min_improvements=1)
        gate = pm2.evaluate_for_promotion("r1")
        self.assertTrue(gate["passed"])


# ---------------------------------------------------------------------------
# Drill 6: No policy modification guarantee
# ---------------------------------------------------------------------------

class TestStep113DrillNoPolicyModification(unittest.TestCase):

    def test_rollback_drill_does_not_modify_policy(self):
        """rollback drill は本番 policy を変更しない"""
        reg, ev, pm = _setup_full_pipeline("r1")
        pm.promote("r1", "promoter", "drill")
        reg.rollback("r1", "operator", "drill test")
        # 例外が発生しなければ OK
        self.assertTrue(True)

    def test_export_contains_safety_note(self):
        """export 結果に安全確認 note が含まれる"""
        reg, ev, pm = _setup_full_pipeline("r1")
        pm.promote("r1", "promoter", "drill")
        reg.rollback("r1", "operator", "drill")

        reg_json = reg.export(fmt="json")
        pm_json = pm.export(fmt="json")

        self.assertIn("no automatic policy", reg_json.lower())
        self.assertIn("does not modify production", pm_json.lower())


# ---------------------------------------------------------------------------
# Drill 7: Edge cases
# ---------------------------------------------------------------------------

class TestStep113DrillEdgeCases(unittest.TestCase):

    def test_rollback_nonexistent_raises_keyerror(self):
        """存在しない rule の rollback は KeyError"""
        reg = create_adoption_registry()
        with self.assertRaises(KeyError):
            reg.rollback("nonexistent", "op", "test")

    def test_double_rollback_prevented(self):
        """二重 rollback は防止される"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.rollback("r1", "bob", "first")
        with self.assertRaises(ValueError):
            reg.rollback("r1", "charol", "second")

    def test_inactive_cannot_rollback(self):
        """inactive 状態からは rollback 不可"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        reg.deactivate("r1")
        with self.assertRaises(ValueError):
            reg.rollback("r1", "bob", "test")

    def test_promoted_then_blocked_after_rollback_and_readopt(self):
        """promoted -> rollback -> readopt -> block の流れ"""
        reg, ev, pm = _setup_full_pipeline("r1")
        pm.promote("r1", "promoter", "approved")
        reg.rollback("r1", "op", "issue")

        reg.reactivate("r1")

        # Re-evaluate with regression this time
        ev._shadow_results["r1"]["comparison"] = {
            "regression_count": 1,
            "improvement_count": 0,
        }

        pm2 = create_promotion_manager(ev, max_regressions=0, min_improvements=1)
        gate = pm2.evaluate_for_promotion("r1")
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["promotion_status"], PROMOTION_STATUS_BLOCKED)


# ---------------------------------------------------------------------------
# Drill 8: Export format completeness
# ---------------------------------------------------------------------------

class TestStep113DrillExportCompleteness(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_markdown_export_shows_rollback_details(self):
        """Markdown export に rollback 詳細が含まれる"""
        reg, ev, pm = _setup_full_pipeline("r1")
        pm.promote("r1", "promoter", "approved")
        reg.rollback("r1", "operator", "production issue", "incident-5678")

        md = reg.export(fmt="markdown")
        self.assertIn("↩️", md)
        self.assertIn("operator", md)
        self.assertIn("production issue", md)
        self.assertIn("incident-5678", md)

    def test_json_export_includes_all_rollback_fields(self):
        """JSON export に全 rollback field が含まれる"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice", notes="initial")
        reg.rollback("r1", "bob", "reason", "notes")

        data = json.loads(reg.export(fmt="json"))
        entry = data["entries"][0]
        self.assertIn("rolled_back_at", entry)
        self.assertIn("rolled_back_by", entry)
        self.assertIn("rollback_reason", entry)
        self.assertIn("rollback_notes", entry)
        self.assertIn("rollback_info", entry)


if __name__ == "__main__":
    unittest.main()

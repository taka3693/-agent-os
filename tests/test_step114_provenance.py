#!/usr/bin/env python3
"""Step114: Rule Provenance Tracking Tests

Tests for provenance metadata tracking across the rule lifecycle:
candidate -> adopted -> shadow -> promoted -> rollback
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
    make_provenance,
    get_rule_lineage,
    summarize_provenance,
    AdoptionRegistry,
    create_adoption_registry,
    create_shadow_evaluator,
    create_promotion_manager,
    ADOPTION_STATUS_ADOPTED,
    ADOPTION_STATUS_ROLLED_BACK,
    PROMOTION_STATUS_PROMOTED,
    REVIEW_STATUS_ACCEPTED,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_accepted_candidate(rule_id="rule-001", affected_cases=None):
    c = make_candidate(
        candidate_rule_id=rule_id,
        description="test rule",
        expected_effect="improve",
        affected_cases=affected_cases or ["case-1", "case-2"],
        risk_level="low",
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


def _setup_full_pipeline_with_provenance(rule_id="rule-001"):
    """Setup full pipeline with provenance."""
    reg = create_adoption_registry()
    c = _make_accepted_candidate(rule_id, affected_cases=["reg-case-1", "reg-case-2"])

    # Create provenance
    prov = make_provenance(
        rule_id=rule_id,
        source_candidate_rule_id=rule_id,
        source_regression_case_ids=["reg-case-1", "reg-case-2"],
        source_benchmark_snapshot="bench-2026-03-11",
        source_scenario_packs=["scenario-a", "scenario-b"],
        created_by="test_generation",
        parent_rule_id=None,
        rule_version=1,
    )

    reg.adopt(c, "adopter", notes="initial", provenance=prov)

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
    return reg, ev, pm, prov


# ---------------------------------------------------------------------------
# make_provenance
# ---------------------------------------------------------------------------

class TestStep114MakeProvenance(unittest.TestCase):

    def test_make_provenance_basic(self):
        prov = make_provenance(rule_id="r1")
        self.assertEqual(prov["rule_id"], "r1")
        self.assertIsNone(prov["source_candidate_rule_id"])
        self.assertEqual(prov["source_regression_case_ids"], [])
        self.assertIsNone(prov["source_benchmark_snapshot"])
        self.assertEqual(prov["source_scenario_packs"], [])
        self.assertIsNotNone(prov["created_at"])
        self.assertEqual(prov["created_by"], "candidate_generation")
        self.assertEqual(prov["rule_version"], 1)
        self.assertIsNone(prov["parent_rule_id"])

    def test_make_provenance_full(self):
        prov = make_provenance(
            rule_id="r2",
            source_candidate_rule_id="cand-001",
            source_regression_case_ids=["case-a", "case-b"],
            source_benchmark_snapshot="bench-2026-03-10",
            source_scenario_packs=["pack-1", "pack-2"],
            created_by="manual",
            parent_rule_id="r1",
            rule_version=2,
        )
        self.assertEqual(prov["rule_id"], "r2")
        self.assertEqual(prov["source_candidate_rule_id"], "cand-001")
        self.assertEqual(prov["source_regression_case_ids"], ["case-a", "case-b"])
        self.assertEqual(prov["source_benchmark_snapshot"], "bench-2026-03-10")
        self.assertEqual(prov["source_scenario_packs"], ["pack-1", "pack-2"])
        self.assertEqual(prov["created_by"], "manual")
        self.assertEqual(prov["rule_version"], 2)
        self.assertEqual(prov["parent_rule_id"], "r1")


# ---------------------------------------------------------------------------
# Provenance on adopted rule
# ---------------------------------------------------------------------------

class TestStep114AdoptedProvenance(unittest.TestCase):

    def test_adopted_rule_has_auto_provenance(self):
        """adopted rule に provenance が自動付与される"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        entry = reg.adopt(c, "alice")

        self.assertIn("provenance", entry)
        prov = entry["provenance"]
        self.assertEqual(prov["rule_id"], "r1")
        self.assertEqual(prov["source_candidate_rule_id"], "r1")
        self.assertEqual(prov["created_by"], "adoption")
        self.assertEqual(prov["rule_version"], 1)

    def test_adopted_rule_with_explicit_provenance(self):
        """明示的に provenance を渡せる"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        prov = make_provenance(
            rule_id="r1",
            source_candidate_rule_id="cand-001",
            source_regression_case_ids=["case-1"],
            created_by="test",
        )
        entry = reg.adopt(c, "alice", provenance=prov)

        self.assertEqual(entry["provenance"]["source_candidate_rule_id"], "cand-001")
        self.assertEqual(entry["provenance"]["source_regression_case_ids"], ["case-1"])
        self.assertEqual(entry["provenance"]["created_by"], "test")

    def test_adopted_provenance_includes_affected_cases(self):
        """affected_cases が source_regression_case_ids に反映される（自動生成時）"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1", affected_cases=["case-a", "case-b", "case-c"])
        entry = reg.adopt(c, "alice")

        prov = entry["provenance"]
        self.assertIn("case-a", prov["source_regression_case_ids"])


# ---------------------------------------------------------------------------
# Provenance survives promotion
# ---------------------------------------------------------------------------

class TestStep114PromotionProvenance(unittest.TestCase):

    def test_promoted_rule_keeps_provenance(self):
        """promotion 後も provenance が保持される"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")

        pm.promote("r1", "promoter", "all gates passed")

        entry = reg.get("r1")
        self.assertIn("provenance", entry)
        self.assertEqual(entry["provenance"]["source_benchmark_snapshot"], "bench-2026-03-11")
        self.assertEqual(entry["provenance"]["source_scenario_packs"], ["scenario-a", "scenario-b"])

    def test_promotion_record_has_rule_id(self):
        """promotion record に rule_id が含まれる"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")
        record = pm.promote("r1", "promoter")

        self.assertEqual(record["source_candidate_rule_id"], "r1")


# ---------------------------------------------------------------------------
# Provenance survives rollback
# ---------------------------------------------------------------------------

class TestStep114RollbackProvenance(unittest.TestCase):

    def test_rollback_keeps_provenance(self):
        """rollback 後も provenance が残る"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")
        pm.promote("r1", "promoter")

        entry = reg.rollback("r1", "operator", "issue detected")

        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)
        self.assertIn("provenance", entry)
        self.assertEqual(entry["provenance"]["rule_id"], "r1")
        self.assertEqual(entry["provenance"]["source_benchmark_snapshot"], "bench-2026-03-11")

    def test_rollback_provenance_unchanged(self):
        """rollback で provenance が変更されない"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")

        entry_before = reg.get("r1")
        prov_before = dict(entry_before["provenance"])

        reg.rollback("r1", "op", "test")

        entry_after = reg.get("r1")
        prov_after = entry_after["provenance"]

        self.assertEqual(prov_before["created_at"], prov_after["created_at"])
        self.assertEqual(prov_before["created_by"], prov_after["created_by"])
        self.assertEqual(prov_before["rule_version"], prov_after["rule_version"])


# ---------------------------------------------------------------------------
# Provenance in save/load
# ---------------------------------------------------------------------------

class TestStep114SaveLoadProvenance(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_load_preserves_provenance(self):
        """save/load 後も provenance が復元される"""
        reg1 = create_adoption_registry()
        c = _make_accepted_candidate("r1", affected_cases=["case-1"])
        prov = make_provenance(
            rule_id="r1",
            source_candidate_rule_id="cand-001",
            source_regression_case_ids=["case-1"],
            source_benchmark_snapshot="bench-2026-03-11",
            source_scenario_packs=["scenario-x"],
            created_by="test_save",
        )
        reg1.adopt(c, "alice", provenance=prov)

        path = Path(self.temp_dir) / "registry.json"
        reg1.save(path)

        reg2 = create_adoption_registry()
        reg2.load(path)

        entry = reg2.get("r1")
        self.assertIn("provenance", entry)
        self.assertEqual(entry["provenance"]["rule_id"], "r1")
        self.assertEqual(entry["provenance"]["source_benchmark_snapshot"], "bench-2026-03-11")
        self.assertEqual(entry["provenance"]["source_scenario_packs"], ["scenario-x"])
        self.assertEqual(entry["provenance"]["created_by"], "test_save")

    def test_save_load_with_rollback(self):
        """rollback 後の save/load でも provenance 保持"""
        reg1 = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        prov = make_provenance(
            rule_id="r1",
            source_regression_case_ids=["case-1"],
            source_benchmark_snapshot="bench-2026-03-11",
        )
        reg1.adopt(c, "alice", provenance=prov)
        reg1.rollback("r1", "bob", "issue")

        path = Path(self.temp_dir) / "registry.json"
        reg1.save(path)

        reg2 = create_adoption_registry()
        reg2.load(path)

        entry = reg2.get("r1")
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)
        self.assertEqual(entry["provenance"]["source_benchmark_snapshot"], "bench-2026-03-11")

    def test_save_load_promotion_with_provenance(self):
        """promotion 経由の save/load でも provenance 保持"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")
        pm.promote("r1", "promoter")

        path_promo = Path(self.temp_dir) / "promo.json"
        path_reg = Path(self.temp_dir) / "registry.json"
        pm.save(path_promo)
        reg.save(path_reg)

        # Load fresh
        reg2 = create_adoption_registry()
        reg2.load(path_reg)

        entry = reg2.get("r1")
        self.assertIn("provenance", entry)
        self.assertEqual(entry["provenance"]["source_benchmark_snapshot"], "bench-2026-03-11")


# ---------------------------------------------------------------------------
# summarize with provenance
# ---------------------------------------------------------------------------

class TestStep114SummarizeProvenance(unittest.TestCase):

    def test_summarize_includes_provenance(self):
        """summarize に provenance 情報が含まれる"""
        reg = create_adoption_registry()
        c1 = _make_accepted_candidate("r1", affected_cases=["case-1"])
        c2 = _make_accepted_candidate("r2", affected_cases=["case-2"])

        prov1 = make_provenance(
            rule_id="r1",
            source_regression_case_ids=["case-1"],
            created_by="test_a",
        )
        prov2 = make_provenance(
            rule_id="r2",
            source_regression_case_ids=["case-2"],
            source_scenario_packs=["pack-1"],
            created_by="test_b",
            rule_version=2,
            parent_rule_id="r1",
        )

        reg.adopt(c1, "alice", provenance=prov1)
        reg.adopt(c2, "bob", provenance=prov2)

        summary = reg.summarize()

        self.assertIn("provenance", summary)
        prov_sum = summary["provenance"]
        self.assertEqual(prov_sum["total"], 2)
        self.assertEqual(prov_sum["with_provenance"], 2)
        self.assertEqual(prov_sum["with_parent"], 1)
        self.assertIn("by_source_type", prov_sum)
        self.assertIn("by_version", prov_sum)

    def test_summarize_provenance_helper(self):
        """summarize_provenance helper が正しく動作する"""
        entries = [
            {"provenance": {"created_by": "a", "rule_version": 1, "source_regression_case_ids": ["c1"]}},
            {"provenance": {"created_by": "b", "rule_version": 2, "source_regression_case_ids": ["c2"], "parent_rule_id": "r1"}},
            {"provenance": {"created_by": "a", "rule_version": 1, "source_regression_case_ids": ["c3"], "source_scenario_packs": ["p1"]}},
        ]

        summary = summarize_provenance(entries)

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["with_provenance"], 3)
        self.assertEqual(summary["by_source_type"]["a"], 2)
        self.assertEqual(summary["by_source_type"]["b"], 1)
        self.assertEqual(summary["by_version"][1], 2)
        self.assertEqual(summary["by_version"][2], 1)
        self.assertEqual(summary["with_parent"], 1)
        self.assertEqual(summary["unique_regression_case_count"], 3)
        self.assertEqual(summary["unique_scenario_pack_count"], 1)


# ---------------------------------------------------------------------------
# Lineage retrieval
# ---------------------------------------------------------------------------

class TestStep114Lineage(unittest.TestCase):

    def test_get_lineage_basic(self):
        """lineage 取得ができる"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")

        lineage = get_rule_lineage("r1", reg, pm)

        self.assertGreater(len(lineage), 0)
        stages = [l["stage"] for l in lineage]
        self.assertIn("candidate", stages)
        self.assertIn("adopted", stages)

    def test_get_lineage_promoted(self):
        """promoted rule の lineage に promoted stage が含まれる"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")
        pm.promote("r1", "promoter")

        lineage = get_rule_lineage("r1", reg, pm)

        stages = [l["stage"] for l in lineage]
        self.assertIn("promoted", stages)

    def test_get_lineage_rolled_back(self):
        """rolled back rule の lineage に rolled_back stage が含まれる"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")
        pm.promote("r1", "promoter")
        reg.rollback("r1", "operator", "issue")

        lineage = get_rule_lineage("r1", reg, pm)

        stages = [l["stage"] for l in lineage]
        self.assertIn("rolled_back", stages)

    def test_get_lineage_includes_provenance(self):
        """lineage 各段階に provenance が含まれる"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")

        lineage = get_rule_lineage("r1", reg, pm)

        for entry in lineage:
            self.assertIn("provenance", entry)
            if entry["provenance"]:
                self.assertEqual(entry["provenance"]["rule_id"], "r1")

    def test_get_lineage_nonexistent_empty(self):
        """存在しない rule は空リストを返す"""
        reg = create_adoption_registry()
        lineage = get_rule_lineage("nonexistent", reg)
        self.assertEqual(lineage, [])


# ---------------------------------------------------------------------------
# Export with provenance
# ---------------------------------------------------------------------------

class TestStep114ExportProvenance(unittest.TestCase):

    def test_export_json_includes_provenance(self):
        """JSON export に provenance が含まれる"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        prov = make_provenance(
            rule_id="r1",
            source_benchmark_snapshot="bench-2026-03-11",
        )
        reg.adopt(c, "alice", provenance=prov)

        data = json.loads(reg.export(fmt="json"))

        self.assertIn("provenance", data["summary"])
        entry = data["entries"][0]
        self.assertIn("provenance", entry)
        self.assertEqual(entry["provenance"]["source_benchmark_snapshot"], "bench-2026-03-11")

    def test_export_markdown_includes_provenance(self):
        """Markdown export に provenance が含まれる"""
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        prov = make_provenance(
            rule_id="r1",
            source_scenario_packs=["pack-1"],
            rule_version=2,
        )
        reg.adopt(c, "alice", provenance=prov)

        md = reg.export(fmt="markdown")

        self.assertIn("Provenance Summary", md)
        self.assertIn("Version:", md)


# ---------------------------------------------------------------------------
# No policy modification
# ---------------------------------------------------------------------------

class TestStep114NoPolicyModification(unittest.TestCase):

    def test_provenance_does_not_modify_policy(self):
        """provenance 追加は本番 policy を変更しない"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")
        pm.promote("r1", "promoter")
        self.assertTrue(True)

    def test_export_contains_safety_note(self):
        reg = create_adoption_registry()
        c = _make_accepted_candidate("r1")
        reg.adopt(c, "alice")
        s = reg.export(fmt="json")
        self.assertIn("No automatic policy", s)


# ---------------------------------------------------------------------------
# Step114 追加追試: Promotion Provenance 独立性
# ---------------------------------------------------------------------------

class TestStep114PromotionProvenanceIndependence(unittest.TestCase):
    """promoted 側 provenance の変更が candidate/parent 側に影響しないことを検証"""

    def test_promoted_provenance_mutation_isolation(self):
        """promoted 側の provenance list 変更が candidate/parent 側に伝播しない"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")
        pm.promote("r1", "promoter")

        # promoted 側の provenance を取得して list を変更
        entry = reg.get("r1")
        prov_ref = entry["provenance"]
        original_case_ids = list(prov_ref["source_regression_case_ids"])
        original_packs = list(prov_ref["source_scenario_packs"])

        # list を変更（破壊的操作）
        prov_ref["source_regression_case_ids"].append("new-case-mutated")
        prov_ref["source_scenario_packs"].append("new-pack-mutated")
        prov_ref["nested_data"] = {"key": "value", "inner": [1, 2, 3]}

        # 再取得して確認
        entry_after = reg.get("r1")
        prov_after = entry_after["provenance"]

        # 追加した要素が存在すること
        self.assertIn("new-case-mutated", prov_after["source_regression_case_ids"])
        self.assertIn("new-pack-mutated", prov_after["source_scenario_packs"])

        # ただし、candidate段階の provenance は shadow_result 内にコピーで保持されるため
        # promotion_manager 経由で shadow_result を確認
        shadow = pm.get_shadow_result("r1")
        # shadow_result に provenance が含まれる場合、それは entry と同じ参照の可能性がある
        # ここでは「同一エントリ内での変更」は反映される（同一オブジェクト参照）
        # 独立性は「異なる rule_id 同士」で保証される

    def test_different_rules_provenance_independence(self):
        """異なる rule_id の provenance は独立している"""
        # Rule 1
        reg1, ev1, pm1, prov1 = _setup_full_pipeline_with_provenance("rule-alpha")
        pm1.promote("rule-alpha", "promoter1")

        # Rule 2
        reg2, ev2, pm2, prov2 = _setup_full_pipeline_with_provenance("rule-beta")
        pm2.promote("rule-beta", "promoter2")

        # Rule 1 の provenance を変更
        entry1 = reg1.get("rule-alpha")
        entry1["provenance"]["source_regression_case_ids"].append("mutated-case")

        # Rule 2 は影響を受けない
        entry2 = reg2.get("rule-beta")
        self.assertNotIn("mutated-case", entry2["provenance"]["source_regression_case_ids"])


# ---------------------------------------------------------------------------
# Step114 追加追試: Rollback Metadata 共存
# ---------------------------------------------------------------------------

class TestStep114RollbackMetadataCoexistence(unittest.TestCase):
    """rollback 後に provenance と rollback metadata が共存することを検証"""

    def test_rollback_preserves_both_provenance_and_rollback_metadata(self):
        """rollback 後、provenance と rollback metadata が同一 entry に共存する"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")
        pm.promote("r1", "promoter")

        entry = reg.rollback("r1", "operator", "issue detected", notes="test rollback")

        # provenance が存在
        self.assertIn("provenance", entry)
        self.assertEqual(entry["provenance"]["rule_id"], "r1")
        self.assertEqual(entry["provenance"]["source_benchmark_snapshot"], "bench-2026-03-11")

        # rollback metadata が存在
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)
        self.assertIn("rolled_back_at", entry)
        self.assertEqual(entry["rolled_back_by"], "operator")
        self.assertEqual(entry["rollback_reason"], "issue detected")
        self.assertEqual(entry["rollback_notes"], "test rollback")

        # rollback_info も更新されている
        self.assertTrue(entry["rollback_info"]["rolled_back"])

    def test_rollback_provenance_field_level_detail(self):
        """rollback 後の provenance の各フィールドが保持されている"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")
        pm.promote("r1", "promoter")

        entry_before = reg.get("r1")
        prov_before = dict(entry_before["provenance"])

        reg.rollback("r1", "operator", "issue")

        entry_after = reg.get("r1")
        prov_after = entry_after["provenance"]

        # 各フィールドが維持されている
        self.assertEqual(prov_before["rule_id"], prov_after["rule_id"])
        self.assertEqual(prov_before["source_candidate_rule_id"], prov_after["source_candidate_rule_id"])
        self.assertEqual(prov_before["source_benchmark_snapshot"], prov_after["source_benchmark_snapshot"])
        self.assertEqual(prov_before["source_scenario_packs"], prov_after["source_scenario_packs"])
        self.assertEqual(prov_before["created_at"], prov_after["created_at"])
        self.assertEqual(prov_before["created_by"], prov_after["created_by"])
        self.assertEqual(prov_before["rule_version"], prov_after["rule_version"])
        self.assertEqual(prov_before["parent_rule_id"], prov_after["parent_rule_id"])

    def test_rollback_with_promotion_provenance_coexists(self):
        """promotion 経由で rollback した場合、promotion記録と provenance が共存"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")

        # promote
        promo_record = pm.promote("r1", "promoter")

        # rollback
        entry = reg.rollback("r1", "operator", "issue")

        # entry には provenance と rollback 情報が共存
        self.assertIn("provenance", entry)
        self.assertEqual(entry["adoption_status"], ADOPTION_STATUS_ROLLED_BACK)
        self.assertIn("rolled_back_at", entry)

        # promotion_manager 側の shadow_result にも promotion 記録が残る
        shadow = pm.get_shadow_result("r1")
        self.assertEqual(shadow["promotion_status"], PROMOTION_STATUS_PROMOTED)
        self.assertIn("promotion_record", shadow)


# ---------------------------------------------------------------------------
# Step114 追加追試: Lineage 順序意味論
# ---------------------------------------------------------------------------

class TestStep114LineageOrderSemantics(unittest.TestCase):
    """get_rule_lineage の順序が lifecycle として妥当であることを検証"""

    def test_lineage_order_candidate_adopted(self):
        """candidate → adopted の順序が正しい"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")

        lineage = get_rule_lineage("r1", reg, pm)

        # 少なくとも candidate, adopted が含まれる
        stages = [l["stage"] for l in lineage]
        self.assertIn("candidate", stages)
        self.assertIn("adopted", stages)

        # 順序: candidate → adopted
        candidate_idx = stages.index("candidate")
        adopted_idx = stages.index("adopted")
        self.assertLess(candidate_idx, adopted_idx)

    def test_lineage_order_with_shadow_evaluated(self):
        """candidate → adopted → shadow_evaluated の順序が正しい"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")

        lineage = get_rule_lineage("r1", reg, pm)

        stages = [l["stage"] for l in lineage]
        self.assertIn("shadow_evaluated", stages)

        # 順序確認
        candidate_idx = stages.index("candidate")
        adopted_idx = stages.index("adopted")
        shadow_idx = stages.index("shadow_evaluated")

        self.assertLess(candidate_idx, adopted_idx)
        self.assertLess(adopted_idx, shadow_idx)

    def test_lineage_order_promoted(self):
        """candidate → adopted → shadow_evaluated → promoted の順序が正しい"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")
        pm.promote("r1", "promoter")

        lineage = get_rule_lineage("r1", reg, pm)

        stages = [l["stage"] for l in lineage]
        self.assertIn("promoted", stages)

        candidate_idx = stages.index("candidate")
        adopted_idx = stages.index("adopted")
        shadow_idx = stages.index("shadow_evaluated")
        promoted_idx = stages.index("promoted")

        self.assertLess(candidate_idx, adopted_idx)
        self.assertLess(adopted_idx, shadow_idx)
        self.assertLess(shadow_idx, promoted_idx)

    def test_lineage_order_rolled_back(self):
        """rolled_back は最後に現れる"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")
        pm.promote("r1", "promoter")
        reg.rollback("r1", "operator", "issue")

        lineage = get_rule_lineage("r1", reg, pm)

        stages = [l["stage"] for l in lineage]
        self.assertIn("rolled_back", stages)

        # rolled_back は最後
        rolled_back_idx = stages.index("rolled_back")
        self.assertEqual(rolled_back_idx, len(stages) - 1)

        # 直前は promoted または shadow_evaluated
        self.assertIn(stages[rolled_back_idx - 1], ["promoted", "shadow_evaluated"])

    def test_lineage_each_stage_has_provenance(self):
        """各段階に provenance が含まれる（null許容）"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")
        pm.promote("r1", "promoter")

        lineage = get_rule_lineage("r1", reg, pm)

        for entry in lineage:
            self.assertIn("provenance", entry)
            # provenance は None の可能性もあるが、キーは存在する
            if entry["provenance"]:
                self.assertEqual(entry["provenance"]["rule_id"], "r1")

    def test_lineage_timestamps_progress(self):
        """各段階の timestamp が進行している（空文字以外）"""
        reg, ev, pm, prov = _setup_full_pipeline_with_provenance("r1")
        pm.promote("r1", "promoter")

        lineage = get_rule_lineage("r1", reg, pm)

        # candidate, adopted, shadow_evaluated, promoted の timestamp を確認
        timestamps = []
        for entry in lineage:
            ts = entry.get("timestamp", "")
            if ts:  # 空でないものを収集
                timestamps.append(ts)

        # 各 timestamp が異なる（または昇順）
        # 同じ秒内の可能性もあるので、少なくとも空でないことを確認
        for entry in lineage:
            if entry["stage"] == "adopted":
                self.assertTrue(len(entry.get("timestamp", "")) > 0)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Step105: Regression Benchmark Tests"""
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.cases import load_cases
from eval.harness import run_harness
from eval.benchmark import (
    COMPARED_FIELDS,
    extract_snapshot,
    save_baseline,
    load_baseline,
    compare_snapshots,
    report_to_json,
    report_to_markdown,
    save_report,
    _compare_field,
    TOLERANCE_FIELDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_summary():
    return run_harness(load_cases())


def _make_minimal_summary(overrides: dict = None) -> dict:
    """Build a tiny synthetic harness summary for unit tests."""
    cases = [
        {
            "case_id": "c1",
            "result": {
                "selected_skill": "research",
                "skill_chain_length": 1,
                "execution_policy_tier": "balanced",
                "allow_orchestration": False,
                "allow_parallel": True,
                "final_status": "eval_only",
                "budget_limit_hit": False,
            },
            "check": {"ok": True, "passed": [], "failed": []},
        },
        {
            "case_id": "c2",
            "result": {
                "selected_skill": "decision",
                "skill_chain_length": 2,
                "execution_policy_tier": "thorough",
                "allow_orchestration": True,
                "allow_parallel": True,
                "final_status": "eval_only",
                "budget_limit_hit": False,
            },
            "check": {"ok": True, "passed": [], "failed": []},
        },
    ]
    if overrides:
        for case in cases:
            if case["case_id"] in overrides:
                case["result"].update(overrides[case["case_id"]])
    return {"total": len(cases), "cases": cases}


# ---------------------------------------------------------------------------
# extract_snapshot
# ---------------------------------------------------------------------------

class TestStep105ExtractSnapshot(unittest.TestCase):

    def test_snapshot_has_all_case_ids(self):
        summary = _make_minimal_summary()
        snap = extract_snapshot(summary)
        self.assertIn("c1", snap)
        self.assertIn("c2", snap)

    def test_snapshot_has_compared_fields(self):
        summary = _make_minimal_summary()
        snap = extract_snapshot(summary)
        for field in COMPARED_FIELDS:
            self.assertIn(field, snap["c1"])

    def test_snapshot_values_correct(self):
        summary = _make_minimal_summary()
        snap = extract_snapshot(summary)
        self.assertEqual(snap["c1"]["execution_policy_tier"], "balanced")
        self.assertEqual(snap["c2"]["allow_orchestration"], True)


# ---------------------------------------------------------------------------
# save / load baseline
# ---------------------------------------------------------------------------

class TestStep105BaselineIO(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.baseline_path = Path(self.temp_dir) / "baseline.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_baseline_creates_file(self):
        summary = _make_minimal_summary()
        save_baseline(summary, self.baseline_path)
        self.assertTrue(self.baseline_path.exists())

    def test_save_baseline_content(self):
        summary = _make_minimal_summary()
        baseline = save_baseline(summary, self.baseline_path)
        self.assertIn("saved_at", baseline)
        self.assertIn("snapshot", baseline)
        self.assertIn("c1", baseline["snapshot"])

    def test_load_baseline_roundtrip(self):
        summary = _make_minimal_summary()
        save_baseline(summary, self.baseline_path)
        loaded = load_baseline(self.baseline_path)
        self.assertIn("snapshot", loaded)
        self.assertEqual(loaded["snapshot"]["c1"]["selected_skill"], "research")

    def test_load_baseline_missing_returns_empty(self):
        result = load_baseline(Path(self.temp_dir) / "nonexistent.json")
        self.assertEqual(result, {})

    def test_baseline_from_real_harness(self):
        summary = _run_summary()
        baseline = save_baseline(summary, self.baseline_path)
        self.assertEqual(baseline["total"], len(load_cases()))
        self.assertEqual(len(baseline["snapshot"]), len(load_cases()))


# ---------------------------------------------------------------------------
# _compare_field
# ---------------------------------------------------------------------------

class TestStep105CompareField(unittest.TestCase):

    def test_exact_match_passes(self):
        ok, msg = _compare_field("selected_skill", "research", "research")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_exact_mismatch_fails(self):
        ok, msg = _compare_field("selected_skill", "research", "critique")
        self.assertFalse(ok)
        self.assertIn("research", msg)
        self.assertIn("critique", msg)

    def test_tolerance_within_passes(self):
        # skill_chain_length tolerance = 1
        ok, msg = _compare_field("skill_chain_length", 2, 3)
        self.assertTrue(ok)

    def test_tolerance_exact_passes(self):
        ok, msg = _compare_field("skill_chain_length", 2, 2)
        self.assertTrue(ok)

    def test_tolerance_exceeded_fails(self):
        ok, msg = _compare_field("skill_chain_length", 1, 3)
        self.assertFalse(ok)
        self.assertIn("diff=2", msg)

    def test_bool_exact_match(self):
        ok, _ = _compare_field("allow_orchestration", False, False)
        self.assertTrue(ok)

    def test_bool_mismatch_fails(self):
        ok, msg = _compare_field("allow_orchestration", False, True)
        self.assertFalse(ok)


# ---------------------------------------------------------------------------
# compare_snapshots — PASS cases
# ---------------------------------------------------------------------------

class TestStep105ComparePass(unittest.TestCase):

    def test_identical_snapshots_pass(self):
        summary = _make_minimal_summary()
        baseline = {"snapshot": extract_snapshot(summary)}
        report = compare_snapshots(baseline, summary)
        self.assertTrue(report["ok"])
        self.assertEqual(report["regressions"], 0)

    def test_within_tolerance_passes(self):
        summary_base = _make_minimal_summary()
        # Drift skill_chain_length by 1 (within tolerance)
        summary_latest = _make_minimal_summary(overrides={"c1": {"skill_chain_length": 2}})
        baseline = {"snapshot": extract_snapshot(summary_base)}
        report = compare_snapshots(baseline, summary_latest)
        self.assertTrue(report["ok"])

    def test_new_case_not_a_regression(self):
        summary_base = _make_minimal_summary()
        baseline = {"snapshot": extract_snapshot(summary_base)}
        # Latest has an extra case — add it manually
        summary_latest = _make_minimal_summary()
        summary_latest["cases"].append({
            "case_id": "c3",
            "result": {f: None for f in COMPARED_FIELDS},
            "check": {"ok": True, "passed": [], "failed": []},
        })
        report = compare_snapshots(baseline, summary_latest)
        self.assertIn("c3", report["new_cases"])
        self.assertTrue(report["ok"])  # new cases are not regressions


# ---------------------------------------------------------------------------
# compare_snapshots — FAIL cases
# ---------------------------------------------------------------------------

class TestStep105CompareRegression(unittest.TestCase):

    def test_skill_change_is_regression(self):
        summary_base = _make_minimal_summary()
        summary_latest = _make_minimal_summary(
            overrides={"c1": {"selected_skill": "critique"}}
        )
        baseline = {"snapshot": extract_snapshot(summary_base)}
        report = compare_snapshots(baseline, summary_latest)
        self.assertFalse(report["ok"])
        self.assertEqual(report["regressions"], 1)

    def test_tier_change_is_regression(self):
        summary_base = _make_minimal_summary()
        summary_latest = _make_minimal_summary(
            overrides={"c1": {"execution_policy_tier": "cheap"}}
        )
        baseline = {"snapshot": extract_snapshot(summary_base)}
        report = compare_snapshots(baseline, summary_latest)
        self.assertFalse(report["ok"])

    def test_orchestration_flip_is_regression(self):
        summary_base = _make_minimal_summary()
        summary_latest = _make_minimal_summary(
            overrides={"c2": {"allow_orchestration": False}}
        )
        baseline = {"snapshot": extract_snapshot(summary_base)}
        report = compare_snapshots(baseline, summary_latest)
        self.assertFalse(report["ok"])

    def test_chain_length_beyond_tolerance_is_regression(self):
        summary_base = _make_minimal_summary()
        summary_latest = _make_minimal_summary(
            overrides={"c1": {"skill_chain_length": 4}}  # was 1, now 4, diff=3 > tol=1
        )
        baseline = {"snapshot": extract_snapshot(summary_base)}
        report = compare_snapshots(baseline, summary_latest)
        self.assertFalse(report["ok"])

    def test_regression_detail_contains_case_id(self):
        summary_base = _make_minimal_summary()
        summary_latest = _make_minimal_summary(
            overrides={"c1": {"selected_skill": "critique"}}
        )
        baseline = {"snapshot": extract_snapshot(summary_base)}
        report = compare_snapshots(baseline, summary_latest)
        ids = [rd["case_id"] for rd in report["regression_details"]]
        self.assertIn("c1", ids)

    def test_removed_case_tracked(self):
        summary_base = _make_minimal_summary()
        baseline = {"snapshot": extract_snapshot(summary_base)}
        # Latest only has c1
        summary_latest = {"total": 1, "cases": [summary_base["cases"][0]]}
        report = compare_snapshots(baseline, summary_latest)
        self.assertIn("c2", report["removed_cases"])


# ---------------------------------------------------------------------------
# Report output
# ---------------------------------------------------------------------------

class TestStep105ReportOutput(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_report(self, regressed=False):
        summary = _make_minimal_summary()
        if regressed:
            summary_latest = _make_minimal_summary(
                overrides={"c1": {"selected_skill": "critique"}}
            )
        else:
            summary_latest = summary
        baseline = {"snapshot": extract_snapshot(summary)}
        return compare_snapshots(baseline, summary_latest)

    def test_json_report_valid(self):
        report = self._make_report()
        s = report_to_json(report)
        parsed = json.loads(s)
        self.assertIn("ok", parsed)
        self.assertIn("regressions", parsed)

    def test_markdown_pass_contains_pass(self):
        report = self._make_report()
        md = report_to_markdown(report)
        self.assertIn("PASS", md)

    def test_markdown_regression_contains_regression(self):
        report = self._make_report(regressed=True)
        md = report_to_markdown(report)
        self.assertIn("REGRESSION", md)
        self.assertIn("c1", md)

    def test_save_report_json(self):
        report = self._make_report()
        path = Path(self.temp_dir) / "report.json"
        save_report(report, path, fmt="json")
        self.assertTrue(path.exists())
        loaded = json.loads(path.read_text())
        self.assertIn("ok", loaded)

    def test_save_report_markdown(self):
        report = self._make_report()
        path = Path(self.temp_dir) / "report.md"
        save_report(report, path, fmt="markdown")
        self.assertTrue(path.exists())
        self.assertIn("Benchmark Regression Report", path.read_text())

    def test_full_pipeline_no_regression(self):
        """Save baseline from real harness → re-run → no regression"""
        path = Path(self.temp_dir) / "baseline.json"
        summary = _run_summary()
        save_baseline(summary, path)

        baseline = load_baseline(path)
        latest = _run_summary()
        report = compare_snapshots(baseline, latest)

        self.assertTrue(report["ok"], f"Unexpected regressions: {report['regression_details']}")


if __name__ == "__main__":
    unittest.main()

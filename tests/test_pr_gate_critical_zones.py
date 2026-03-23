from tools import pr_gate
import io
import json
import sys
from contextlib import redirect_stdout


def _run_main_with(monkeypatch, changed_files, diff_summary, blocked_deletions=None):
    blocked_deletions = blocked_deletions or []

    monkeypatch.setattr(pr_gate, "load_policy", lambda: {
        "protected_paths": ["tools/", "config/"]
    })
    monkeypatch.setattr(pr_gate, "get_changed_files", lambda repo, branch, base: changed_files)
    monkeypatch.setattr(pr_gate, "get_diff_summary", lambda repo, branch, base: diff_summary)
    monkeypatch.setattr(pr_gate, "detect_blocked_deletions", lambda base, branch: blocked_deletions)
    monkeypatch.setattr(
        pr_gate,
        "assess_risk",
        lambda changed_files, diff_summary, policy, blocked_deletions=None: "low",
    )
    monkeypatch.setattr(pr_gate, "check_syntax", lambda: "pass")
    monkeypatch.setattr(pr_gate, "check_tests", lambda: "pass")
    monkeypatch.setattr(pr_gate, "check_freshness", lambda: "unknown")
    monkeypatch.setattr(pr_gate, "generate_pr_title", lambda branch, changed_files: "title")
    monkeypatch.setattr(pr_gate, "generate_pr_body", lambda changed_files, diff_summary, risk_level: "body")
    monkeypatch.setattr(pr_gate, "generate_pr_url", lambda repo, branch, base: "url")
    monkeypatch.setattr(
        pr_gate,
        "generate_create_pr_command",
        lambda repo, branch, base, pr_title, pr_body: "cmd",
    )
    monkeypatch.setattr(
        pr_gate,
        "generate_manual_review_checklist",
        lambda changed_files, protected_paths, risk_level: [],
    )
    monkeypatch.setattr(pr_gate, "build_checklist", lambda **kwargs: ["check"])
    monkeypatch.setattr(pr_gate, "save_state", lambda result: "/tmp/pr_gate_state.json")

    old_argv = sys.argv[:]
    sys.argv = [
        "pr_gate.py",
        "--repo", "demo/repo",
        "--branch", "feature/test",
        "--base", "main",
    ]
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            pr_gate.main()
    finally:
        sys.argv = old_argv

    return json.loads(buf.getvalue())


def test_workflow_change_requires_maintainer_review(monkeypatch):
    data = _run_main_with(
        monkeypatch,
        changed_files=[".github/workflows/pr-gate.yml"],
        diff_summary={"files": 1, "additions": 5, "deletions": 1, "deleted_files": []},
    )
    assert "maintainer_review" in data["approval_requirements"]


def test_config_change_requires_maintainer_review(monkeypatch):
    data = _run_main_with(
        monkeypatch,
        changed_files=["config/app.yaml"],
        diff_summary={"files": 1, "additions": 3, "deletions": 0, "deleted_files": []},
    )
    assert "maintainer_review" in data["approval_requirements"]

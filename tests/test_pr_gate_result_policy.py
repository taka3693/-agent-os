from tools import pr_gate
import io
import json
import sys
from contextlib import redirect_stdout


def test_result_policy_adds_warning_and_approval_for_unjustified_deletion(monkeypatch):
    monkeypatch.setattr(pr_gate, "load_policy", lambda: {
        "protected_paths": ["tools/", "config/"]
    })
    monkeypatch.setattr(pr_gate, "get_changed_files", lambda repo, branch, base: [
        "docs/readme.md"
    ])
    monkeypatch.setattr(pr_gate, "get_diff_summary", lambda repo, branch, base: {
        "files": 1,
        "additions": 0,
        "deletions": 5,
        "deleted_files": ["docs/readme.md"],
    })
    monkeypatch.setattr(pr_gate, "detect_blocked_deletions", lambda base, branch: [])
    monkeypatch.setattr(
        pr_gate,
        "assess_risk",
        lambda changed_files, diff_summary, policy, blocked_deletions=None: "high",
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
        "--change-context", "delete without marker",
    ]

    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            pr_gate.main()
    finally:
        sys.argv = old_argv

    data = json.loads(buf.getvalue())

    assert "deletions_without_justification" in data["warnings"]
    assert "deletion_justification" in data["approval_requirements"]
    assert data["merge_recommendation"] == "hard_block"

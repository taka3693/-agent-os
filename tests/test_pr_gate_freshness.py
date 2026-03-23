from tools.pr_gate import _check_freshness_impl


def test_check_freshness_pass_when_branch_not_far_behind(monkeypatch):
    monkeypatch.setattr(
        "tools.pr_gate.get_branch_divergence",
        lambda repo, branch, base: {"behind_by": 3, "ahead_by": 1},
    )
    assert _check_freshness_impl("demo/repo", "feature/x", "main") == "pass"


def test_check_freshness_fail_when_branch_far_behind(monkeypatch):
    monkeypatch.setattr(
        "tools.pr_gate.get_branch_divergence",
        lambda repo, branch, base: {"behind_by": 25, "ahead_by": 1},
    )
    assert _check_freshness_impl("demo/repo", "feature/x", "main") == "fail"


def test_check_freshness_unknown_on_error(monkeypatch):
    def boom(repo, branch, base):
        raise RuntimeError("git failed")

    monkeypatch.setattr("tools.pr_gate.get_branch_divergence", boom)
    assert _check_freshness_impl("demo/repo", "feature/x", "main") == "unknown"

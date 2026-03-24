#!/usr/bin/env python3
"""
merge_pr.py - approved / low risk PR を安全条件付きで merge する
"""
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Any, Dict


def load_state(state_file: str) -> Dict[str, Any]:
    path = Path(state_file)
    if not path.exists():
        return {"ok": False, "status": "merge_blocked", "reason": "state_not_found", "state_file": state_file}
    return json.loads(path.read_text())


def save_state(state: Dict[str, Any]) -> None:
    state_file = Path(state.get("state_file", ""))
    if state_file.exists():
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def block(reason: str, state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": False,
        "status": "merge_blocked",
        "reason": reason,
        "state_file": state.get("state_file")
    }


def get_pr_info(branch: str) -> Dict[str, Any]:
    result = subprocess.run(
        [
            "gh", "pr", "view", branch,
            "--json",
            "number,title,url,state,isDraft,mergeable,reviewDecision,statusCheckRollup,headRefName,baseRefName"
        ],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        return {"ok": False, "stderr": result.stderr, "stdout": result.stdout}
    try:
        return {"ok": True, "data": json.loads(result.stdout)}
    except json.JSONDecodeError:
        return {"ok": False, "stderr": "invalid_pr_json", "stdout": result.stdout}


def checks_state(pr: Dict[str, Any]) -> str:
    rollup = pr.get("statusCheckRollup") or []
    if not rollup:
        return "pass"
    states = []
    for item in rollup:
        st = item.get("state") or item.get("conclusion") or ""
        if st:
            states.append(str(st).upper())
    if any(s in {"FAILURE", "FAILED", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"} for s in states):
        return "failed"
    if any(s in {"PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", "WAITING"} for s in states):
        return "pending"
    return "pass"


def do_merge(pr_number: int) -> Dict[str, Any]:
    result = subprocess.run(
        ["gh", "pr", "merge", str(pr_number), "--squash", "--delete-branch"],
        capture_output=True,
        text=True
    )
    return {
        "ok": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Merge PR safely")
    parser.add_argument("--state", required=True, help="State file path")
    args = parser.parse_args()

    state = load_state(args.state)
    if not state.get("ok", True):
        print(json.dumps(state, ensure_ascii=False, indent=2))
        sys.exit(1)

    if state.get("status") != "approved":
        print(json.dumps(block("not_approved", state), ensure_ascii=False, indent=2))
        sys.exit(1)

    if state.get("risk_level") != "low":
        print(json.dumps(block("risk_not_low", state), ensure_ascii=False, indent=2))
        sys.exit(1)

    if state.get("base") != "main":
        print(json.dumps(block("base_not_main", state), ensure_ascii=False, indent=2))
        sys.exit(1)

    if not state.get("merge_allowed", False):
        print(json.dumps(block("merge_not_allowed", state), ensure_ascii=False, indent=2))
        sys.exit(1)

    pr_view = get_pr_info(state.get("branch", ""))
    if not pr_view.get("ok"):
        result = {
            "ok": False,
            "status": "merge_blocked",
            "reason": "pr_not_found",
            "stderr": pr_view.get("stderr"),
            "state_file": state.get("state_file")
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)

    pr = pr_view["data"]

    if pr.get("isDraft"):
        print(json.dumps(block("draft_pr", state), ensure_ascii=False, indent=2))
        sys.exit(1)

    if str(pr.get("mergeable", "")).upper() not in {"MERGEABLE", "MERGING"}:
        print(json.dumps(block("not_mergeable", state), ensure_ascii=False, indent=2))
        sys.exit(1)

    review = str(pr.get("reviewDecision") or "").upper()
    if review == "REVIEW_REQUIRED":
        print(json.dumps(block("review_required", state), ensure_ascii=False, indent=2))
        sys.exit(1)
    if review == "CHANGES_REQUESTED":
        print(json.dumps(block("changes_requested", state), ensure_ascii=False, indent=2))
        sys.exit(1)

    checks = checks_state(pr)
    if checks == "failed":
        print(json.dumps(block("checks_failed", state), ensure_ascii=False, indent=2))
        sys.exit(1)
    if checks == "pending":
        print(json.dumps(block("checks_pending", state), ensure_ascii=False, indent=2))
        sys.exit(1)

    merged = do_merge(pr["number"])
    if not merged["ok"]:
        result = {
            "ok": False,
            "status": "merge_failed",
            "reason": "gh_merge_failed",
            "stderr": merged.get("stderr"),
            "stdout": merged.get("stdout"),
            "state_file": state.get("state_file")
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)

    state["merge_executed"] = True
    state["merge_result"] = "merged"
    state["merged_at"] = datetime.now().isoformat()
    state["merge_method"] = "squash"
    state["pr_number"] = pr["number"]
    state["pr_url"] = pr["url"]
    save_state(state)

    result = {
        "ok": True,
        "status": "merged",
        "pr_number": pr["number"],
        "pr_url": pr["url"],
        "merge_method": "squash",
        "state_file": state.get("state_file")
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

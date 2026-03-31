"""GitHub Observer - GitHub状態の監視

PR、Issue、CI/CD結果を監視し、必要なアクションを提案する。
"""
from __future__ import annotations
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"
GITHUB_CACHE = STATE_DIR / "github_cache.json"


def run_gh_command(args: List[str], timeout: int = 30) -> Dict[str, Any]:
    """gh CLIコマンドを実行"""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )
        
        if result.returncode == 0:
            return {"ok": True, "output": result.stdout.strip()}
        else:
            return {"ok": False, "error": result.stderr.strip()}
    
    except FileNotFoundError:
        return {"ok": False, "error": "gh CLI not installed"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Command timed out"}


def get_open_prs() -> Dict[str, Any]:
    """オープンなPRを取得"""
    result = run_gh_command([
        "pr", "list",
        "--json", "number,title,headRefName,state,isDraft,createdAt,updatedAt",
    ])
    
    if not result["ok"]:
        return result
    
    try:
        prs = json.loads(result["output"]) if result["output"] else []
        return {"ok": True, "prs": prs, "count": len(prs)}
    except json.JSONDecodeError:
        return {"ok": False, "error": "Failed to parse PR list"}


def get_pr_details(pr_number: int) -> Dict[str, Any]:
    """PR詳細を取得"""
    result = run_gh_command([
        "pr", "view", str(pr_number),
        "--json", "number,title,body,state,mergeable,reviews,statusCheckRollup",
    ])
    
    if not result["ok"]:
        return result
    
    try:
        pr = json.loads(result["output"])
        return {"ok": True, "pr": pr}
    except json.JSONDecodeError:
        return {"ok": False, "error": "Failed to parse PR details"}


def get_ci_status(pr_number: Optional[int] = None) -> Dict[str, Any]:
    """CI/CDステータスを取得"""
    if pr_number:
        result = run_gh_command([
            "pr", "checks", str(pr_number),
            "--json", "name,state,conclusion,startedAt,completedAt",
        ])
    else:
        # 現在のブランチのステータス
        result = run_gh_command([
            "run", "list",
            "--limit", "5",
            "--json", "status,conclusion,name,createdAt,headBranch",
        ])
    
    if not result["ok"]:
        return result
    
    try:
        checks = json.loads(result["output"]) if result["output"] else []
        
        # 失敗しているチェックを抽出
        failed = [c for c in checks if c.get("conclusion") == "failure"]
        pending = [c for c in checks if c.get("state") == "pending" or c.get("status") == "in_progress"]
        
        return {
            "ok": True,
            "checks": checks,
            "failed_count": len(failed),
            "pending_count": len(pending),
            "failed_checks": failed,
        }
    except json.JSONDecodeError:
        return {"ok": False, "error": "Failed to parse CI status"}


def get_open_issues() -> Dict[str, Any]:
    """オープンなIssueを取得"""
    result = run_gh_command([
        "issue", "list",
        "--json", "number,title,labels,createdAt,state",
        "--limit", "20",
    ])
    
    if not result["ok"]:
        return result
    
    try:
        issues = json.loads(result["output"]) if result["output"] else []
        return {"ok": True, "issues": issues, "count": len(issues)}
    except json.JSONDecodeError:
        return {"ok": False, "error": "Failed to parse issue list"}


def analyze_github_state() -> Dict[str, Any]:
    """GitHub状態を総合分析"""
    prs = get_open_prs()
    issues = get_open_issues()
    ci = get_ci_status()
    
    # アクション提案を生成
    actions = []
    warnings = []
    
    # PR関連
    if prs.get("ok"):
        for pr in prs.get("prs", []):
            if pr.get("isDraft"):
                continue
            
            # 古いPRの警告
            updated = pr.get("updatedAt", "")
            if updated:
                # 簡易的な日付比較（7日以上更新なし）
                actions.append({
                    "type": "review_pr",
                    "pr_number": pr["number"],
                    "title": pr["title"],
                    "reason": "Open PR needs attention",
                })
    
    # CI失敗
    if ci.get("ok") and ci.get("failed_count", 0) > 0:
        for check in ci.get("failed_checks", []):
            warnings.append({
                "type": "ci_failure",
                "check_name": check.get("name"),
                "suggestion": "Investigate and fix CI failure",
            })
    
    # Issue関連
    if issues.get("ok"):
        bug_issues = [i for i in issues.get("issues", []) 
                      if any("bug" in str(l).lower() for l in i.get("labels", []))]
        if bug_issues:
            actions.append({
                "type": "fix_bugs",
                "count": len(bug_issues),
                "reason": f"{len(bug_issues)} bug issues need attention",
            })
    
    return {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "prs": prs if prs.get("ok") else {"error": prs.get("error")},
        "issues": issues if issues.get("ok") else {"error": issues.get("error")},
        "ci": ci if ci.get("ok") else {"error": ci.get("error")},
        "suggested_actions": actions,
        "warnings": warnings,
    }


def create_issue(title: str, body: str, labels: Optional[List[str]] = None) -> Dict[str, Any]:
    """Issueを作成"""
    args = ["issue", "create", "--title", title, "--body", body]
    
    if labels:
        for label in labels:
            args.extend(["--label", label])
    
    return run_gh_command(args)


def create_pr(title: str, body: str, base: str = "main") -> Dict[str, Any]:
    """PRを作成"""
    return run_gh_command([
        "pr", "create",
        "--title", title,
        "--body", body,
        "--base", base,
    ])

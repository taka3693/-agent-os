#!/usr/bin/env python3
"""
PR Gate - PR作成前のリスク判定と承認待ち状態管理

責務:
- 変更規模を取得
- リスク判定
- PR下書き生成
- 承認待ち状態を保存
- PR作成用URL/コマンド生成
- PR作成実行（--create-pr指定時）
"""
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "merge_policy.json"
STATE_DIR = ROOT / "state" / "pr_gate"

def load_policy() -> Dict[str, Any]:
    """マージポリシーを読み込み"""
    if not CONFIG_PATH.exists():
        return {
            "protected_paths": [],
            "low_risk_paths": [],
            "max_changed_files_for_low": 3,
            "max_diff_lines_for_low": 100,
            "required_checks": ["syntax", "tests"],
            "default_merge_recommendation": "manual_approval_required"
        }
    return json.loads(CONFIG_PATH.read_text())

def get_changed_files(repo: str, branch: str, base: str) -> List[str]:
    """変更ファイル一覧を取得"""
    # ローカルgitを使用
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{branch}"],
        capture_output=True,
        text=True,
        cwd=ROOT
    )
    if result.returncode != 0:
        return []
    return [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]

def get_diff_summary(repo: str, branch: str, base: str) -> Dict[str, int]:
    """diff統計を取得"""
    result = subprocess.run(
        ["git", "diff", "--shortstat", f"{base}...{branch}"],
        capture_output=True,
        text=True,
        cwd=ROOT
    )
    
    # Example: "3 files changed, 12 insertions(+), 5 deletions(-)"
    summary = {"files": 0, "additions": 0, "deletions": 0}
    
    if result.returncode != 0 or not result.stdout.strip():
        return summary
    
    import re
    files_match = re.search(r'(\d+) files? changed', result.stdout)
    add_match = re.search(r'(\d+) insertions?', result.stdout)
    del_match = re.search(r'(\d+) deletions?', result.stdout)
    
    if files_match:
        summary["files"] = int(files_match.group(1))
    if add_match:
        summary["additions"] = int(add_match.group(1))
    if del_match:
        summary["deletions"] = int(del_match.group(1))
    
    return summary

def assess_risk(changed_files: List[str], diff_summary: Dict[str, int], policy: Dict[str, Any]) -> str:
    """リスク判定"""
    # protected_pathsに変更がある場合はhigh
    for file in changed_files:
        for protected in policy.get("protected_paths", []):
            if file.startswith(protected) or file == protected:
                return "high"
    
    # 変更規模が大きい場合はmedium
    if diff_summary["files"] > policy.get("max_changed_files_for_low", 3):
        return "medium"
    
    total_lines = diff_summary["additions"] + diff_summary["deletions"]
    if total_lines > policy.get("max_diff_lines_for_low", 100):
        return "medium"
    
    return "low"

def check_syntax() -> str:
    """構文チェック（簡易版）"""
    # 実際にはpython -m py_compile等を実行
    return "unknown"

def check_tests() -> str:
    """テストチェック（簡易版）"""
    # 実際にはpytest等を実行
    return "unknown"

def check_freshness() -> str:
    """鮮度チェック（簡易版）"""
    # 実際にはmainとの乖離をチェック
    return "unknown"

def generate_pr_title(branch: str, changed_files: List[str]) -> str:
    """PRタイトル生成"""
    if not changed_files:
        return f"Update from {branch}"
    
    # 最初のファイルから推測
    first_file = changed_files[0]
    
    if "fix" in branch:
        return f"fix: update {first_file}"
    elif "feat" in branch:
        return f"feat: add {first_file}"
    else:
        return f"Update {first_file}"

def generate_pr_body(changed_files: List[str], diff_summary: Dict[str, int], risk_level: str) -> str:
    """PR本文生成"""
    body = "## Summary\n"
    
    if changed_files:
        body += "\n### Changed Files\n"
        for f in changed_files:
            body += f"- {f}\n"
    
    body += f"\n### Diff Summary\n"
    body += f"- Files: {diff_summary['files']}\n"
    body += f"- Additions: +{diff_summary['additions']}\n"
    body += f"- Deletions: -{diff_summary['deletions']}\n"
    
    body += f"\n### Risk Assessment\n"
    body += f"- Risk Level: **{risk_level.upper()}**\n"
    
    return body

def generate_pr_url(repo: str, branch: str, base: str) -> str:
    """GitHub PR作成URL生成"""
    # https://github.com/{owner}/{repo}/compare/{base}...{branch}
    return f"https://github.com/{repo}/compare/{base}...{branch}"

def generate_create_pr_command(repo: str, branch: str, base: str, title: str, body: str) -> str:
    """gh CLI PR作成コマンド生成"""
    # gh pr create --title "..." --body "..." --base main
    # bodyは改行を含むので、ヒアドキュメント形式にする
    body_escaped = body.replace('"', '\\"').replace('\n', '\\n')
    return f'gh pr create --title "{title}" --body "{body_escaped}" --base {base}'

def generate_manual_review_checklist(
    changed_files: List[str],
    protected_paths: List[str],
    risk_level: str
) -> List[str]:
    """手動レビュー用チェックリスト生成"""
    checklist = []
    
    # 基本チェック
    checklist.append("- [ ] コードレビュー完了")
    checklist.append("- [ ] 動作確認完了")
    checklist.append("- [ ] テスト実行（必要時）")
    
    # protected_pathsが含まれる場合の追加チェック
    if risk_level == "high":
        protected_changed = []
        for file in changed_files:
            for protected in protected_paths:
                if file.startswith(protected) or file == protected:
                    protected_changed.append(file)
                    break
        
        if protected_changed:
            checklist.append("")
            checklist.append("### Protected Paths Review")
            checklist.append("- [ ] 影響範囲の確認")
            checklist.append("- [ ] 後方互換性の確認")
            checklist.append("- [ ] セキュリティ影響の確認")
            checklist.append(f"- Changed protected files: {', '.join(protected_changed)}")
    
    # medium riskの場合
    if risk_level == "medium":
        checklist.append("")
        checklist.append("### Medium Risk Items")
        checklist.append("- [ ] 変更規模の妥当性確認")
        checklist.append("- [ ] 依存関係への影響確認")
    
    return checklist

def create_pr_with_gh(
    repo: str,
    branch: str,
    base: str,
    title: str,
    body: str
) -> Dict[str, Any]:
    """gh CLIを使用してPRを作成"""
    try:
        # gh CLIの存在確認
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return {
                "pr_created": False,
                "error": "gh CLI not found",
                "pr_url": None,
                "pr_command_output": None
            }
        
        # PR作成実行
        # --head flagを使用してリモートブランチを明示
        result = subprocess.run(
            ["gh", "pr", "create", "--title", title, "--body", body, "--base", base, "--head", f"origin/{branch}"],
            capture_output=True,
            text=True,
            cwd=ROOT
        )
        
        if result.returncode == 0:
            # 成功: PR URLを抽出
            pr_url = result.stdout.strip()
            return {
                "pr_created": True,
                "pr_url": pr_url,
                "pr_command_output": result.stdout,
                "pr_command_stderr": result.stderr if result.stderr else None
            }
        else:
            # 失敗: エラー情報を返す
            return {
                "pr_created": False,
                "error": "gh pr create failed",
                "pr_url": None,
                "pr_command_output": result.stdout,
                "pr_command_stderr": result.stderr
            }
    
    except Exception as e:
        return {
            "pr_created": False,
            "error": f"Exception: {str(e)}",
            "pr_url": None,
            "pr_command_output": None
        }

def save_state(data: Dict[str, Any]) -> Path:
    """承認待ち状態を保存"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    branch = data["branch"].replace("/", "_")
    state_file = STATE_DIR / f"{branch}_{timestamp}.json"
    
    state = {
        **data,
        "status": "pending_approval",
        "created_at": datetime.now().isoformat(),
        "state_file": str(state_file)
    }
    
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    return state_file

def main():
    """メインエントリーポイント"""
    import argparse
    
    parser = argparse.ArgumentParser(description="PR Gate")
    parser.add_argument("--repo", required=True, help="Repository (e.g., taka3693/-agent-os)")
    parser.add_argument("--branch", required=True, help="Feature branch")
    parser.add_argument("--base", default="main", help="Base branch")
    parser.add_argument("--create-pr", action="store_true", help="Create PR using gh CLI")
    
    args = parser.parse_args()
    
    # ポリシー読み込み
    policy = load_policy()
    
    # 変更取得
    changed_files = get_changed_files(args.repo, args.branch, args.base)
    diff_summary = get_diff_summary(args.repo, args.branch, args.base)
    
    # リスク判定
    risk_level = assess_risk(changed_files, diff_summary, policy)
    
    # チェック
    checks = {
        "syntax": check_syntax(),
        "tests": check_tests(),
        "freshness": check_freshness()
    }
    
    # PR下書き生成
    pr_title = generate_pr_title(args.branch, changed_files)
    pr_body = generate_pr_body(changed_files, diff_summary, risk_level)
    
    # PR作成URL生成
    pr_url = generate_pr_url(args.repo, args.branch, args.base)
    
    # PR作成コマンド生成
    create_pr_command = generate_create_pr_command(
        args.repo, args.branch, args.base, pr_title, pr_body
    )
    
    # 手動レビューチェックリスト生成
    manual_review_checklist = generate_manual_review_checklist(
        changed_files, policy.get("protected_paths", []), risk_level
    )
    
    # マージ推奨判定
    merge_recommendation = policy.get("default_merge_recommendation", "manual_approval_required")
    if risk_level == "low" and all(c in ["pass", "unknown"] for c in checks.values()):
        merge_recommendation = "eligible_for_manual_merge_review"
    
    # PR作成（--create-pr指定時）
    pr_result = None
    if args.create_pr:
        pr_result = create_pr_with_gh(
            args.repo, args.branch, args.base, pr_title, pr_body
        )
        # pr_urlを更新（作成成功時）
        if pr_result.get("pr_created"):
            pr_url = pr_result.get("pr_url", pr_url)
    
    # 結果まとめ
    result = {
        "ok": True,
        "repo": args.repo,
        "branch": args.branch,
        "base": args.base,
        "risk_level": risk_level,
        "changed_files": changed_files,
        "diff_summary": diff_summary,
        "checks": checks,
        "merge_recommendation": merge_recommendation,
        "pr_title": pr_title,
        "pr_body": pr_body,
        "pr_url": pr_url,
        "create_pr_command": create_pr_command,
        "manual_review_checklist": manual_review_checklist
    }
    
    # PR作成結果を追加
    if pr_result:
        result["pr_created"] = pr_result.get("pr_created", False)
        result["pr_command_output"] = pr_result.get("pr_command_output")
        if pr_result.get("error"):
            result["error"] = pr_result.get("error")
        if pr_result.get("pr_command_stderr"):
            result["pr_command_stderr"] = pr_result.get("pr_command_stderr")
    
    # 状態保存
    state_file = save_state(result)
    result["state_file"] = str(state_file)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

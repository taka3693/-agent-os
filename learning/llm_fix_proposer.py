"""LLM Fix Proposer - GLM-5を使った修正案生成

検出された問題に対して、LLMを使ってコード修正案を生成する。
"""
from __future__ import annotations
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"


def call_openclaw(prompt: str, agent: str = "dev", timeout: int = 120) -> Dict[str, Any]:
    """OpenClawを呼び出してLLM応答を取得"""
    try:
        result = subprocess.run(
            ["openclaw", "agent", "--agent", agent, "-m", prompt, "--local"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )
        
        if result.returncode == 0:
            return {"ok": True, "response": result.stdout.strip()}
        else:
            return {"ok": False, "error": result.stderr or "OpenClaw failed"}
    
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "OpenClaw timeout"}
    except FileNotFoundError:
        return {"ok": False, "error": "OpenClaw not found"}


def generate_fix_with_llm(
    issue: Dict[str, Any],
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """LLMを使って修正案を生成
    
    Args:
        issue: 検出された問題
        context: 追加のコンテキスト（関連コードなど）
    
    Returns:
        生成された修正案
    """
    issue_type = issue.get("type", "unknown")
    
    # プロンプト構築
    prompt = f"""あなたはAgent-OSの自己改善システムです。
以下の問題を分析し、具体的な修正案を提案してください。

## 問題
- タイプ: {issue_type}
- 詳細: {json.dumps(issue, ensure_ascii=False, indent=2)}

{f"## 関連コンテキスト{chr(10)}{context}" if context else ""}

## 出力形式
以下のJSON形式で回答してください（JSONのみ、説明不要）:
````json
{{
  "analysis": "問題の根本原因の分析",
  "fix_type": "config_change | code_fix | architecture_change | workaround",
  "priority": "high | medium | low",
  "changes": [
    {{
      "file": "ファイルパス",
      "description": "変更内容の説明",
      "before": "変更前のコード（該当部分のみ）",
      "after": "変更後のコード"
    }}
  ],
  "testing": "テスト方法の提案",
  "risks": ["リスクがあれば記載"]
}}
```"""

    result = call_openclaw(prompt)
    
    if not result["ok"]:
        return {
            "ok": False,
            "error": result["error"],
            "fallback": True,
        }
    
    # JSON抽出
    response = result["response"]
    try:
        # ```json ... ``` を抽出
        if "```json" in response:
            json_start = response.index("```json") + 7
            json_end = response.index("```", json_start)
            json_str = response[json_start:json_end].strip()
        elif "```" in response:
            json_start = response.index("```") + 3
            json_end = response.index("```", json_start)
            json_str = response[json_start:json_end].strip()
        else:
            json_str = response
        
        fix = json.loads(json_str)
        fix["generated_by"] = "llm"
        fix["generated_at"] = datetime.now(timezone.utc).isoformat()
        fix["original_issue"] = issue
        
        return {"ok": True, "fix": fix}
    
    except (json.JSONDecodeError, ValueError) as e:
        return {
            "ok": False,
            "error": f"Failed to parse LLM response: {e}",
            "raw_response": response[:500],
        }


def generate_fixes_for_issues(
    issues: List[Dict[str, Any]],
    max_fixes: int = 3,
) -> List[Dict[str, Any]]:
    """複数の問題に対して修正案を生成"""
    fixes = []
    
    for issue in issues[:max_fixes]:
        # 関連コードのコンテキストを取得
        context = _get_context_for_issue(issue)
        
        result = generate_fix_with_llm(issue, context)
        
        if result["ok"]:
            fixes.append(result["fix"])
        else:
            # フォールバック: ルールベースの修正案
            fixes.append({
                "analysis": "LLM生成失敗、ルールベースのフォールバック",
                "fix_type": "workaround",
                "priority": "medium",
                "changes": [],
                "error": result.get("error"),
                "original_issue": issue,
                "generated_by": "fallback",
            })
    
    return fixes


def _get_context_for_issue(issue: Dict[str, Any]) -> Optional[str]:
    """問題に関連するコードコンテキストを取得"""
    issue_type = issue.get("type", "")
    
    if issue_type == "timeout":
        # タイムアウト問題: budget設定を確認
        budget_file = PROJECT_ROOT / "runner" / "orchestrator.py"
        if budget_file.exists():
            content = budget_file.read_text()
            # max_duration関連の行を抽出
            lines = content.split("\n")
            relevant = [l for l in lines if "duration" in l.lower() or "timeout" in l.lower()]
            if relevant:
                return f"関連コード（orchestrator.py）:\n" + "\n".join(relevant[:10])
    
    elif issue_type == "test_failure":
        # テスト失敗: テストファイルを確認
        test_file = issue.get("file")
        if test_file:
            test_path = PROJECT_ROOT / test_file
            if test_path.exists():
                content = test_path.read_text()
                return f"テストファイル（{test_file}）:\n{content[:2000]}"
    
    return None


def save_llm_fixes(fixes: List[Dict[str, Any]]) -> Path:
    """LLM生成の修正案を保存"""
    output_file = STATE_DIR / "llm_fix_proposals.jsonl"
    
    with open(output_file, "a") as f:
        for fix in fixes:
            f.write(json.dumps(fix, ensure_ascii=False) + "\n")
    
    return output_file


def run_llm_improvement_cycle(
    dry_run: bool = False,
    max_fixes: int = 3,
) -> Dict[str, Any]:
    """LLM自己改善サイクルを実行"""
    from learning.failure_analyzer import run_full_analysis
    
    # 1. 問題分析
    analysis = run_full_analysis()
    issues = analysis.get("issues", [])
    
    if not issues:
        return {
            "ok": True,
            "message": "No issues found",
            "fixes_generated": 0,
        }
    
    # 2. LLMで修正案生成
    fixes = generate_fixes_for_issues(issues, max_fixes)
    
    # 3. 保存
    if not dry_run and fixes:
        save_llm_fixes(fixes)
    
    return {
        "ok": True,
        "issues_analyzed": len(issues),
        "fixes_generated": len(fixes),
        "fixes": fixes,
        "dry_run": dry_run,
    }

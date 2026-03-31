"""Fix Proposer - LLMを使って修正案を生成

検出された問題に対して、コード修正案を生成する。
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"


def generate_fix_prompt(suggestion: Dict[str, Any]) -> str:
    """修正案生成のためのプロンプトを作成"""
    category = suggestion.get("category", "general")
    
    if category == "performance":
        return f"""以下の問題に対する修正案を提案してください:

問題: {suggestion['suggestion']}
影響: {suggestion.get('affected', 'unknown')}

以下を検討してください:
1. タイムアウト値の増加
2. 処理の最適化
3. 非同期処理への変更
4. キャッシュの導入

JSON形式で回答:
{{"fix_type": "...", "description": "...", "code_changes": [...]}}"""

    elif category == "reliability":
        return f"""以下の繰り返しエラーの修正案を提案してください:

エラー: {suggestion['suggestion']}
発生回数: {suggestion.get('occurrences', 'multiple')}

根本原因を特定し、修正案を提案してください。

JSON形式で回答:
{{"fix_type": "...", "root_cause": "...", "code_changes": [...]}}"""

    elif category == "quality":
        return f"""以下のテスト失敗の修正案を提案してください:

失敗: {suggestion['suggestion']}
ファイル: {suggestion.get('file', 'unknown')}

JSON形式で回答:
{{"fix_type": "...", "description": "...", "code_changes": [...]}}"""

    else:
        return f"""以下の問題の修正案を提案してください:

問題: {suggestion['suggestion']}

JSON形式で回答:
{{"fix_type": "...", "description": "...", "code_changes": [...]}}"""


def propose_fixes_offline(
    suggestions: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """オフラインで修正案を生成（LLMなし、ルールベース）"""
    fixes = []
    
    for suggestion in suggestions:
        category = suggestion.get("category", "general")
        
        if category == "performance" and "timeout" in suggestion["suggestion"].lower():
            fixes.append({
                "suggestion_id": id(suggestion),
                "category": category,
                "fix_type": "config_change",
                "description": "Increase timeout value",
                "code_changes": [
                    {
                        "file": "runner/orchestrator.py",
                        "change_type": "config",
                        "description": "Increase max_duration_seconds in budget",
                    }
                ],
                "priority": suggestion.get("priority", "medium"),
                "auto_applicable": False,
            })
        
        elif category == "reliability":
            fixes.append({
                "suggestion_id": id(suggestion),
                "category": category,
                "fix_type": "error_handling",
                "description": f"Add error handling for: {suggestion['suggestion']}",
                "code_changes": [
                    {
                        "change_type": "add_try_catch",
                        "description": "Wrap in try-except with retry logic",
                    }
                ],
                "priority": suggestion.get("priority", "medium"),
                "auto_applicable": False,
            })
        
        elif category == "optimization":
            fixes.append({
                "suggestion_id": id(suggestion),
                "category": category,
                "fix_type": "tuning",
                "description": suggestion["suggestion"],
                "code_changes": [],
                "priority": suggestion.get("priority", "low"),
                "auto_applicable": False,
            })
    
    return fixes


def save_fix_proposals(fixes: List[Dict[str, Any]]) -> Path:
    """修正案をファイルに保存"""
    output_file = STATE_DIR / "fix_proposals.jsonl"
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    with open(output_file, "a") as f:
        for fix in fixes:
            fix["proposed_at"] = timestamp
            fix["status"] = "proposed"
            f.write(json.dumps(fix, ensure_ascii=False) + "\n")
    
    return output_file


def load_pending_fixes() -> List[Dict[str, Any]]:
    """未適用の修正案を読み込む"""
    fix_file = STATE_DIR / "fix_proposals.jsonl"
    
    if not fix_file.exists():
        return []
    
    pending = []
    for line in fix_file.read_text().strip().split("\n"):
        if line.strip():
            try:
                fix = json.loads(line)
                if fix.get("status") == "proposed":
                    pending.append(fix)
            except json.JSONDecodeError:
                continue
    
    return pending

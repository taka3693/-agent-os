"""Self-Improvement Runner - 自己改善サイクル

1. 失敗・問題を分析
2. 修正案を生成
3. 承認キューに登録（または自動適用）
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"

from learning.failure_analyzer import run_full_analysis, get_improvement_suggestions
from learning.fix_proposer import propose_fixes_offline, save_fix_proposals


def run_self_improvement_cycle(
    dry_run: bool = False,
) -> Dict[str, Any]:
    """自己改善サイクルを実行
    
    Args:
        dry_run: Trueの場合、修正案を保存しない
    
    Returns:
        サイクル実行結果
    """
    # 1. 問題分析
    analysis = run_full_analysis()
    
    # 2. 修正案生成
    fixes = propose_fixes_offline(analysis["suggestions"])
    
    # 3. 保存（dry_runでなければ）
    saved_file = None
    if not dry_run and fixes:
        saved_file = save_fix_proposals(fixes)
    
    result = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "issues_analyzed": analysis["issues_found"],
        "suggestions_generated": len(analysis["suggestions"]),
        "fixes_proposed": len(fixes),
        "saved_to": str(saved_file) if saved_file else None,
        "fixes": fixes,
    }
    
    # ログに記録
    if not dry_run:
        log_file = STATE_DIR / "self_improvement_cycles.jsonl"
        log_entry = {k: v for k, v in result.items() if k != "fixes"}
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    
    return result


def get_self_improvement_status() -> Dict[str, Any]:
    """自己改善サイクルの状態を取得"""
    log_file = STATE_DIR / "self_improvement_cycles.jsonl"
    fix_file = STATE_DIR / "fix_proposals.jsonl"
    
    status = {
        "total_cycles": 0,
        "last_cycle": None,
        "pending_fixes": 0,
    }
    
    if log_file.exists():
        lines = [l for l in log_file.read_text().strip().split("\n") if l.strip()]
        status["total_cycles"] = len(lines)
        if lines:
            try:
                status["last_cycle"] = json.loads(lines[-1])
            except json.JSONDecodeError:
                pass
    
    if fix_file.exists():
        pending = 0
        for line in fix_file.read_text().strip().split("\n"):
            if line.strip():
                try:
                    fix = json.loads(line)
                    if fix.get("status") == "proposed":
                        pending += 1
                except json.JSONDecodeError:
                    continue
        status["pending_fixes"] = pending
    
    return status

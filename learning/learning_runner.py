"""Learning Runner - 学習→行動ポリシー生成のサイクル

定期的に実行され、学習エピソードからパターンを抽出し、
新しい行動ポリシーを生成・保存する。
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from learning.pattern_extractor import extract_patterns, get_recommendations
from learning.action_policy import (
    load_policies,
    save_policy,
    generate_policies_from_recommendations,
)


STATE_DIR = Path(__file__).resolve().parents[1] / "state"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_learning_cycle(
    min_occurrences: int = 2,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """学習サイクルを実行
    
    1. エピソードからパターン抽出
    2. パターンから推奨生成
    3. 推奨からポリシー生成
    4. 新規ポリシーを保存
    
    Args:
        min_occurrences: パターン認識の最小出現回数
        dry_run: Trueの場合、ポリシー保存しない
    
    Returns:
        サイクル実行結果
    """
    # 1. パターン抽出
    patterns = extract_patterns(min_occurrences=min_occurrences)
    
    # 2. 推奨生成
    recommendations = get_recommendations(patterns)
    
    # 3. ポリシー生成
    new_policies = generate_policies_from_recommendations(recommendations)
    
    # 4. 既存ポリシーとの重複チェック
    existing = load_policies()
    existing_targets = {(p.get("action"), p.get("target")) for p in existing}
    
    unique_policies = [
        p for p in new_policies
        if (p.get("action"), p.get("target")) not in existing_targets
    ]
    
    # 5. 保存
    saved_count = 0
    if not dry_run:
        for policy in unique_policies:
            save_policy(policy)
            saved_count += 1
    
    result = {
        "executed_at": utc_now_iso(),
        "dry_run": dry_run,
        "patterns_found": len(patterns.get("patterns", [])),
        "recommendations": len(recommendations),
        "new_policies_generated": len(new_policies),
        "unique_policies": len(unique_policies),
        "policies_saved": saved_count,
        "summary": patterns.get("summary", {}),
    }
    
    # ログに記録
    if not dry_run:
        log_file = STATE_DIR / "learning_cycles.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    
    return result


def get_learning_status() -> Dict[str, Any]:
    """学習サイクルの状態を取得"""
    log_file = STATE_DIR / "learning_cycles.jsonl"
    
    if not log_file.exists():
        return {"status": "no_history", "last_cycle": None}
    
    try:
        lines = log_file.read_text().strip().split("\n")
        if not lines or not lines[-1]:
            return {"status": "no_history", "last_cycle": None}
        
        last_cycle = json.loads(lines[-1])
        return {
            "status": "active",
            "last_cycle": last_cycle,
            "total_cycles": len(lines),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

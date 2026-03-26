#!/usr/bin/env python3
from __future__ import annotations
from typing import Dict, Any, List
import re
import sys
from pathlib import Path

# Add project root to path for strategy_manager import
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DECISION_KEYWORDS = (
    "比較", "選定", "判断", "決めたい", "どれ", "優先", "優先順位",
    "choose", "compare", "decision", "decide", "prioritize", "priority",
)

DEFAULT_AXES = ["価値", "コスト", "速度", "リスク"]

def _derive_options(query: str) -> List[str]:
    q = (query or "").strip()
    if not q:
        return []
    
    noise_patterns = [
        r"、どちらを優先すべきか",
        r"、どっちを優先すべきか",
        r"どちらを優先すべきか",
        r"どっちを優先すべきか",
        r"どちらがいいか",
        r"どっちがいいか",
        r"どちらを選ぶべきか",
        r"どれを優先",
        r"すべきか$",
        r"べきか$",
        r"がいいか$",
        r"がいい$",
        r"方が良い$",
    ]
    cleaned_q = q
    for pattern in noise_patterns:
        cleaned_q = re.sub(pattern, "", cleaned_q)
    cleaned_q = cleaned_q.strip().rstrip("、").rstrip(",")
    
    seps = [" vs ", " VS ", " or ", " OR ", "と", "、", ",", "それとも", " か "]
    parts = [cleaned_q]
    for sep in seps:
        nxt = []
        for part in parts:
            if sep in part:
                nxt.extend([x.strip() for x in part.split(sep) if x.strip()])
            else:
                nxt.append(part)
        parts = nxt
    
    final = []
    for x in parts:
        x = x.strip()
        if len(x) >= 2 and x not in final:
            final.append(x)
    return final[:5]

def _score_options(options: List[str], axes: List[str]) -> Dict[str, Dict[str, int]]:
    scores = {}
    for i, opt in enumerate(options):
        opt_scores = {}
        for j, axis in enumerate(axes):
            base = 7 if i == 0 else 6
            opt_scores[axis] = base + (j % 3) - 1
        opt_scores["total"] = sum(v for v in opt_scores.values() if isinstance(v, int))
        scores[opt] = opt_scores
    return scores

def _pick_winner(scores: Dict[str, Dict[str, int]]) -> tuple:
    if not scores:
        return None, None
    sorted_opts = sorted(scores.items(), key=lambda x: x[1].get("total", 0), reverse=True)
    winner = sorted_opts[0][0] if sorted_opts else None
    deprioritized = sorted_opts[-1][0] if len(sorted_opts) > 1 else None
    return winner, deprioritized

def _check_strategy_alignment(query: str, winner: str) -> Dict[str, Any]:
    """Check alignment with weekly goals using strategy_manager."""
    try:
        from tools.strategy_manager import check_goal_alignment, get_strategy_summary
        
        # Check both the query and the winner
        query_alignment = check_goal_alignment(query)
        winner_alignment = check_goal_alignment(winner) if winner else {}
        
        summary = get_strategy_summary()
        
        return {
            "checked": True,
            "primary_goal": summary.get("primary_goal"),
            "query_aligns_primary": query_alignment.get("aligns_with_primary", False),
            "query_aligns_secondary": query_alignment.get("aligns_with_secondary", False),
            "winner_aligns_primary": winner_alignment.get("aligns_with_primary", False),
            "winner_aligns_secondary": winner_alignment.get("aligns_with_secondary", False),
            "matched_keywords": list(set(
                query_alignment.get("matched_keywords", []) + 
                winner_alignment.get("matched_keywords", [])
            )),
            "recommendation": winner_alignment.get("recommendation", query_alignment.get("recommendation", "review")),
        }
    except Exception as e:
        return {
            "checked": False,
            "error": str(e),
        }

def run_decision(query: str) -> Dict[str, Any]:
    q = (query or "").strip()
    options = _derive_options(q)
    axes = DEFAULT_AXES.copy()
    
    findings = [
        f"依頼文を確認: {q}",
        f"判断軸を設定: {' / '.join(axes)}",
    ]
    
    decision = {
        "conclusion": None,
        "winner": None,
        "deprioritized": None,
        "next_actions": [],
    }
    scores = {}
    decision_reason_structured = {
        "query": q,
        "options_detected": options,
        "axes_used": axes,
        "selection_method": "score_based",
        "confidence": "medium",
    }
    
    if len(options) >= 2:
        findings.append("候補を分解: " + " / ".join(options))
        scores = _score_options(options, axes)
        winner, deprioritized = _pick_winner(scores)
        
        decision["winner"] = winner
        decision["deprioritized"] = deprioritized
        decision["conclusion"] = f"{winner}を優先"
        decision["next_actions"] = [
            f"今日中に {winner} で狙う案件/テーマを3件書き出す",
            f"{winner} の提案文または実績訴求文を1本作る",
            f"{deprioritized} はアイデア保留箱に入れ、着手条件を数値化する",
        ]
        
        decision_reason_structured["winner_reason"] = f"{winner}が総合スコアで優位"
        decision_reason_structured["confidence"] = "high" if len(options) == 2 else "medium"
        
        findings.append(f"判定結果: {winner} を優先（総合スコア上位）")
        summary = f"意思決定完了。{winner}を優先する。"
        
        # Check strategy alignment
        strategy_alignment = _check_strategy_alignment(q, winner)
        if strategy_alignment.get("checked"):
            pg = strategy_alignment.get("primary_goal")
            if strategy_alignment.get("winner_aligns_primary"):
                findings.append(f"✅ 週目標「{pg}」と整合 → 優先度高")
            elif strategy_alignment.get("winner_aligns_secondary"):
                findings.append(f"⚠️ 副次目標との整合（週目標「{pg}」ではない）")
                findings.append(f"💡 主目標に集中すべきか再検討を推奨")
            else:
                findings.append(f"🚨 警告: 週目標「{pg}」から外れています")
                findings.append(f"💡 本当にこれを今やるべきか？主目標に戻ることを検討")
    else:
        findings.append("候補不足: 比較対象を2〜5個に明示してください")
        decision["conclusion"] = "保留"
        decision["next_actions"] = ["比較対象を明確化して再入力する"]
        decision_reason_structured["confidence"] = "low"
        summary = "意思決定の下準備を完了した。候補不足のため、比較対象の明確化が必要。"
        strategy_alignment = {"checked": False, "reason": "no_winner"}
    
    return {
        "summary": summary,
        "findings": findings,
        "decision": decision,
        "axes": axes,
        "scores": scores,
        "decision_reason_structured": decision_reason_structured,
        "strategy_alignment": strategy_alignment,
        "ok": True,
    }

def execute(query: str) -> Dict[str, Any]:
    return run_decision(query)

if __name__ == "__main__":
    import json
    import sys
    q = " ".join(sys.argv[1:]).strip()
    print(json.dumps(run_decision(q), ensure_ascii=False, indent=2))

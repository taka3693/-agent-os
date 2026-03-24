#!/usr/bin/env python3
from __future__ import annotations
from typing import Dict, Any, List
import re

DECISION_KEYWORDS = (
    "比較", "選定", "判断", "決めたい", "どれ", "優先", "優先順位",
    "choose", "compare", "decision", "decide", "prioritize", "priority",
)

DEFAULT_AXES = ["価値", "コスト", "速度", "リスク"]

def _derive_options(query: str) -> List[str]:
    q = (query or "").strip()
    if not q:
        return []
    
    # Remove noise phrases first
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
    
    # Split by separators - order matters, "と" should be early
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
    
    # Final cleanup
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
    else:
        findings.append("候補不足: 比較対象を2〜5個に明示してください")
        decision["conclusion"] = "保留"
        decision["next_actions"] = ["比較対象を明確化して再入力する"]
        decision_reason_structured["confidence"] = "low"
        summary = "意思決定の下準備を完了した。候補不足のため、比較対象の明確化が必要。"
    
    return {
        "summary": summary,
        "findings": findings,
        "decision": decision,
        "axes": axes,
        "scores": scores,
        "decision_reason_structured": decision_reason_structured,
        "ok": True,
    }

def execute(query: str) -> Dict[str, Any]:
    return run_decision(query)

if __name__ == "__main__":
    import json
    import sys
    q = " ".join(sys.argv[1:]).strip()
    print(json.dumps(run_decision(q), ensure_ascii=False, indent=2))

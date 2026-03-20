from typing import List, Dict, Any
import hashlib

def _default_criteria():
    return ["impact", "cost", "speed", "risk", "scalability"]

def _default_weights(criteria):
    base = {
        "impact": 5,
        "scalability": 4,
        "speed": 3,
        "cost": 2,
        "risk": 1,
    }
    return {c: base.get(c, 1) for c in criteria}

def _score(option: str, criteria):
    h = hashlib.md5(option.strip().lower().encode()).hexdigest()
    vals = []
    for i, c in enumerate(criteria):
        chunk = h[i * 2:(i * 2) + 2] or "0f"
        vals.append((int(chunk, 16) % 5) + 1)
    return {c: vals[i] for i, c in enumerate(criteria)}

def generate_decision(goal: str, options: List[str], criteria=None, weights=None) -> Dict[str, Any]:
    criteria = criteria or _default_criteria()
    weights = weights or _default_weights(criteria)
    options = [o.strip() for o in options if o and o.strip()]
    comp, scores = [], []

    for o in options:
        m = _score(o, criteria)
        weighted_total = sum(m[c] * weights.get(c, 1) for c in criteria)
        comp.append({
            "option": o,
            "scores": m,
            "notes": "",
        })
        scores.append({
            "option": o,
            "total": weighted_total,
            "breakdown": m,
            "weighted_breakdown": {c: m[c] * weights.get(c, 1) for c in criteria},
        })

    scores.sort(key=lambda x: (-x["total"], x["option"]))
    best = scores[0]

    rejected = []
    for s in scores[1:]:
        gap = best["total"] - s["total"]
        reason = "加重スコアが低い" if gap > 0 else "同点だが優先順位で劣後"
        rejected.append({"option": s["option"], "reason": reason})

    max_total = sum(5 * weights.get(c, 1) for c in criteria)
    summary = f"推奨は{best['option']}。理由は{best['option']}が加重スコア最上位だから。次は小規模テスト。"
    findings = [
        f"最上位候補: {best['option']}",
        f"比較候補数: {len(options)}",
        f"評価軸数: {len(criteria)}",
    ]

    return {
        "summary": summary,
        "findings": findings,
        "goal": goal,
        "options": options,
        "criteria": criteria,
        "weights": weights,
        "comparison": comp,
        "scores": scores,
        "recommendation": {
            "option": best["option"],
            "confidence": round(best["total"] / max_total, 2)
        },
        "reasoning": f"{best['option']}が加重スコア最上位のため推奨",
        "rejected": rejected,
        "next_actions": [
            f"{best['option']}で小規模テストを実施",
            "成功指標に対する結果を計測",
            "継続拡大か方針転換かを判断"
        ]
    }

OPTION_ALIASES = {
    "広告": ["広告", "ads", "ad", "アド"],
    "受託": ["受託", "案件", "フリーランス", "コンサル", "開発受注"],
    "サブスク": ["サブスク", "月額", "定額", "subscription", "継続課金"],
    "買い切り": ["買い切り", "単発", "販売", "ライセンス", "パッケージ"],
}

PRESET_WEIGHTS = {
    "speed": {"speed": 0.35, "predictability": 0.15, "scalability": 0.10, "labor_dependency": 0.15, "retention": 0.05, "distribution_dependency": 0.10, "margin": 0.10},
    "recurring": {"speed": 0.05, "predictability": 0.20, "scalability": 0.15, "labor_dependency": 0.10, "retention": 0.25, "distribution_dependency": 0.10, "margin": 0.15},
    "scalability": {"speed": 0.05, "predictability": 0.10, "scalability": 0.30, "labor_dependency": 0.20, "retention": 0.10, "distribution_dependency": 0.10, "margin": 0.15},
    "monetization": {"speed": 0.20, "predictability": 0.15, "scalability": 0.15, "labor_dependency": 0.10, "retention": 0.10, "distribution_dependency": 0.10, "margin": 0.20},
}

CRITERIA = ["speed", "predictability", "scalability", "labor_dependency", "retention", "distribution_dependency", "margin"]

OPTION_PROFILES = {
    "広告": {"speed": 1, "predictability": 1, "scalability": 4, "labor_dependency": 5, "retention": 2, "distribution_dependency": 1, "margin": 4},
    "受託": {"speed": 5, "predictability": 3, "scalability": 1, "labor_dependency": 1, "retention": 1, "distribution_dependency": 4, "margin": 2},
    "サブスク": {"speed": 2, "predictability": 4, "scalability": 5, "labor_dependency": 4, "retention": 5, "distribution_dependency": 3, "margin": 5},
    "買い切り": {"speed": 3, "predictability": 2, "scalability": 4, "labor_dependency": 3, "retention": 1, "distribution_dependency": 2, "margin": 4},
}

def _score(option, weights):
    p = OPTION_PROFILES.get(option, {k: 2 for k in CRITERIA})
    return round(sum(p[k] * weights[k] for k in CRITERIA), 3)

def _extract_options(request: str):
    req = (request or "").lower()
    opts = []
    if any(x in req for x in ["月額", "定額", "継続課金"]):
        opts.append("サブスク")
    if any(x in req for x in ["コンサル", "案件", "受託"]):
        opts.append("受託")
    if opts:
        return sorted(set(opts))
    for key, vals in OPTION_ALIASES.items():
        if any(v.lower() in req for v in vals):
            opts.append(key)
    return sorted(set(opts))

def generate_decision(request: str, context=None, feedback=None):
    req = request or ""
    low = req.lower()

    preset = "monetization"
    if "fast cash" in low or "fast" in low or "即金" in req:
        preset = "speed"
    elif "recurring" in low or "継続" in req:
        preset = "recurring"
    elif "scale" in low or "scalability" in low:
        preset = "scalability"

    weights = PRESET_WEIGHTS[preset].copy()
    # Feedback-based weight adjustment
    if feedback:
        sr = feedback.get("success_rate", 1)
        if sr < 0.7:
            # 失敗時: speedとpredictabilityを重視、scalabilityを下げる
            weights["speed"] = min(0.5, weights["speed"] + 0.15)
            weights["predictability"] = min(0.35, weights["predictability"] + 0.10)
            weights["scalability"] = max(0.05, weights["scalability"] - 0.10)

    options = _extract_options(req) or ["広告", "受託", "サブスク", "買い切り"]
    scores = {o: _score(o, weights) for o in options}
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    best = ranked[0][0]
    second = ranked[1][0] if len(ranked) > 1 else best
    gap = round(ranked[0][1] - ranked[1][1], 3) if len(ranked) > 1 else 0

    diff = {k: OPTION_PROFILES[best][k] - OPTION_PROFILES[second][k] for k in CRITERIA}
    top_axes = sorted(diff.items(), key=lambda x: x[1], reverse=True)[:3]
    axes_str = ", ".join(f"{k}(+{v})" for k, v in top_axes if v > 0)

    needed = []
    for k in CRITERIA:
        d = OPTION_PROFILES[best][k] - OPTION_PROFILES[second][k]
        if d <= 0:
            needed.append((k, abs(d) + 1))
    needed_str = ", ".join(f"{k}(+{v})" for k, v in needed[:3])

    action_rules = {
        "speed": "即金化できる販売導線を作る",
        "retention": "継続率を上げる仕組みを設計する",
        "scalability": "自動化 or 商品化する",
        "labor_dependency": "人依存を減らす",
        "distribution_dependency": "集客チャネルを増やす",
        "margin": "価格またはコスト構造を見直す",
        "predictability": "収益の再現性を高める",
    }
    next_actions = [action_rules[k] for k, _ in needed[:3]] if needed else ["継続価値の定義", "提供フロー作成", "初期ユーザー獲得"]

    return {
        "summary": "best option selected",
        "goal": preset,
        "options": options,
        "criteria": CRITERIA,
        "weights": weights,
        "scores": scores,
        "comparison": [{"option_a": best, "option_b": second, "gap": gap}],
        "proposal": {
            "title": "収益モデル提案",
            "recommended_model": best,
            "why": f"{best} beats {second} by {gap} driven by {axes_str}",
            "why_not_second": f"{second}は今回は2番手。主因は to flip decision, improve: {needed_str}",
            "kpi": ["MRR", "churn", "trial_to_paid", "CAC回収月数"],
            "first_month": ["オファー定義", "LP作成", "初回顧客5件獲得", "継続率計測"],
            "expected_outcome": "maximized decision score",
            "risk": f"to flip decision, improve: {needed_str}",
            "next_steps": next_actions,
        },
        "recommendation": {"option": best, "score": scores[best]},
        "reasoning": [f"{best} wins on {axes_str}"],
        "rejected": [{"option": o, "score": s} for o, s in ranked[1:]],
        "next_actions": next_actions,
        "execution_tasks": [{"task": a, "status": "pending"} for a in next_actions],
        "preset": preset,
    }

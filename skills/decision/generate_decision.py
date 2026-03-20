
def _score_option_rule_based(option, criteria=None, context=None):
    t = str(option).lower()
    c = str(criteria).lower() if criteria else ""
    ctx = str(context).lower() if context else ""

    # base
    if "サブスク" in t:
        score = 80
    elif "買い切り" in t:
        score = 75
    else:
        score = 70

    # ===== 逆転条件 =====
    if "初期" in c or "すぐ" in c:
        if "買い切り" in t:
            score += 10
        if "サブスク" in t:
            score -= 10

    if "安定" in c or "継続" in c:
        if "サブスク" in t:
            score += 10
        if "買い切り" in t:
            score -= 5

    if "個別" in ctx or "受託" in ctx:
        if "サブスク" in t:
            score -= 10

    return score

    t = str(option).lower()
    if "サブスク" in t:
        return 80
    if "買い切り" in t:
        return 75
    return 70


def generate_decision(request: str, context=None, **kwargs):
    options = ["買い切り", "サブスク"]

    
    # criteria抽出
    r = request.lower()
    crit = []
    if "速" in r or "すぐ" in r:
        crit.append("speed")
    if "安定" in r or "継続" in r:
        crit.append("predict")
    if "スケール" in r or "拡張" in r:
        crit.append("scale")

    criteria = " ".join(crit) if crit else "default"

    context = request


    scores = {o: _score_option_rule_based(o, criteria, context) for o in options}

    # dynamic weights
    weights = {"speed":1.3,"predictability":1.2,"scalability":1.1}
    if "speed" in criteria:
        weights["speed"] += 0.5
    if "predict" in criteria:
        weights["predictability"] += 0.5
    if "scale" in criteria:
        weights["scalability"] += 0.5

    sorted_opts = sorted(options, key=lambda x: scores[x], reverse=True)

    return {
        "summary": "best option selected",
        "findings": [],
        "goal": "max monetization",
        "options": options,
        "criteria": ["speed", "predictability", "scalability"],
        "weights": weights,
        
        
        "comparison": [],
        "scores": scores,
        
        "proposal": {
            "title": "収益化戦略提案",
            "recommended_model": sorted_opts[0],
            "why": "継続収益 or 即金性の観点で最適",
            "expected_outcome": "短期〜中期での収益最大化",
            "risk": "モデル依存による収益偏り",
            "next_steps": [
                "ターゲット決定",
                "価格設計",
                "初期ユーザー検証"
            ]
        },
        "recommendation": {

            "option": sorted_opts[0],
            "score": scores[sorted_opts[0]]
        },
        "reasoning": ["subscription has recurring revenue"],
        "rejected": [
            {"option": o, "score": scores[o]} for o in sorted_opts[1:]
        ],
        "next_actions": [],
        "preset": "monetization"
    }

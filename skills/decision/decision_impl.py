#!/usr/bin/env python3
from __future__ import annotations

from typing import Dict, Any, List

DECISION_KEYWORDS = (
    "比較", "選定", "判断", "決めたい", "どれ", "優先", "優先順位",
    "choose", "compare", "decision", "decide", "prioritize", "priority",
)

def _derive_options(query: str) -> List[str]:
    q = (query or "").strip()
    if not q:
        return []

    seps = [" vs ", " VS ", " or ", " OR ", " と ", "、", ",", "/", "か"]
    parts = [q]
    for sep in seps:
        nxt = []
        for part in parts:
            if sep in part:
                nxt.extend([x.strip() for x in part.split(sep) if x.strip()])
            else:
                nxt.append(part)
        parts = nxt

    uniq = []
    for x in parts:
        if x and x not in uniq:
            uniq.append(x)
    return uniq[:5]

def run_decision(query: str) -> Dict[str, Any]:
    q = (query or "").strip()
    options = _derive_options(q)

    findings = [
        f"依頼文を確認: {q}",
        "判断軸を抽出: 価値 / コスト / 速度 / リスク の4軸で評価する",
    ]

    if len(options) >= 2:
        findings.append("候補を分解: " + " / ".join(options))
        findings.append("次アクション案: 候補ごとに4軸スコアを付けて上位1案を決定する")
        summary = "意思決定の下準備を完了した。比較軸を固定し、候補評価に進める。"
    else:
        findings.append("次アクション案: 候補を2〜5個に明示してから比較表を作成する")
        summary = "意思決定の下準備を完了した。候補不足のため、比較対象の明確化が必要。"

    return {
        "summary": summary,
        "findings": findings,
    }

def execute(query: str) -> Dict[str, Any]:
    return run_decision(query)

if __name__ == "__main__":
    import json
    import sys
    q = " ".join(sys.argv[1:]).strip()
    print(json.dumps(run_decision(q), ensure_ascii=False, indent=2))

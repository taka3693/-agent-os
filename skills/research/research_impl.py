#!/usr/bin/env python3

def run_research(query: str) -> dict:
    q = query.strip() if isinstance(query, str) else ""
    if not q:
        raise ValueError("query is required")

    findings = [
        f"依頼文を確認: {q}",
        "キーワード分解を実施: 比較/整理/要約の3観点で扱う",
        "次アクション案: 比較軸を3つに固定して情報を収集する",
    ]
    summary = "ローカル整形による調査下準備を完了した。"

    return {
        "summary": summary,
        "findings": findings,
    }

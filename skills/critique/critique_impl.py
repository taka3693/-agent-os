from __future__ import annotations

from typing import Any, Dict, List


def _normalize_query(query: Any) -> str:
    if query is None:
        return ""
    return str(query).strip()


def _make_findings(query: str) -> List[str]:
    findings: List[str] = []

    if not query:
        return [
            "入力が空。対象・目的・制約が不足している。",
            "評価基準が不明。何をもって良し悪しを判断するか未定義。",
            "次の一手がない。批評が実行へ接続していない。",
        ]

    if len(query) < 20:
        findings.append("入力が短い。背景・対象・成功条件が不足している可能性が高い。")

    if not any(k in query for k in ["目的", "ゴール", "成功", "評価", "基準", "KPI"]):
        findings.append("成功条件が未定義。批評の着地点が曖昧。")

    if not any(k in query for k in ["制約", "期限", "コスト", "リスク", "前提"]):
        findings.append("制約条件の記述が弱い。現実的な判断にならない恐れがある。")

    if not any(k in query for k in ["なぜ", "理由", "根拠"]):
        findings.append("理由・根拠の明示が弱い。印象批評になる危険がある。")

    if not findings:
        findings = [
            "主張の根拠はあるかを確認すべき。",
            "前提・制約の漏れを明示すべき。",
            "改善案を次のアクションまで落とすべき。",
        ]

    return findings[:5]


def run(query: str, **kwargs: Any) -> Dict[str, Any]:
    q = _normalize_query(query)
    findings = _make_findings(q)
    return {
        "ok": True,
        "skill": "critique",
        "query": q,
        "summary": "入力内容の批評観点を整理し、弱点・前提漏れ・実行性不足を指摘した。",
        "findings": findings,
    }


def execute(query: str, **kwargs: Any) -> Dict[str, Any]:
    return run(query, **kwargs)


def critique(query: str, **kwargs: Any) -> Dict[str, Any]:
    return run(query, **kwargs)

def run_critique(query: str, **kwargs):
    return run(query, **kwargs)

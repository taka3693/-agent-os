from __future__ import annotations

from typing import Any, List

from .constants import ROUTER_CATEGORY_ORDER, ROUTER_MAX_CHAIN

DECISION_KEYWORDS = [
    "比較",
    "選定",
    "判断",
    "決めたい",
    "どれ",
    "優先",
    "choose",
    "compare",
    "decision",
    "prioritize",
]

CRITIQUE_KEYWORDS = [
    "批評",
    "レビュー",
    "改善点",
    "問題点",
    "弱点",
    "欠点",
    "穴",
    "矛盾",
    "違和感",
    "甘い",
    "粗い",
    "詰めが甘い",
    "見落とし",
    "危険",
    "リスク",
    "critique",
    "review",
    "weakness",
    "issue",
    "risk",
]

EXPERIMENT_KEYWORDS = [
    "試す",
    "試したい",
    "テスト",
    "検証",
    "仮説",
    "実験",
    "試行",
    "比較実験",
    "experiment",
    "test",
    "validate",
    "validation",
    "try",
    "hypothesis",
]

EXECUTION_KEYWORDS = [
    "実行",
    "進める",
    "やる",
    "作る",
    "実装",
    "着手",
    "対応",
    "片付ける",
    "execute",
    "execution",
    "implement",
    "build",
    "do",
    "ship",
]

RETROSPECTIVE_KEYWORDS = [
    "振り返り",
    "ふりかえり",
    "反省",
    "レビュー会",
    "総括",
    "改善振り返り",
    "kpt",
    "keep",
    "problem",
    "try",
    "retrospective",
    "retro",
    "postmortem",
    "lessons learned",
]


def safe_text(text: Any) -> str:
    return "" if text is None else str(text)


def contains_any(text_lower: str, keywords: List[str]) -> bool:
    return any(str(k).lower() in text_lower for k in keywords)


def is_decision_text(text: str) -> bool:
    return contains_any(safe_text(text).lower(), DECISION_KEYWORDS)


def is_critique_text(text: str) -> bool:
    return contains_any(safe_text(text).lower(), CRITIQUE_KEYWORDS)


def is_experiment_text(text: str) -> bool:
    return contains_any(safe_text(text).lower(), EXPERIMENT_KEYWORDS)


def is_execution_text(text: str) -> bool:
    return contains_any(safe_text(text).lower(), EXECUTION_KEYWORDS)


def is_retrospective_text(text: str) -> bool:
    return contains_any(safe_text(text).lower(), RETROSPECTIVE_KEYWORDS)


def detect_route_candidates(text: str) -> List[str]:
    text_lower = safe_text(text).lower()
    candidates: List[str] = []

    checks = [
        ("critique", is_critique_text),
        ("decision", is_decision_text),
        ("experiment", is_experiment_text),
        ("execution", is_execution_text),
        ("retrospective", is_retrospective_text),
    ]

    for skill, fn in checks:
        if fn(text_lower):
            candidates.append(skill)

    if not candidates:
        candidates.append("research")

    ordered: List[str] = []
    for skill in ROUTER_CATEGORY_ORDER:
        if skill in candidates and skill not in ordered:
            ordered.append(skill)

    for skill in candidates:
        if skill not in ordered:
            ordered.append(skill)

    return ordered[:ROUTER_MAX_CHAIN]

#!/usr/bin/env python3
"""Step104/107: Evaluation Cases + Scenario Packs

Representative task cases for evaluating routing / execution / orchestration /
budget policy quality. Each case is a dict that can be fed into the policy
pipeline and checked against expected outputs.

Step107 adds scenario packs (budget_stress, failure_recovery, partial_heavy,
orchestration_boundary, routing_ambiguity, execution_risk) for targeted testing.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Case schema
# ---------------------------------------------------------------------------

def make_case(
    case_id: str,
    label: str,
    kind: str,
    text: str,
    task_context: Optional[Dict[str, Any]] = None,
    expected: Optional[Dict[str, Any]] = None,
    packs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create an evaluation case dict.

    Args:
        case_id: Unique identifier
        label: Human-readable description
        kind: Category (simple/decision/research/execution/complex/
                        failure_history/low_budget/orchestration)
        text: Query text fed into the router
        task_context: Optional context dict (budget, metrics, failure_history)
        expected: Expected assertions (key → value or callable)
        packs: Optional list of scenario pack names this case belongs to

    Returns:
        Case dict
    """
    return {
        "case_id": case_id,
        "label": label,
        "kind": kind,
        "text": text,
        "task_context": task_context or {},
        "expected": expected or {},
        "packs": packs or [],
    }


# ---------------------------------------------------------------------------
# Budget helpers
# ---------------------------------------------------------------------------

def _healthy_budget() -> Dict[str, Any]:
    return {
        "max_subtasks": 5,
        "spent_subtasks": 0,
        "max_worker_runs": 10,
        "spent_worker_runs": 0,
        "budget_limit_hits": 0,
    }


def _low_budget() -> Dict[str, Any]:
    """Low budget: only 1 worker run remaining."""
    return {
        "max_subtasks": 5,
        "spent_subtasks": 0,
        "max_worker_runs": 4,
        "spent_worker_runs": 3,
        "budget_limit_hits": 0,
    }


def _stressed_budget() -> Dict[str, Any]:
    """Stressed budget: zero remaining."""
    return {
        "max_subtasks": 5,
        "spent_subtasks": 5,
        "max_worker_runs": 10,
        "spent_worker_runs": 10,
        "budget_limit_hits": 1,
    }


def _exhausted_budget() -> Dict[str, Any]:
    """Exhausted: budget limit already hit."""
    return {
        "max_subtasks": 5,
        "spent_subtasks": 5,
        "max_worker_runs": 10,
        "spent_worker_runs": 10,
        "budget_limit_hits": 3,
    }


def _failure_metrics() -> Dict[str, Any]:
    return {
        "failed_steps": 5,
        "partial_runs": 1,
        "budget_limit_hits": 0,
    }


def _partial_metrics() -> Dict[str, Any]:
    return {
        "failed_steps": 1,
        "partial_runs": 3,
        "budget_limit_hits": 0,
    }


# ---------------------------------------------------------------------------
# Scenario packs
# ---------------------------------------------------------------------------

PACK_NAMES = [
    "budget_stress",
    "failure_recovery",
    "partial_heavy",
    "orchestration_boundary",
    "routing_ambiguity",
    "execution_risk",
]


def list_packs() -> List[str]:
    """Return list of available scenario pack names."""
    return list(PACK_NAMES)


def load_packs(packs: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Load cases belonging to specified packs.

    Args:
        packs: List of pack names to filter by. Empty list returns all.

    Returns:
        List of cases belonging to at least one of the specified packs.
    """
    if not packs:
        return list(EVAL_CASES)
    pack_set = set(packs)
    return [c for c in EVAL_CASES if pack_set & set(c.get("packs", []))]


# ---------------------------------------------------------------------------
# Representative cases
# ---------------------------------------------------------------------------

EVAL_CASES: List[Dict[str, Any]] = [
    # -----------------------------------------------------------------------
    # 1. Simple task
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-001",
        label="単純な調べ物",
        kind="simple",
        text="Python の list と tuple の違いは？",
        task_context={"budget": _healthy_budget(), "metrics": {}},
        expected={
            "execution_policy.tier": "balanced",
            "execution_policy.allow_orchestration": False,
        },
        packs=["routing_ambiguity"],
    ),

    # -----------------------------------------------------------------------
    # 2. Decision task
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-002",
        label="判断系タスク",
        kind="decision",
        text="AWS と GCP どちらを選定すべきか比較して判断してほしい",
        task_context={"budget": _healthy_budget(), "metrics": {}},
        expected={
            "selected_skill_in": ["decision", "research"],
            "execution_policy.tier_in": ["balanced", "thorough"],
        },
        packs=["orchestration_boundary"],
    ),

    # -----------------------------------------------------------------------
    # 3. Research task
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-003",
        label="調査系タスク",
        kind="research",
        text="最近の LLM の精度向上トレンドを調べてまとめてほしい",
        task_context={"budget": _healthy_budget(), "metrics": {}},
        expected={
            "selected_skill_in": ["research", "critique"],
        },
        packs=["routing_ambiguity"],
    ),

    # -----------------------------------------------------------------------
    # 4. Execution task
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-004",
        label="実行系タスク",
        kind="execution",
        text="CI パイプラインの実装を進めて手順を整理してほしい",
        task_context={"budget": _healthy_budget(), "metrics": {}},
        expected={
            "selected_skill_in": ["execution", "research"],
        },
        packs=["execution_risk"],
    ),

    # -----------------------------------------------------------------------
    # 5. High complexity task
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-005",
        label="高複雑度タスク（長文・多観点）",
        kind="complex",
        text=(
            "マイクロサービスアーキテクチャへの移行計画を比較・選定し、"
            "リスクを批評して実験的に検証してから実行手順に落とし込む "
        ) * 10,   # > 300 chars
        task_context={
            "budget": _healthy_budget(),
            "metrics": {},
            "complexity": "complex",
        },
        expected={
            "execution_policy.tier": "thorough",
            "execution_policy.allow_orchestration": True,
        },
        packs=["orchestration_boundary"],
    ),

    # -----------------------------------------------------------------------
    # 6. Failure history task
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-006",
        label="失敗履歴ありタスク",
        kind="failure_history",
        text="批評とレビューをお願いします",
        task_context={
            "budget": _healthy_budget(),
            "metrics": {"failed_steps": 6},
            "failure_history": {"critique": 5},
        },
        expected={
            "execution_policy.tier": "cheap",
            "execution_policy.allow_orchestration": False,
        },
        packs=["failure_recovery"],
    ),

    # -----------------------------------------------------------------------
    # 7. Low budget task
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-007",
        label="低予算タスク",
        kind="low_budget",
        text="比較して選定して実行してほしい",
        task_context={
            "budget": _low_budget(),
            "metrics": {},
        },
        expected={
            "execution_policy.tier": "cheap",
            "skill_chain_length_lte": 1,
        },
        packs=["budget_stress"],
    ),

    # -----------------------------------------------------------------------
    # 8. Orchestration candidate task
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-008",
        label="Orchestration 候補タスク",
        kind="orchestration",
        text=(
            "複数の技術選定肢を並列調査・比較・批評してからリスク評価し最終判断せよ "
        ) * 15,  # > 300 chars
        task_context={
            "budget": _healthy_budget(),
            "metrics": {},
            "complexity": "complex",
        },
        expected={
            "execution_policy.allow_orchestration": True,
            "routing_policy.orchestration_eligible": True,
        },
        packs=["orchestration_boundary"],
    ),

    # -----------------------------------------------------------------------
    # Pack: budget_stress (additional cases)
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-101",
        label="予算枯渇直前タスク",
        kind="low_budget",
        text="重要な比較判断をしたい",
        task_context={
            "budget": _stressed_budget(),
            "metrics": {},
        },
        expected={
            "execution_policy.tier": "cheap",
        },
        packs=["budget_stress"],
    ),
    make_case(
        case_id="case-102",
        label="予算完全枯渇タスク",
        kind="low_budget",
        text="追加調査が必要",
        task_context={
            "budget": _exhausted_budget(),
            "metrics": {},
        },
        expected={
            "execution_policy.tier": "cheap",
        },
        packs=["budget_stress"],
    ),
    make_case(
        case_id="case-103",
        label="残り1実行タスク",
        kind="low_budget",
        text="最後の判断をしたい",
        task_context={
            "budget": _low_budget(),
            "metrics": {},
        },
        expected={
            "skill_chain_length_lte": 1,
        },
        packs=["budget_stress"],
    ),

    # -----------------------------------------------------------------------
    # Pack: failure_recovery (additional cases)
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-201",
        label="連続失敗からの復旧タスク",
        kind="failure_history",
        text="再度批評をお願いします",
        task_context={
            "budget": _healthy_budget(),
            "metrics": _failure_metrics(),
            "failure_history": {"critique": 4, "decision": 2},
        },
        expected={
            "execution_policy.tier": "cheap",
            "execution_policy.allow_orchestration": False,
        },
        packs=["failure_recovery"],
    ),
    make_case(
        case_id="case-202",
        label="高失敗率実行タスク",
        kind="failure_history",
        text="実行を再試行したい",
        task_context={
            "budget": _healthy_budget(),
            "metrics": {"failed_steps": 8},
            "failure_history": {"execution": 6},
        },
        expected={
            "execution_policy.tier": "cheap",
        },
        packs=["failure_recovery"],
    ),

    # -----------------------------------------------------------------------
    # Pack: partial_heavy (additional cases)
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-301",
        label="部分成功多発タスク",
        kind="complex",
        text="複雑な分析と判断を段階的に進めたい",
        task_context={
            "budget": _healthy_budget(),
            "metrics": _partial_metrics(),
        },
        expected={
            # Should reinforce with critique/decision
        },
        packs=["partial_heavy"],
    ),
    make_case(
        case_id="case-302",
        label="頻繁な部分実行タスク",
        kind="execution",
        text="段階的実装を進めたい",
        task_context={
            "budget": _healthy_budget(),
            "metrics": {"partial_runs": 4},
        },
        expected={},
        packs=["partial_heavy"],
    ),

    # -----------------------------------------------------------------------
    # Pack: orchestration_boundary (additional cases)
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-401",
        label="境界ケース: 複雑だが予算少なめ",
        kind="complex",
        text=("複雑な技術選定を比較判断せよ " * 20),  # > 300 chars
        task_context={
            "budget": {  # Moderate budget, not quite enough for orchestration
                "max_subtasks": 5,
                "spent_subtasks": 2,
                "max_worker_runs": 10,
                "spent_worker_runs": 6,
            },
            "complexity": "complex",
        },
        expected={
            # May or may not allow orchestration - boundary case
        },
        packs=["orchestration_boundary"],
    ),
    make_case(
        case_id="case-402",
        label="境界ケース: 単純だが長文",
        kind="simple",
        text=("簡単な調査 " * 50),  # Long but simple
        task_context={
            "budget": _healthy_budget(),
        },
        expected={
            # boundary case: long text may be treated as complex by current policy
        },
        packs=["orchestration_boundary"],
    ),

    # -----------------------------------------------------------------------
    # Pack: routing_ambiguity (additional cases)
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-501",
        label="あいまいキーワードタスク",
        kind="simple",
        text="何か調べて整理してほしい",  # No clear skill keyword
        task_context={
            "budget": _healthy_budget(),
        },
        expected={
            "selected_skill_in": ["research"],  # Should fallback to research
        },
        packs=["routing_ambiguity"],
    ),
    make_case(
        case_id="case-502",
        label="複数スキルキーワード競合",
        kind="decision",
        text="比較判断して批評して実行してほしい",  # Multiple keywords
        task_context={
            "budget": _healthy_budget(),
        },
        expected={
            "selected_skill_in": ["decision", "critique", "execution", "research"],
        },
        packs=["routing_ambiguity"],
    ),

    # -----------------------------------------------------------------------
    # Pack: execution_risk (additional cases)
    # -----------------------------------------------------------------------
    make_case(
        case_id="case-601",
        label="高リスク実行タスク",
        kind="execution",
        text="本番環境へのデプロイを実行してほしい",
        task_context={
            "budget": _healthy_budget(),
            "metrics": {"failed_steps": 2},
        },
        expected={
            "execution_policy.tier_in": ["cheap", "balanced"],
        },
        packs=["execution_risk"],
    ),
    make_case(
        case_id="case-602",
        label="障害復旧実行タスク",
        kind="execution",
        text="障害対応を進めて復旧させてほしい",
        task_context={
            "budget": _healthy_budget(),
            "failure_history": {"execution": 3},
        },
        expected={
            "execution_policy.tier_in": ["cheap", "balanced"],
        },
        packs=["execution_risk", "failure_recovery"],
    ),
]


def load_cases(kinds: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Load evaluation cases, optionally filtered by kind."""
    if not kinds:
        return list(EVAL_CASES)
    return [c for c in EVAL_CASES if c["kind"] in kinds]

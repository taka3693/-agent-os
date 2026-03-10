from __future__ import annotations

from typing import Any, Dict


def make_plan_outline(text: str, selected_skills):
    text = "" if text is None else str(text).strip()
    skills = selected_skills if isinstance(selected_skills, list) and selected_skills else ["research"]

    steps = []
    for skill in skills:
        if skill == "research":
            steps.append({
                "skill": "research",
                "purpose": "入力内容の整理と情報抽出",
                "done_when": "要点・論点・不足情報が見える",
            })
        elif skill == "decision":
            steps.append({
                "skill": "decision",
                "purpose": "比較と優先順位づけ",
                "done_when": "採用候補と判断理由が明文化される",
            })
        elif skill == "critique":
            steps.append({
                "skill": "critique",
                "purpose": "弱点・前提漏れ・リスクの洗い出し",
                "done_when": "問題点と改善観点が列挙される",
            })
        elif skill == "experiment":
            steps.append({
                "skill": "experiment",
                "purpose": "仮説検証の最小実験化",
                "done_when": "仮説と検証手順が定義される",
            })
        elif skill == "execution":
            steps.append({
                "skill": "execution",
                "purpose": "実行手順への分解",
                "done_when": "着手可能な手順列になる",
            })
        elif skill == "retrospective":
            steps.append({
                "skill": "retrospective",
                "purpose": "結果の振り返りと改善抽出",
                "done_when": "次回アクションが明確になる",
            })
        else:
            steps.append({
                "skill": str(skill),
                "purpose": "未定義スキル",
                "done_when": "処理結果が返る",
            })

    goal = text if text else "入力要求を処理する"
    return {
        "goal": goal,
        "steps": steps,
        "step_count": len(steps),
        "mode": "autonomous_planning",
    }


def attach_autonomous_plan(route_result: Dict[str, Any], text: str) -> Dict[str, Any]:
    if not isinstance(route_result, dict):
        route_result = {}

    selected_skills = route_result.get("selected_skills")
    if not isinstance(selected_skills, list) or not selected_skills:
        selected_skills = [route_result.get("selected_skill") or "research"]

    out = dict(route_result)
    out["plan"] = make_plan_outline(text, selected_skills)
    out["planning_mode"] = "autonomous"
    return out

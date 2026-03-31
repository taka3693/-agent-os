"""Proactive Task Generator - 観察結果からタスクを自動生成

観察結果を分析し、実行可能なタスクを提案する。
全てのタスクは承認フローを経由する（安全性担保）。
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List
import uuid


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_task_id() -> str:
    return f"proactive-{uuid.uuid4().hex[:8]}"


class ProactiveTaskGenerator:
    """観察結果からタスクを生成"""
    
    def __init__(self, observations: Dict[str, Any]):
        self.observations = observations
        self.generated_tasks: List[Dict[str, Any]] = []
    
    def generate_all(self) -> List[Dict[str, Any]]:
        """全ての観察結果からタスクを生成"""
        self.generated_tasks = []
        
        self._generate_from_health()
        self._generate_from_failures()
        self._generate_from_learning()
        self._generate_from_idle()
        
        return self.generated_tasks
    
    def _generate_from_health(self) -> None:
        """ヘルス問題からタスク生成"""
        health = self.observations.get("health", {})
        issues = health.get("issues", [])
        
        for issue in issues:
            issue_type = issue.get("type")
            
            if issue_type == "high_failure_rate":
                self.generated_tasks.append({
                    "id": generate_task_id(),
                    "type": "maintenance",
                    "skill": "research",
                    "query": "失敗タスクの共通原因を分析し、改善策を提案してください",
                    "context": {
                        "trigger": "high_failure_rate",
                        "detail": issue.get("detail"),
                    },
                    "priority": "high",
                    "requires_approval": True,
                    "created_at": utc_now_iso(),
                    "source": "proactive_generator",
                })
            
            elif issue_type == "approval_backlog":
                self.generated_tasks.append({
                    "id": generate_task_id(),
                    "type": "notification",
                    "skill": None,  # 通知のみ
                    "query": f"承認待ちタスクが溜まっています: {issue.get('detail')}",
                    "context": {"trigger": "approval_backlog"},
                    "priority": "low",
                    "requires_approval": False,  # 通知は承認不要
                    "created_at": utc_now_iso(),
                    "source": "proactive_generator",
                })
    
    def _generate_from_failures(self) -> None:
        """失敗パターンからタスク生成"""
        failures = self.observations.get("failures", {})
        patterns = failures.get("patterns", [])
        
        high_severity = [p for p in patterns if p.get("severity") == "high"]
        
        for pattern in high_severity:
            error_type = pattern.get("error_type", "unknown")
            count = pattern.get("count", 0)
            
            self.generated_tasks.append({
                "id": generate_task_id(),
                "type": "improvement",
                "skill": "decision",
                "query": f"エラー '{error_type}' が {count} 回発生しています。対処方針を決定してください",
                "context": {
                    "trigger": "recurring_error",
                    "error_type": error_type,
                    "occurrence_count": count,
                },
                "priority": "high",
                "requires_approval": True,
                "created_at": utc_now_iso(),
                "source": "proactive_generator",
            })
    
    def _generate_from_learning(self) -> None:
        """学習結果からタスク生成"""
        learning = self.observations.get("learning", {})
        insights = learning.get("insights", [])
        
        for insight in insights:
            if insight.get("type") == "recurring_friction":
                self.generated_tasks.append({
                    "id": generate_task_id(),
                    "type": "improvement",
                    "skill": "retrospective",
                    "query": "高摩擦エピソードが繰り返し発生しています。承認ポリシーまたは自動化の改善を検討してください",
                    "context": {
                        "trigger": "recurring_friction",
                        "detail": insight.get("detail"),
                        "suggestion": insight.get("suggestion"),
                    },
                    "priority": "medium",
                    "requires_approval": True,
                    "created_at": utc_now_iso(),
                    "source": "proactive_generator",
                })
    
    def _generate_from_idle(self) -> None:
        """アイドル状態からタスク生成"""
        idle = self.observations.get("idle", {})
        
        if idle.get("is_idle"):
            # アイドル時は探索タスクを提案
            self.generated_tasks.append({
                "id": generate_task_id(),
                "type": "exploration",
                "skill": "research",
                "query": "システムの改善機会を探索してください。効率化、新機能、または技術的負債の解消について調査",
                "context": {"trigger": "system_idle"},
                "priority": "low",
                "requires_approval": True,
                "created_at": utc_now_iso(),
                "source": "proactive_generator",
            })


def generate_proactive_tasks(observations: Dict[str, Any]) -> List[Dict[str, Any]]:
    """便利関数: 観察結果からタスクを生成"""
    generator = ProactiveTaskGenerator(observations)
    return generator.generate_all()

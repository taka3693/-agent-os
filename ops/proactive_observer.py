"""Proactive Observer - 能動的タスク生成のための観察モジュール

Agent-OSが自律的に課題を発見し、タスクを提案するための観察機構。
観察結果は承認フローを経て実行される（安全性担保）。
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ProactiveObserver:
    """システム状態を観察し、課題を発見する"""
    
    def __init__(self, state_root: Path, tasks_root: Path, logs_root: Optional[Path] = None):
        self.state_root = state_root
        self.tasks_root = tasks_root
        self.logs_root = logs_root or state_root.parent / "logs"
    
    def observe_all(self) -> Dict[str, Any]:
        """全ての観察を実行し、統合結果を返す"""
        return {
            "observed_at": utc_now_iso(),
            "health": self.observe_health(),
            "failures": self.observe_failures(),
            "learning": self.observe_learning(),
            "idle": self.observe_idle(),
        }
    
    def observe_health(self) -> Dict[str, Any]:
        """ヘルス状態を観察"""
        health_file = self.state_root / "health_latest.json"
        if not health_file.exists():
            return {"status": "unknown", "issues": []}
        
        try:
            health = json.loads(health_file.read_text())
            issues = []
            
            # 失敗タスクが多い
            failed_count = health.get("failed_task_count", 0)
            if failed_count >= 3:
                issues.append({
                    "type": "high_failure_rate",
                    "severity": "warning",
                    "detail": f"{failed_count} failed tasks detected",
                })
            
            # 承認待ちが溜まっている
            pending_count = health.get("awaiting_approval_count", 0)
            if pending_count >= 5:
                issues.append({
                    "type": "approval_backlog",
                    "severity": "info",
                    "detail": f"{pending_count} tasks awaiting approval",
                })
            
            return {
                "status": "healthy" if not issues else "degraded",
                "issues": issues,
                "raw": health,
            }
        except Exception as e:
            return {"status": "error", "issues": [], "error": str(e)}
    
    def observe_failures(self) -> Dict[str, Any]:
        """失敗パターンを観察"""
        failures_file = self.state_root / "failed_tasks.jsonl"
        if not failures_file.exists():
            return {"patterns": [], "count": 0}
        
        try:
            failures = []
            for line in failures_file.read_text().strip().split("\n")[-20:]:  # 直近20件
                if line.strip():
                    failures.append(json.loads(line))
            
            # パターン分析（シンプル版）
            error_types: Dict[str, int] = {}
            for f in failures:
                error = f.get("error_type", "unknown")
                error_types[error] = error_types.get(error, 0) + 1
            
            patterns = [
                {"error_type": k, "count": v, "severity": "high" if v >= 3 else "low"}
                for k, v in error_types.items()
            ]
            
            return {"patterns": patterns, "count": len(failures)}
        except Exception as e:
            return {"patterns": [], "count": 0, "error": str(e)}
    
    def observe_learning(self) -> Dict[str, Any]:
        """学習結果から改善点を観察"""
        episodes_file = self.state_root.parent / "learning" / "learning_episodes.jsonl"
        if not episodes_file.exists():
            return {"insights": [], "episode_count": 0}
        
        try:
            episodes = []
            for line in episodes_file.read_text().strip().split("\n")[-50:]:
                if line.strip():
                    episodes.append(json.loads(line))
            
            # 高摩擦エピソードを抽出
            high_friction = [
                e for e in episodes
                if e.get("outcome") == "success_high_friction"
            ]
            
            insights = []
            if len(high_friction) >= 3:
                insights.append({
                    "type": "recurring_friction",
                    "detail": f"{len(high_friction)} high-friction episodes",
                    "suggestion": "Review approval policies or automation",
                })
            
            return {"insights": insights, "episode_count": len(episodes)}
        except Exception as e:
            return {"insights": [], "episode_count": 0, "error": str(e)}
    
    def observe_idle(self) -> Dict[str, Any]:
        """アイドル状態を観察"""
        # タスクキューが空かどうか
        pending_dir = self.tasks_root / "pending"
        running_dir = self.tasks_root / "running"
        
        pending_count = len(list(pending_dir.glob("*.json"))) if pending_dir.exists() else 0
        running_count = len(list(running_dir.glob("*.json"))) if running_dir.exists() else 0
        
        is_idle = pending_count == 0 and running_count == 0
        
        return {
            "is_idle": is_idle,
            "pending_count": pending_count,
            "running_count": running_count,
        }


def observe_system(state_root: Path, tasks_root: Path) -> Dict[str, Any]:
    """便利関数: システム全体を観察"""
    observer = ProactiveObserver(state_root, tasks_root)
    return observer.observe_all()

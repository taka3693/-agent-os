"""Failure Analyzer - 失敗ログから改善ポイントを特定

テスト失敗、実行エラー、タイムアウトなどを分析し、
修正可能なパターンを検出する。
"""
from __future__ import annotations
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"


def analyze_test_failures(test_output: str) -> List[Dict[str, Any]]:
    """pytestの出力から失敗を分析"""
    failures = []
    
    # FAILED パターン
    failed_pattern = r"FAILED\s+([\w/]+\.py)::([\w_]+)"
    for match in re.finditer(failed_pattern, test_output):
        failures.append({
            "type": "test_failure",
            "file": match.group(1),
            "test": match.group(2),
        })
    
    # ERROR パターン
    error_pattern = r"ERROR\s+([\w/]+\.py)::([\w_]+)"
    for match in re.finditer(error_pattern, test_output):
        failures.append({
            "type": "test_error",
            "file": match.group(1),
            "test": match.group(2),
        })
    
    # ImportError / ModuleNotFoundError
    import_pattern = r"(ImportError|ModuleNotFoundError):\s*(.+)"
    for match in re.finditer(import_pattern, test_output):
        failures.append({
            "type": "import_error",
            "error": match.group(1),
            "message": match.group(2),
        })
    
    return failures


def analyze_execution_logs(log_file: Optional[Path] = None) -> List[Dict[str, Any]]:
    """実行ログからエラーパターンを分析"""
    if log_file is None:
        log_file = STATE_DIR / "approval_executions.jsonl"
    
    if not log_file.exists():
        return []
    
    issues = []
    error_counts = Counter()
    timeout_count = 0
    
    for line in log_file.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            result = record.get("result", {})
            
            # タイムアウト検出
            orch_result = result.get("result", {}).get("orchestration_result", {})
            for subtask in orch_result.get("subtask_results", []):
                sub_result = subtask.get("result", {})
                if "timeout" in str(sub_result).lower():
                    timeout_count += 1
                    issues.append({
                        "type": "timeout",
                        "fingerprint": record.get("fingerprint"),
                        "action": record.get("action"),
                    })
                
                # エラー検出
                error = sub_result.get("error")
                if error:
                    error_counts[error] += 1
                    
        except json.JSONDecodeError:
            continue
    
    # 繰り返しエラーをissueに追加
    for error, count in error_counts.items():
        if count >= 2:
            issues.append({
                "type": "recurring_error",
                "error": error,
                "count": count,
            })
    
    return issues


def analyze_proactive_cycles() -> List[Dict[str, Any]]:
    """Proactiveサイクルの問題を分析"""
    cycle_file = STATE_DIR / "proactive_cycles.jsonl"
    
    if not cycle_file.exists():
        return []
    
    issues = []
    empty_cycles = 0
    total_cycles = 0
    
    for line in cycle_file.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            total_cycles += 1
            
            if record.get("generated_count", 0) == 0:
                empty_cycles += 1
                
        except json.JSONDecodeError:
            continue
    
    # 空サイクルが多い場合
    if total_cycles > 5 and empty_cycles / total_cycles > 0.5:
        issues.append({
            "type": "ineffective_proactive",
            "empty_cycles": empty_cycles,
            "total_cycles": total_cycles,
            "suggestion": "Expand observation triggers or reduce cooldown",
        })
    
    return issues


def get_improvement_suggestions(
    issues: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """問題から改善提案を生成"""
    suggestions = []
    
    for issue in issues:
        if issue["type"] == "timeout":
            suggestions.append({
                "priority": "high",
                "category": "performance",
                "suggestion": f"Increase timeout or optimize {issue.get('action')}",
                "affected": issue.get("fingerprint"),
            })
        
        elif issue["type"] == "recurring_error":
            suggestions.append({
                "priority": "high",
                "category": "reliability",
                "suggestion": f"Fix recurring error: {issue['error']}",
                "occurrences": issue["count"],
            })
        
        elif issue["type"] == "test_failure":
            suggestions.append({
                "priority": "medium",
                "category": "quality",
                "suggestion": f"Fix failing test: {issue['file']}::{issue['test']}",
                "file": issue["file"],
            })
        
        elif issue["type"] == "import_error":
            suggestions.append({
                "priority": "high",
                "category": "dependency",
                "suggestion": f"Fix import: {issue['message']}",
            })
        
        elif issue["type"] == "ineffective_proactive":
            suggestions.append({
                "priority": "low",
                "category": "optimization",
                "suggestion": issue["suggestion"],
            })
    
    return suggestions


def run_full_analysis() -> Dict[str, Any]:
    """全分析を実行"""
    all_issues = []
    
    # 実行ログ分析
    all_issues.extend(analyze_execution_logs())
    
    # Proactiveサイクル分析
    all_issues.extend(analyze_proactive_cycles())
    
    # 改善提案生成
    suggestions = get_improvement_suggestions(all_issues)
    
    return {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "issues_found": len(all_issues),
        "issues": all_issues,
        "suggestions": suggestions,
    }

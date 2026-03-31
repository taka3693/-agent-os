"""Limitation Detector - 限界を検出して適切に対応

実行中のタスクで限界に達したことを検出し、
適切なフォールバック行動を取る。
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"
LIMITATION_LOG = STATE_DIR / "limitation_events.jsonl"


# 限界検出のパターン
LIMITATION_PATTERNS = {
    "timeout": {
        "indicators": ["timeout", "timed out", "deadline exceeded"],
        "severity": "medium",
        "response": "retry_with_smaller_scope",
    },
    "rate_limit": {
        "indicators": ["rate limit", "too many requests", "429"],
        "severity": "low",
        "response": "wait_and_retry",
    },
    "auth_failure": {
        "indicators": ["unauthorized", "forbidden", "401", "403", "認証"],
        "severity": "high",
        "response": "escalate_to_user",
    },
    "resource_exhausted": {
        "indicators": ["out of memory", "quota exceeded", "disk full"],
        "severity": "high",
        "response": "abort_and_report",
    },
    "unknown_error": {
        "indicators": ["unknown error", "unexpected", "内部エラー"],
        "severity": "medium",
        "response": "log_and_retry",
    },
    "capability_exceeded": {
        "indicators": ["cannot", "unable to", "できない", "わからない"],
        "severity": "medium",
        "response": "admit_limitation",
    },
}


def detect_limitation(error_message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """エラーメッセージから限界を検出"""
    error_lower = error_message.lower()
    
    for pattern_name, pattern in LIMITATION_PATTERNS.items():
        for indicator in pattern["indicators"]:
            if indicator.lower() in error_lower:
                return {
                    "pattern": pattern_name,
                    "severity": pattern["severity"],
                    "recommended_response": pattern["response"],
                    "matched_indicator": indicator,
                    "original_error": error_message,
                    "context": context,
                }
    
    return None


def log_limitation_event(
    pattern: str,
    error: str,
    response_taken: str,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """限界イベントをログに記録"""
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pattern": pattern,
        "error": error,
        "response_taken": response_taken,
        "context": context or {},
    }
    
    with open(LIMITATION_LOG, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def get_limitation_response(limitation: Dict[str, Any]) -> Dict[str, Any]:
    """限界に対する適切な応答を生成"""
    response_type = limitation["recommended_response"]
    
    responses = {
        "retry_with_smaller_scope": {
            "action": "retry",
            "modifications": {"reduce_scope": True, "max_retries": 2},
            "message": "タイムアウトしました。範囲を縮小して再試行します。",
        },
        "wait_and_retry": {
            "action": "wait",
            "modifications": {"wait_seconds": 60, "then_retry": True},
            "message": "レート制限に達しました。少し待ってから再試行します。",
        },
        "escalate_to_user": {
            "action": "escalate",
            "modifications": {"require_user_input": True},
            "message": "認証が必要です。ユーザーの確認を待ちます。",
        },
        "abort_and_report": {
            "action": "abort",
            "modifications": {"generate_report": True},
            "message": "リソースが不足しています。タスクを中断し、レポートを生成します。",
        },
        "log_and_retry": {
            "action": "retry",
            "modifications": {"log_details": True, "max_retries": 1},
            "message": "予期しないエラーが発生しました。詳細をログに記録して再試行します。",
        },
        "admit_limitation": {
            "action": "admit",
            "modifications": {"suggest_alternative": True},
            "message": "この作業は私の能力の限界を超えています。代替案を提案します。",
        },
    }
    
    return responses.get(response_type, {
        "action": "unknown",
        "modifications": {},
        "message": "不明な状況です。ユーザーに確認してください。",
    })


def handle_limitation(
    error_message: str,
    context: Optional[Dict[str, Any]] = None,
    auto_respond: bool = True,
) -> Dict[str, Any]:
    """限界を検出し、適切に対応する
    
    Args:
        error_message: エラーメッセージ
        context: タスクコンテキスト
        auto_respond: 自動的に応答を実行するか
    
    Returns:
        {
            "limitation_detected": bool,
            "limitation": {...},
            "response": {...},
            "action_taken": str,
        }
    """
    limitation = detect_limitation(error_message, context)
    
    if not limitation:
        return {
            "limitation_detected": False,
            "limitation": None,
            "response": None,
            "action_taken": "none",
        }
    
    response = get_limitation_response(limitation)
    
    # ログに記録
    log_limitation_event(
        pattern=limitation["pattern"],
        error=error_message,
        response_taken=response["action"],
        context=context,
    )
    
    return {
        "limitation_detected": True,
        "limitation": limitation,
        "response": response,
        "action_taken": response["action"] if auto_respond else "pending",
    }


def get_limitation_stats() -> Dict[str, Any]:
    """限界イベントの統計を取得"""
    if not LIMITATION_LOG.exists():
        return {"total_events": 0, "patterns": {}}
    
    events = []
    for line in LIMITATION_LOG.read_text().strip().split("\n"):
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    
    pattern_counts = {}
    for event in events:
        pattern = event.get("pattern", "unknown")
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
    
    return {
        "total_events": len(events),
        "patterns": pattern_counts,
        "most_common": max(pattern_counts, key=pattern_counts.get) if pattern_counts else None,
    }

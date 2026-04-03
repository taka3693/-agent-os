"""Feedback Processor - ユーザーフィードバックの処理

ユーザーからのフィードバックを学習に反映する。
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"
LOG_DIR = PROJECT_ROOT / "logs"

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"feedback_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

FEEDBACK_FILE = STATE_DIR / "user_feedback.jsonl"


def record_feedback(
    task_id: str,
    feedback_type: str,
    rating: int,
    comment: Optional[str] = None,
    context: Optional[Dict] = None,
) -> Dict[str, Any]:
    """フィードバックを記録"""
    feedback = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "type": feedback_type,
        "rating": max(1, min(5, rating)),
        "comment": comment,
        "context": context or {},
        "processed": False,
    }
    
    with open(FEEDBACK_FILE, "a") as f:
        f.write(json.dumps(feedback, ensure_ascii=False) + "\n")
    
    logger.info(f"Recorded feedback for task {task_id}: {feedback_type} ({rating}/5)")
    return {"ok": True, "feedback_id": f"{task_id}-{feedback['timestamp']}"}


def get_feedback(task_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
    """フィードバックを取得"""
    if not FEEDBACK_FILE.exists():
        return []
    
    feedbacks = []
    for line in FEEDBACK_FILE.read_text().strip().split("\n"):
        if line.strip():
            try:
                fb = json.loads(line)
                if task_id is None or fb.get("task_id") == task_id:
                    feedbacks.append(fb)
            except json.JSONDecodeError:
                continue
    
    return feedbacks[-limit:]


def process_feedback() -> Dict[str, Any]:
    """未処理フィードバックを学習に反映"""
    feedbacks = get_feedback()
    unprocessed = [f for f in feedbacks if not f.get("processed")]
    
    if not unprocessed:
        return {"processed": 0, "adjustments": []}
    
    adjustments = []
    
    for fb in unprocessed:
        rating = fb.get("rating", 3)
        fb_type = fb.get("type", "general")
        context = fb.get("context", {})
        
        if rating <= 2:
            adjustments.append({
                "type": "negative_feedback",
                "task_type": context.get("task_type"),
                "action": "reduce_confidence",
                "parameters": context.get("parameters"),
            })
        elif rating >= 4:
            adjustments.append({
                "type": "positive_feedback",
                "task_type": context.get("task_type"),
                "action": "increase_confidence",
                "parameters": context.get("parameters"),
            })
    
    # Mark as processed
    if FEEDBACK_FILE.exists():
        lines = FEEDBACK_FILE.read_text().strip().split("\n")
        updated = []
        for line in lines:
            if line.strip():
                try:
                    fb = json.loads(line)
                    fb["processed"] = True
                    updated.append(json.dumps(fb, ensure_ascii=False))
                except json.JSONDecodeError:
                    updated.append(line)
        FEEDBACK_FILE.write_text("\n".join(updated) + "\n")
    
    logger.info(f"Processed {len(unprocessed)} feedbacks, {len(adjustments)} adjustments")
    return {"processed": len(unprocessed), "adjustments": adjustments}


def get_feedback_stats() -> Dict[str, Any]:
    """フィードバック統計を取得"""
    feedbacks = get_feedback()
    
    if not feedbacks:
        return {"total": 0, "avg_rating": 0, "by_type": {}}
    
    ratings = [f.get("rating", 3) for f in feedbacks]
    by_type = {}
    for fb in feedbacks:
        t = fb.get("type", "general")
        if t not in by_type:
            by_type[t] = {"count": 0, "ratings": []}
        by_type[t]["count"] += 1
        by_type[t]["ratings"].append(fb.get("rating", 3))
    
    for t in by_type:
        by_type[t]["avg_rating"] = sum(by_type[t]["ratings"]) / len(by_type[t]["ratings"])
        del by_type[t]["ratings"]
    
    return {
        "total": len(feedbacks),
        "avg_rating": sum(ratings) / len(ratings),
        "by_type": by_type,
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Feedback Processor CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    record_p = subparsers.add_parser("record", help="Record feedback")
    record_p.add_argument("--task-id", required=True)
    record_p.add_argument("--type", default="general")
    record_p.add_argument("--rating", type=int, required=True)
    record_p.add_argument("--comment", default=None)
    
    process_p = subparsers.add_parser("process", help="Process feedback")
    
    stats_p = subparsers.add_parser("stats", help="Get feedback stats")
    
    args = parser.parse_args()
    
    if args.command == "record":
        result = record_feedback(args.task_id, args.type, args.rating, args.comment)
        print(json.dumps(result, indent=2))
    elif args.command == "process":
        result = process_feedback()
        print(json.dumps(result, indent=2))
    elif args.command == "stats":
        result = get_feedback_stats()
        print(json.dumps(result, indent=2))

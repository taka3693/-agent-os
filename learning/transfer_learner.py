"""Transfer Learner - 過去の経験を類似タスクに転移

タスク間の類似度を計算し、知識を転移する。
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from difflib import SequenceMatcher

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"
LOG_DIR = PROJECT_ROOT / "logs"

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"transfer_learner_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

TRANSFER_FILE = STATE_DIR / "transfer_learning.jsonl"
LEARNING_FILE = STATE_DIR / "realtime_learning.jsonl"


def _load_learning_history() -> List[Dict[str, Any]]:
    """学習履歴を読み込み"""
    if not LEARNING_FILE.exists():
        return []
    entries = []
    for line in LEARNING_FILE.read_text().strip().split("\n"):
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _save_transfer(transfer: Dict[str, Any]) -> None:
    """転移記録を保存"""
    with open(TRANSFER_FILE, "a") as f:
        f.write(json.dumps(transfer, ensure_ascii=False) + "\n")


def _string_similarity(s1: str, s2: str) -> float:
    """文字列の類似度を計算"""
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


def _param_overlap(p1: Dict, p2: Dict) -> float:
    """パラメータの重なりを計算"""
    if not p1 or not p2:
        return 0.0
    keys1, keys2 = set(p1.keys()), set(p2.keys())
    if not keys1 or not keys2:
        return 0.0
    overlap = len(keys1 & keys2)
    return overlap / max(len(keys1), len(keys2))


def find_similar_tasks(task: Dict[str, Any], limit: int = 5) -> Dict[str, Any]:
    """類似タスクを検索"""
    task_type = task.get("type", "")
    task_params = task.get("params", {})
    
    history = _load_learning_history()
    if not history:
        return {"similar": [], "similarity_scores": []}
    
    scored = []
    for entry in history:
        entry_type = entry.get("task_type", "")
        entry_params = entry.get("task_params", {})
        
        type_sim = _string_similarity(task_type, entry_type)
        param_sim = _param_overlap(task_params, entry_params)
        
        total_sim = (type_sim * 0.6) + (param_sim * 0.4)
        
        if total_sim > 0.3:
            scored.append((entry, total_sim))
    
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:limit]
    
    return {
        "similar": [e[0] for e in top],
        "similarity_scores": [e[1] for e in top],
    }


def transfer_knowledge(
    source_task_type: str,
    target_task_type: str,
) -> Dict[str, Any]:
    """知識を転移"""
    history = _load_learning_history()
    
    source_entries = [e for e in history if e.get("task_type") == source_task_type and e.get("success")]
    
    if not source_entries:
        return {"transferred": [], "applicability": 0.0}
    
    transferred = []
    for entry in source_entries:
        for pattern in entry.get("patterns", []):
            transferred.append({
                "original_type": source_task_type,
                "target_type": target_task_type,
                "pattern": pattern,
                "confidence": pattern.get("confidence", 0.5) * 0.8,
            })
    
    type_sim = _string_similarity(source_task_type, target_task_type)
    
    transfer_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source_task_type,
        "target": target_task_type,
        "patterns_transferred": len(transferred),
        "applicability": type_sim,
    }
    _save_transfer(transfer_record)
    
    logger.info(f"Transferred {len(transferred)} patterns from {source_task_type} to {target_task_type}")
    
    return {"transferred": transferred, "applicability": type_sim}


def apply_transfer(task: Dict[str, Any]) -> Dict[str, Any]:
    """転移学習を適用"""
    task_type = task.get("type", "")
    
    similar = find_similar_tasks(task)
    
    suggestions = []
    source_tasks = []
    
    for entry, score in zip(similar["similar"], similar["similarity_scores"]):
        if score < 0.4:
            continue
        
        source_tasks.append(entry.get("task_type", "unknown"))
        
        for pattern in entry.get("patterns", []):
            if pattern.get("success", False):
                suggestions.append({
                    "type": "transfer",
                    "source": entry.get("task_type"),
                    "pattern": pattern.get("type"),
                    "value": pattern.get("value"),
                    "confidence": score * pattern.get("confidence", 0.5),
                })
    
    suggestions.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    
    return {
        "suggestions": suggestions[:10],
        "source_tasks": list(set(source_tasks)),
    }


def measure_transfer_effect(window_hours: int = 168) -> Dict[str, Any]:
    """転移学習の効果を測定"""
    if not TRANSFER_FILE.exists():
        return {"transfer_count": 0, "success_rate": 0.0}
    
    cutoff = datetime.now(timezone.utc).timestamp() - (window_hours * 3600)
    
    transfers = []
    for line in TRANSFER_FILE.read_text().strip().split("\n"):
        if line.strip():
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).timestamp()
                if ts >= cutoff:
                    transfers.append(entry)
            except (json.JSONDecodeError, KeyError):
                continue
    
    if not transfers:
        return {"transfer_count": 0, "success_rate": 0.0}
    
    total_patterns = sum(t.get("patterns_transferred", 0) for t in transfers)
    avg_applicability = sum(t.get("applicability", 0) for t in transfers) / len(transfers)
    
    return {
        "transfer_count": len(transfers),
        "total_patterns": total_patterns,
        "avg_applicability": avg_applicability,
        "success_rate": avg_applicability,
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Transfer Learning CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    similar_p = subparsers.add_parser("similar", help="Find similar tasks")
    similar_p.add_argument("--task-type", required=True)
    
    transfer_p = subparsers.add_parser("transfer", help="Transfer knowledge")
    transfer_p.add_argument("--source", required=True)
    transfer_p.add_argument("--target", required=True)
    
    measure_p = subparsers.add_parser("measure", help="Measure transfer effect")
    measure_p.add_argument("--window", type=int, default=168)
    
    args = parser.parse_args()
    
    if args.command == "similar":
        result = find_similar_tasks({"type": args.task_type})
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "transfer":
        result = transfer_knowledge(args.source, args.target)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.command == "measure":
        result = measure_transfer_effect(args.window)
        print(json.dumps(result, indent=2, ensure_ascii=False))

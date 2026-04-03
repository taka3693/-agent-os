"""
Realtime Learner for Agent OS

Learns from task execution results in real-time.
Records success/failure patterns immediately and applies learning to future tasks.
Measures learning effectiveness over time.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"

# Create directory
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(PROJECT_ROOT / "logs" / f"realtime_learner_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ===== MISO Integration =====

MISO_AVAILABLE = False
try:
    from miso.bridge import start_mission, update_agent_status, complete_mission, fail_mission
    MISO_AVAILABLE = True
    logger.info("MISO bridge is available")
except ImportError:
    logger.warning("MISO bridge not available")


# ===== Learning Storage =====

LEARNING_FILE = STATE_DIR / "realtime_learning.jsonl"


def save_learning(entry: Dict[str, Any]) -> None:
    """Save a learning entry to the learning file"""
    with open(LEARNING_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_learning_entries(
    task_type: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Load learning entries, optionally filtered by task type"""
    entries = []

    if not LEARNING_FILE.exists():
        return entries

    try:
        with open(LEARNING_FILE, "r") as f:
            lines = f.readlines()

        # Get last N lines in reverse order
        for line in reversed(lines[-limit:]):
            if line.strip():
                try:
                    entry = json.loads(line)
                    if task_type is None or entry.get("task_type") == task_type:
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"Failed to load learning entries: {e}")

    return entries


# ===== Pattern Extraction =====

def extract_success_patterns(task: Dict[str, Any], result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract success patterns from a successful task execution.

    Args:
        task: Task dict with type, parameters, etc.
        result: Execution result

    Returns:
        List of success patterns
    """
    patterns = []
    task_type = task.get("type", "unknown")

    # Pattern 1: Parameter combinations
    params = task.get("parameters", {})
    if params:
        patterns.append({
            "type": "parameter_combination",
            "task_type": task_type,
            "parameters": params,
            "success_rate": 1.0,
            "sample_size": 1,
            "description": f"Successful parameter set for {task_type}"
        })

    # Pattern 2: Execution time optimization
    if "execution_time" in result:
        exec_time = result["execution_time"]
        if exec_time > 0:
            patterns.append({
                "type": "execution_time",
                "task_type": task_type,
                "optimal_time": exec_time,
                "parameters": params,
                "description": f"Optimal execution time for {task_type}: {exec_time:.2f}s"
            })

    # Pattern 3: Resource usage
    if "resource_usage" in result:
        usage = result["resource_usage"]
        patterns.append({
            "type": "resource_usage",
            "task_type": task_type,
            "memory_mb": usage.get("memory_mb", 0),
            "cpu_percent": usage.get("cpu_percent", 0),
            "parameters": params,
            "description": f"Resource usage for {task_type}"
        })

    # Pattern 4: Model selection
    if "model" in task:
        patterns.append({
            "type": "model_selection",
            "task_type": task_type,
            "model": task["model"],
            "success": True,
            "description": f"Successful model for {task_type}: {task['model']}"
        })

    return patterns


def extract_failure_patterns(task: Dict[str, Any], result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract failure patterns from a failed task execution.

    Args:
        task: Task dict
        result: Execution result

    Returns:
        List of failure patterns with mitigation strategies
    """
    patterns = []
    task_type = task.get("type", "unknown")
    error = result.get("error", "Unknown error")

    # Pattern 1: Parameter issues
    params = task.get("parameters", {})
    patterns.append({
        "type": "parameter_failure",
        "task_type": task_type,
        "parameters": params,
        "error": error,
        "mitigation": "Try different parameter values",
        "description": f"Failed parameters for {task_type}: {error}"
    })

    # Pattern 2: Timeout patterns
    if "timeout" in result and result["timeout"]:
        patterns.append({
            "type": "timeout_failure",
            "task_type": task_type,
            "parameters": params,
            "mitigation": "Increase timeout or optimize task",
            "description": f"Timeout for {task_type}, consider increasing timeout"
        })

    # Pattern 3: Resource exhaustion
    if "error" in result and any(keyword in error.lower() for keyword in ["memory", "out of memory", "oom"]):
        patterns.append({
            "type": "resource_failure",
            "task_type": task_type,
            "resource": "memory",
            "mitigation": "Reduce memory usage or increase available memory",
            "description": f"Memory exhaustion for {task_type}"
        })

    # Pattern 4: Model-specific failures
    if "model" in task and "model" in error.lower():
        patterns.append({
            "type": "model_failure",
            "task_type": task_type,
            "model": task["model"],
            "mitigation": "Try a different model",
            "description": f"Model {task['model']} failed for {task_type}"
        })

    return patterns


# ===== Learning Functions =====

def learn_from_execution(
    task: Dict[str, Any],
    result: Dict[str, Any],
    chat_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Learn from a task execution result in real-time.

    Args:
        task: Task dict with type, parameters, etc.
        result: Execution result
        chat_id: Telegram chat ID for MISO

    Returns:
        Dict with learning results
    """
    task_type = task.get("type", "unknown")
    success = result.get("ok", False)

    logger.info(f"Learning from execution: {task_type} (success={success})")

    # Create learning entry
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "task_type": task_type,
        "task": task,
        "result": result,
        "success": success,
        "patterns": [],
    }

    # Extract patterns based on success/failure
    if success:
        entry["patterns"] = extract_success_patterns(task, result)
    else:
        entry["patterns"] = extract_failure_patterns(task, result)

    # Save learning entry
    save_learning(entry)

    # Update MISO if available
    if MISO_AVAILABLE and chat_id:
        try:
            mission_id = f"learning-{task_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            start_mission(
                mission_id=mission_id,
                mission_name=f"Learning: {task_type}",
                goal=f"Learn from {task_type} execution",
                chat_id=chat_id,
                agents=["learner"]
            )
            update_agent_status(mission_id, "learner", "DONE")
            complete_mission(mission_id, f"Learned {len(entry['patterns'])} patterns")
        except Exception as e:
            logger.warning(f"Failed to update MISO: {e}")

    return {
        "ok": True,
        "learned": len(entry["patterns"]) > 0,
        "patterns": entry["patterns"],
        "entry_id": entry["id"]
    }


def get_learned_patterns(task_type: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get learned patterns for a specific task type.

    Args:
        task_type: Type of task
        limit: Maximum number of patterns to return

    Returns:
        List of learned patterns
    """
    entries = load_learning_entries(task_type=task_type, limit=limit * 2)  # Get more for deduplication

    # Aggregate and deduplicate patterns
    pattern_map = {}

    for entry in entries:
        for pattern in entry.get("patterns", []):
            key = f"{pattern['type']}_{pattern.get('description', '')}"

            if key not in pattern_map:
                pattern_map[key] = {
                    **pattern,
                    "success_count": 0,
                    "failure_count": 0,
                    "last_seen": entry["timestamp"],
                }

            # Update counts
            if entry["success"]:
                pattern_map[key]["success_count"] += 1
            else:
                pattern_map[key]["failure_count"] += 1

            # Update last seen
            if entry["timestamp"] > pattern_map[key]["last_seen"]:
                pattern_map[key]["last_seen"] = entry["timestamp"]

    # Convert to list and calculate success rate
    patterns = []
    for pattern in pattern_map.values():
        total = pattern["success_count"] + pattern["failure_count"]
        pattern["success_rate"] = pattern["success_count"] / total if total > 0 else 0
        pattern["sample_size"] = total
        patterns.append(pattern)

    # Sort by success rate (descending) and recency
    patterns.sort(key=lambda p: (p["success_rate"], p["last_seen"]), reverse=True)

    return patterns[:limit]


def apply_learning(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply learned patterns to a task before execution.

    Args:
        task: Task dict to apply learning to

    Returns:
        Dict with suggested adjustments and confidence
    """
    task_type = task.get("type", "unknown")
    logger.info(f"Applying learning to task: {task_type}")

    patterns = get_learned_patterns(task_type)
    adjustments = []

    # Find relevant patterns
    for pattern in patterns:
        pattern_type = pattern["type"]

        if pattern_type == "parameter_combination" and pattern["success_rate"] > 0.7:
            # Suggest using successful parameters
            adjustments.append({
                "type": "parameter_adjustment",
                "suggestion": pattern["parameters"],
                "confidence": pattern["success_rate"],
                "description": "Use parameters from successful execution"
            })

        elif pattern_type == "execution_time":
            # Suggest expected execution time
            adjustments.append({
                "type": "time_estimation",
                "expected_time": pattern["optimal_time"],
                "confidence": pattern["success_rate"],
                "description": f"Expected execution time: {pattern['optimal_time']:.2f}s"
            })

        elif pattern_type == "model_selection" and pattern["success"]:
            # Suggest using successful model
            adjustments.append({
                "type": "model_suggestion",
                "suggested_model": pattern["model"],
                "confidence": pattern["success_rate"],
                "description": f"Use model: {pattern['model']}"
            })

        elif pattern_type == "parameter_failure" and pattern["success_rate"] < 0.3:
            # Suggest avoiding failed parameters
            adjustments.append({
                "type": "parameter_avoidance",
                "avoid_parameters": pattern["parameters"],
                "confidence": 1.0 - pattern["success_rate"],
                "description": "Avoid parameters from failed executions"
            })

        elif pattern_type == "timeout_failure":
            # Suggest increasing timeout
            adjustments.append({
                "type": "timeout_adjustment",
                "suggestion": "increase_timeout",
                "confidence": 0.8,
                "description": "Consider increasing timeout for this task"
            })

        elif pattern_type == "resource_failure":
            # Suggest resource optimization
            adjustments.append({
                "type": "resource_optimization",
                "suggestion": "reduce_memory_usage",
                "confidence": 0.8,
                "description": "Optimize memory usage for this task"
            })

        elif pattern_type == "model_failure":
            # Suggest avoiding failed model
            adjustments.append({
                "type": "model_avoidance",
                "avoid_model": pattern["model"],
                "confidence": 0.8,
                "description": f"Avoid model: {pattern['model']}"
            })

    # Calculate overall confidence
    if adjustments:
        confidence = sum(a["confidence"] for a in adjustments) / len(adjustments)
    else:
        confidence = 0.0

    return {
        "ok": True,
        "adjustments": adjustments,
        "confidence": confidence,
        "patterns_used": len(patterns)
    }


def measure_learning_effect(window_hours: int = 24) -> Dict[str, Any]:
    """
    Measure the effectiveness of learning over time.

    Args:
        window_hours: Time window in hours to analyze

    Returns:
        Dict with improvement metrics
    """
    logger.info(f"Measuring learning effect over {window_hours} hours")

    # Load all entries within time window
    entries = load_learning_entries(limit=1000)

    # Filter by time window
    cutoff_time = datetime.now().timestamp() - (window_hours * 3600)
    window_entries = [
        e for e in entries
        if datetime.fromisoformat(e["timestamp"]).timestamp() > cutoff_time
    ]

    if not window_entries:
        return {
            "ok": True,
            "window_hours": window_hours,
            "total_entries": 0,
            "improvement_rate": 0.0,
            "patterns_count": 0,
            "success_rate": 0.0,
            "message": "No entries in time window"
        }

    # Calculate metrics
    total = len(window_entries)
    successes = sum(1 for e in window_entries if e["success"])
    total_patterns = sum(len(e["patterns"]) for e in window_entries)
    success_rate = successes / total if total > 0 else 0

    # Calculate improvement rate (trend over time)
    if len(window_entries) >= 10:
        # Split window into two halves
        mid = len(window_entries) // 2
        first_half = window_entries[:mid]
        second_half = window_entries[mid:]

        first_success = sum(1 for e in first_half if e["success"])
        second_success = sum(1 for e in second_half if e["success"])

        first_rate = first_success / len(first_half) if first_half else 0
        second_rate = second_success / len(second_half) if second_half else 0

        improvement_rate = second_rate - first_rate
    else:
        improvement_rate = 0.0

    result = {
        "ok": True,
        "window_hours": window_hours,
        "total_entries": total,
        "successes": successes,
        "failures": total - successes,
        "success_rate": success_rate,
        "total_patterns": total_patterns,
        "improvement_rate": improvement_rate,
        "patterns_per_entry": total_patterns / total if total > 0 else 0,
        "measured_at": datetime.now().isoformat(),
    }

    logger.info(f"Learning effect: success_rate={success_rate:.2%}, improvement={improvement_rate:.2%}")

    return result


# ===== CLI Entry Point =====

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Realtime Learner for Agent OS")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # learn
    learn_parser = subparsers.add_parser("learn", help="Learn from task execution")
    learn_parser.add_argument("--task-type", required=True, help="Task type")
    learn_parser.add_argument("--success", type=bool, default=True, help="Success status")
    learn_parser.add_argument("--error", help="Error message (if failed)")
    learn_parser.add_argument("--chat-id", help="Telegram chat ID")
    learn_parser.set_defaults(
        func=lambda args: print(json.dumps(
            learn_from_execution(
                {"type": args.task_type, "parameters": {}},
                {"ok": args.success, "error": args.error},
                args.chat_id
            ),
            indent=2,
            ensure_ascii=False
        ))
    )

    # patterns
    patterns_parser = subparsers.add_parser("patterns", help="Get learned patterns")
    patterns_parser.add_argument("--task-type", required=True, help="Task type")
    patterns_parser.add_argument("--limit", type=int, default=10, help="Max patterns")
    patterns_parser.set_defaults(
        func=lambda args: print(json.dumps(get_learned_patterns(args.task_type, args.limit), indent=2, ensure_ascii=False))
    )

    # apply
    apply_parser = subparsers.add_parser("apply", help="Apply learning to a task")
    apply_parser.add_argument("--task-type", required=True, help="Task type")
    apply_parser.set_defaults(
        func=lambda args: print(json.dumps(apply_learning({"type": args.task_type}), indent=2, ensure_ascii=False))
    )

    # measure
    measure_parser = subparsers.add_parser("measure", help="Measure learning effect")
    measure_parser.add_argument("--window", type=int, default=24, help="Time window in hours")
    measure_parser.set_defaults(
        func=lambda args: print(json.dumps(measure_learning_effect(args.window), indent=2, ensure_ascii=False))
    )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

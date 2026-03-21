#!/usr/bin/env python3
"""Test unified task factory.

Validates:
1. create_skill_task() returns expected schema
2. create_followup_task() creates proper child tasks
3. maybe_create_followup_task() uses factory
"""
import json
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))
from router.task_factory import (
    create_skill_task,
    create_followup_task,
    make_task_id,
)
from router.model_policy import resolve_model_for_skill


def test_make_task_id_format():
    """Test task ID format."""
    task_id = make_task_id()
    parts = task_id.split("-")
    
    # Format: task-YYYYMMDD-HHMMSS-ffffff-XXXXXX
    assert task_id.startswith("task-"), f"ID should start with 'task-', got: {task_id}"
    assert len(parts) >= 4, f"ID should have at least 4 parts, got: {task_id}"
    return True


def test_create_skill_task_schema():
    """Test create_skill_task returns expected schema."""
    task = create_skill_task(
        skill="research",
        query="test query",
        source="test",
        chain_count=0,
    )
    
    # Required fields
    required_fields = [
        "task_id", "created_at", "updated_at", "selected_skill",
        "input_text", "run_input", "status", "chain_count",
        "model", "parent_task_id", "source", "result", "error"
    ]
    
    for field in required_fields:
        assert field in task, f"Missing required field: {field}"
    
    # Value checks
    assert task["selected_skill"] == "research"
    assert task["input_text"] == "test query"
    assert task["status"] == "queued"
    assert task["chain_count"] == 0
    assert task["model"] == resolve_model_for_skill("research")
    assert task["parent_task_id"] is None
    assert task["result"] is None
    assert task["error"] is None
    
    # run_input should contain query
    assert task["run_input"]["query"] == "test query"
    
    return True


def test_create_skill_task_with_parent():
    """Test create_skill_task with parent_task_id."""
    task = create_skill_task(
        skill="critique",
        query="review this",
        parent_task_id="task-20260318-001",
        chain_count=1,
    )
    
    assert task["parent_task_id"] == "task-20260318-001"
    assert task["chain_count"] == 1
    assert task["selected_skill"] == "critique"
    
    return True


def test_create_followup_task():
    """Test create_followup_task creates proper child."""
    parent = {
        "task_id": "task-parent-001",
        "chain_count": 0,
        "source": "agent_os",
    }
    
    child = create_followup_task(
        parent_task=parent,
        next_skill="critique",
        query="review query",
    )
    
    assert child["parent_task_id"] == "task-parent-001"
    assert child["chain_count"] == 1
    assert child["selected_skill"] == "critique"
    assert child["input_text"] == "review query"
    assert child["status"] == "queued"
    assert "chained_from:task-parent-001" in child.get("route_reason", "")
    
    return True


def test_model_resolution():
    """Test that model is resolved correctly for each skill."""
    skills = ["research", "decision", "execution", "critique", "retrospective"]
    
    for skill in skills:
        task = create_skill_task(skill=skill, query="test")
        expected_model = resolve_model_for_skill(skill)
        assert task["model"] == expected_model, \
            f"Model mismatch for {skill}: expected {expected_model}, got {task['model']}"
    
    return True


def test_extra_fields():
    """Test that extra_fields are merged correctly."""
    task = create_skill_task(
        skill="research",
        query="test",
        extra_fields={"custom_field": "custom_value"}
    )
    
    assert task["custom_field"] == "custom_value"
    
    # Core fields should not be overwritten
    task2 = create_skill_task(
        skill="research",
        query="test",
        extra_fields={"selected_skill": "should_not_overwrite"}
    )
    
    assert task2["selected_skill"] == "research"
    
    return True


def test_maybe_create_followup_uses_factory():
    """Test that maybe_create_followup_task uses the factory."""
    from runner.run_research_task import maybe_create_followup_task
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tasks_dir = Path(tmpdir)
        
        # Create parent task file
        parent_path = tasks_dir / "task-20260318-001.json"
        parent_task = {
            "task_id": "task-20260318-001",
            "selected_skill": "execution",
            "chain_count": 0,
            "source": "test",
            "input_text": "test query",
            "run_input": {"query": "test query"},
        }
        parent_path.write_text(json.dumps(parent_task, indent=2))
        
        # Mock result that triggers follow-up
        result = {"artifacts": [], "summary": "done"}
        
        child_path_str = maybe_create_followup_task(parent_path, parent_task, result)
        
        if child_path_str is None:
            print("ERROR: maybe_create_followup_task returned None")
            return False
        
        child_path = Path(child_path_str)
        assert child_path.exists(), f"Child file not created: {child_path}"
        
        child = json.loads(child_path.read_text())
        
        # Verify factory was used (schema should match)
        assert "task_id" in child
        assert child["selected_skill"] == "critique"
        assert child["parent_task_id"] == "task-20260318-001"
        assert child["chain_count"] == 1
        assert child["status"] == "queued"
        
        return True


def main():
    tests = [
        ("make_task_id_format", test_make_task_id_format),
        ("create_skill_task_schema", test_create_skill_task_schema),
        ("create_skill_task_with_parent", test_create_skill_task_with_parent),
        ("create_followup_task", test_create_followup_task),
        ("model_resolution", test_model_resolution),
        ("extra_fields", test_extra_fields),
        ("maybe_create_followup_uses_factory", test_maybe_create_followup_uses_factory),
    ]
    
    results = []
    all_passed = True
    
    for name, fn in tests:
        try:
            passed = fn()
            results.append({"name": name, "passed": passed})
            if not passed:
                all_passed = False
        except Exception as e:
            import traceback
            results.append({"name": name, "passed": False, "error": str(e)})
            all_passed = False
    
    print(json.dumps({
        "ok": all_passed,
        "test_count": len(tests),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "results": results
    }, indent=2))
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

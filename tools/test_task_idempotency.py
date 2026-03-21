#!/usr/bin/env python3
"""Test idempotency of follow-up task creation.

Validates that calling maybe_create_followup_task() multiple times
with the same parent task does NOT create duplicate children.
"""
import json
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))
from runner.run_research_task import (
    maybe_create_followup_task,
    MAX_CHAIN_COUNT,
)
from router.task_factory import make_task_id as factory_make_task_id


def create_mock_parent_task(task_path: Path, task_id: str, skill: str, chain_count: int = 0) -> dict:
    """Create a mock parent task file."""
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    task = {
        "task_id": task_id,
        "created_at": ts,
        "updated_at": ts,
        "selected_skill": skill,
        "chain_count": chain_count,
        "input_text": "test query",
        "run_input": {"query": "test query"},
        "status": "completed",
        "result": {},
    }
    task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n")
    return task


def test_idempotency_execution_to_critique():
    """Test that calling maybe_create_followup_task twice returns the same child."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tasks_dir = Path(tmpdir)

        # Create parent task
        parent_path = tasks_dir / "task-20260318-001.json"
        parent_task = create_mock_parent_task(parent_path, "task-20260318-001", "execution", chain_count=0)

        # Mock result that triggers follow-up (execution → critique)
        result = {"artifacts": [], "summary": "test execution"}

        # First call - should create child
        child_path_1 = maybe_create_followup_task(parent_path, parent_task, result)

        if child_path_1 is None:
            print(json.dumps({"ok": False, "error": "first call returned None"}))
            return False

        # Verify child was created
        child_1 = json.loads(Path(child_path_1).read_text())
        if child_1.get("parent_task_id") != "task-20260318-001":
            print(json.dumps({"ok": False, "error": "child parent_task_id mismatch"}))
            return False
        if child_1.get("selected_skill") != "critique":
            print(json.dumps({"ok": False, "error": "child selected_skill mismatch"}))
            return False

        # Update parent task with next_task_path (simulating save after first call)
        parent_task["next_task_path"] = child_path_1

        # Second call - should return existing child, NOT create new one
        child_path_2 = maybe_create_followup_task(parent_path, parent_task, result)

        if child_path_2 is None:
            print(json.dumps({"ok": False, "error": "second call returned None"}))
            return False

        if child_path_1 != child_path_2:
            print(json.dumps({
                "ok": False,
                "error": "second call created a new child instead of reusing",
                "child_1": child_path_1,
                "child_2": child_path_2
            }))
            return False

        # Verify only one child file exists
        child_files = list(tasks_dir.glob("task-*.json"))
        child_files = [f for f in child_files if f.name != "task-20260318-001.json"]
        if len(child_files) != 1:
            print(json.dumps({
                "ok": False,
                "error": "multiple child files exist",
                "count": len(child_files),
                "files": [f.name for f in child_files]
            }))
            return False

        return True


def test_idempotency_without_next_task_path():
    """Test that even without caller managing next_task_path, idempotency is maintained.

    With the new implementation, maybe_create_followup_task() updates parent
    automatically, so second call will find the existing child and reuse it.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tasks_dir = Path(tmpdir)

        parent_path = tasks_dir / "task-20260318-002.json"
        parent_task = create_mock_parent_task(parent_path, "task-20260318-002", "execution", chain_count=0)

        result = {"artifacts": [], "summary": "test"}

        # First call
        child_path_1 = maybe_create_followup_task(parent_path, parent_task, result)

        # Parent is now updated by maybe_create_followup_task()
        # Reload parent to see the update
        parent_reloaded = json.loads(parent_path.read_text())

        # Second call - should reuse existing child due to auto-saved next_task_path
        child_path_2 = maybe_create_followup_task(parent_path, parent_reloaded, result)

        # These should be the SAME (idempotency is maintained automatically)
        if child_path_1 != child_path_2:
            print(json.dumps({
                "ok": False,
                "error": "expected same child with auto-saved next_task_path",
                "child_1": child_path_1,
                "child_2": child_path_2
            }))
            return False

        # Verify parent has next_task_path
        if not parent_reloaded.get("next_task_path"):
            print(json.dumps({
                "ok": False,
                "error": "parent should have next_task_path after maybe_create_followup_task"
            }))
            return False

        return True


def test_chain_count_limit():
    """Test that MAX_CHAIN_COUNT prevents follow-up creation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tasks_dir = Path(tmpdir)

        parent_path = tasks_dir / "task-20260318-003.json"
        # Set chain_count to MAX
        parent_task = create_mock_parent_task(
            parent_path,
            "task-20260318-003",
            "execution",
            chain_count=MAX_CHAIN_COUNT
        )

        result = {"artifacts": [], "summary": "test"}

        child_path = maybe_create_followup_task(parent_path, parent_task, result)

        if child_path is not None:
            print(json.dumps({
                "ok": False,
                "error": "follow-up created despite MAX_CHAIN_COUNT"
            }))
            return False

        return True


def test_invalid_existing_child_rejected():
    """Test that an existing child with wrong parent_task_id is rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tasks_dir = Path(tmpdir)

        # Create parent
        parent_path = tasks_dir / "task-20260318-004.json"
        parent_task = create_mock_parent_task(parent_path, "task-20260318-004", "execution", chain_count=0)

        # Create a fake existing child with WRONG parent_task_id
        fake_child_path = tasks_dir / "task-20260318-999.json"
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        fake_child = {
            "task_id": "task-20260318-999",
            "parent_task_id": "different-parent",  # WRONG
            "selected_skill": "critique",
            "status": "queued",
        }
        fake_child_path.write_text(json.dumps(fake_child, indent=2))

        # Set parent to point to fake child
        parent_task["next_task_path"] = str(fake_child_path)

        result = {"artifacts": [], "summary": "test"}

        # Should NOT reuse fake child, should create new one
        child_path = maybe_create_followup_task(parent_path, parent_task, result)

        if child_path is None:
            print(json.dumps({"ok": False, "error": "returned None"}))
            return False

        if child_path == str(fake_child_path):
            print(json.dumps({
                "ok": False,
                "error": "reused invalid child with wrong parent_task_id"
            }))
            return False

        return True


def main():
    tests = [
        ("idempotency_execution_to_critique", test_idempotency_execution_to_critique),
        ("idempotency_without_next_task_path", test_idempotency_without_next_task_path),
        ("chain_count_limit", test_chain_count_limit),
        ("invalid_existing_child_rejected", test_invalid_existing_child_rejected),
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

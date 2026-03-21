#!/usr/bin/env python3
"""Smoke tests for guard safety behavior.

These tests verify the core guard behaviors work correctly:
- PYTEST_FAILED blocking
- DANGEROUS_CHANGE blocking
- DIFF_TOO_LARGE blocking
- CRITICAL_FILE_PYTEST_REQUIRED blocking
- Safe case passing
"""
import pytest
from pathlib import Path

from execution.guard import run_all_guards, enforce_guard


@pytest.mark.safety
class TestPytestFailed:
    """Test PYTEST_FAILED blocking behavior."""

    def test_pytest_failed_blocks_success(self):
        """When pytest fails, guard should block."""
        result = {"ok": True}
        pytest_info = {
            "required": True,
            "ran": True,
            "passed": False,
            "exit_code": 1,
            "summary": "FAILED test_x.py::test_y - AssertionError",
        }
        
        all_passed, failures, details = run_all_guards(
            result=result,
            pytest_info=pytest_info,
        )
        
        assert all_passed is False
        assert any("PYTEST_FAILED" in f for f in failures)
        assert any(d["code"] == "PYTEST_FAILED" for d in details)

    def test_pytest_not_run_but_required_blocks(self):
        """When pytest required but not run, guard should block."""
        result = {"ok": True}
        pytest_info = {
            "required": True,
            "ran": False,
            "passed": None,
        }
        
        all_passed, failures, details = run_all_guards(
            result=result,
            pytest_info=pytest_info,
        )
        
        assert all_passed is False
        assert any("PYTEST" in f for f in failures)


@pytest.mark.safety
class TestDangerousChange:
    """Test DANGEROUS_CHANGE blocking behavior."""

    def test_function_deletion_blocks(self):
        """Function deletion in diff should block."""
        result = {"ok": True}
        diff_output = """
diff --git a/example.py b/example.py
-def my_function():
-    pass
"""
        
        all_passed, failures, details = run_all_guards(
            result=result,
            diff_output=diff_output,
        )
        
        assert all_passed is False
        assert any("DANGEROUS_CHANGE" in f for f in failures)
        assert any(d["code"] == "DANGEROUS_CHANGE" for d in details)

    def test_class_deletion_blocks(self):
        """Class deletion in diff should block."""
        result = {"ok": True}
        diff_output = """
diff --git a/example.py b/example.py
-class MyClass:
-    pass
"""
        
        all_passed, failures, details = run_all_guards(
            result=result,
            diff_output=diff_output,
        )
        
        assert all_passed is False
        assert any("DANGEROUS_CHANGE" in f for f in failures)

    def test_import_removal_blocks(self):
        """Import removal in diff should block."""
        result = {"ok": True}
        diff_output = """
diff --git a/example.py b/example.py
-import os
"""
        
        all_passed, failures, details = run_all_guards(
            result=result,
            diff_output=diff_output,
        )
        
        assert all_passed is False
        assert any("DANGEROUS_CHANGE" in f for f in failures)

    def test_non_semantic_change_allowed(self):
        """Non-semantic changes (comments, whitespace) should not trigger dangerous change."""
        result = {"ok": True}
        diff_output = """
diff --git a/example.py b/example.py
-# old comment
+# new comment
"""
        
        all_passed, failures, details = run_all_guards(
            result=result,
            diff_output=diff_output,
        )
        
        # Should not block on dangerous change (may still block on other checks)
        assert not any("DANGEROUS_CHANGE" in f for f in failures)


@pytest.mark.safety
class TestDiffTooLarge:
    """Test DIFF_TOO_LARGE blocking behavior."""

    def test_small_change_oversized_diff_blocks(self):
        """Oversized diff in small-change mode should block."""
        result = {"ok": True}
        # Use additions only to avoid triggering DANGEROUS_CHANGE
        # Generate a diff with more than 50 lines (small change limit)
        diff_lines = ["+x = " + str(i) for i in range(60)]
        diff_output = "\n".join(diff_lines)
        
        all_passed, failures, details = run_all_guards(
            result=result,
            diff_output=diff_output,
            is_small_change=True,
        )
        
        assert all_passed is False
        assert any("DIFF_TOO_LARGE" in f for f in failures)
        assert any(d["code"] == "DIFF_TOO_LARGE" for d in details)


@pytest.mark.safety
class TestCriticalFilePolicy:
    """Test critical file policy behavior."""

    def test_critical_file_pytest_required_blocks(self):
        """Critical file change without pytest should block."""
        result = {
            "ok": True,
            "artifacts": ["execution/guard.py"],
        }
        pytest_info = {
            "required": True,
            "ran": False,  # pytest not run
            "passed": None,
        }
        
        all_passed, failures, details = run_all_guards(
            result=result,
            pytest_info=pytest_info,
        )
        
        assert all_passed is False
        # Guard blocks with PYTEST_REQUIRED_BUT_NOT_EXECUTED and CRITICAL_FILE_MODIFIED
        assert any("PYTEST_REQUIRED_BUT_NOT_EXECUTED" in str(d.get("code", "")) for d in details)
        assert any("CRITICAL_FILE_MODIFIED" in str(d.get("code", "")) for d in details)

    def test_critical_file_dangerous_change_blocks(self):
        """Dangerous change to critical file should block."""
        result = {
            "ok": True,
            "artifacts": ["execution/guard.py"],
        }
        diff_output = """
diff --git a/execution/guard.py b/execution/guard.py
-def run_all_guards():
-    pass
"""
        
        all_passed, failures, details = run_all_guards(
            result=result,
            diff_output=diff_output,
        )
        
        assert all_passed is False
        # Guard blocks with CRITICAL_FILE_MODIFIED and DANGEROUS_CHANGE
        assert any("CRITICAL_FILE_MODIFIED" in str(d.get("code", "")) for d in details)
        assert any("DANGEROUS_CHANGE" in str(d.get("code", "")) for d in details)


@pytest.mark.safety
class TestSafeCase:
    """Test that safe changes pass the guard."""

    def test_safe_small_change_passes(self):
        """Safe small change with pytest passing should pass guard."""
        result = {"ok": True}
        diff_output = """
diff --git a/example.py b/example.py
+def new_function():
+    return 1
"""
        pytest_info = {
            "required": True,
            "ran": True,
            "passed": True,
            "exit_code": 0,
        }
        
        all_passed, failures, details = run_all_guards(
            result=result,
            diff_output=diff_output,
            pytest_info=pytest_info,
            is_small_change=True,
        )
        
        assert all_passed is True
        assert failures == []
        assert details == []

    def test_no_changes_passes(self):
        """No changes should pass guard."""
        result = {"ok": True}
        
        all_passed, failures, details = run_all_guards(
            result=result,
            diff_output="",
        )
        
        assert all_passed is True
        assert failures == []


@pytest.mark.safety
class TestEnforceGuard:
    """Test enforce_guard entry point behavior."""

    def test_enforce_guard_modifies_result_on_failure(self):
        """enforce_guard should modify result when guard fails."""
        result = {"ok": True}
        diff_output = """
diff --git a/example.py b/example.py
-def deleted():
-    pass
"""
        
        modified = enforce_guard(
            result=result,
            diff_output=diff_output,
        )
        
        assert modified["ok"] is False
        assert modified.get("guard_failed") is True
        assert len(modified.get("guard_failures", [])) > 0

    def test_enforce_guard_preserves_success(self):
        """enforce_guard should preserve ok=True when guard passes."""
        result = {"ok": True}
        pytest_info = {
            "required": True,
            "ran": True,
            "passed": True,
        }
        
        modified = enforce_guard(
            result=result,
            pytest_info=pytest_info,
        )
        
        assert modified["ok"] is True
        assert modified.get("guard_failed") is not True

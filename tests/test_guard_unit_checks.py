#!/usr/bin/env python3
"""Unit tests for individual guard check functions.

These tests focus on:
- check_edit_failed
- check_syntax
"""
import tempfile
from pathlib import Path

import pytest

from execution.guard import check_edit_failed, check_syntax


@pytest.mark.safety
class TestCheckEditFailed:
    """Test check_edit_failed function."""

    def test_edit_failed_detected_lowercase(self):
        """Should detect 'edit failed' in lowercase."""
        passed, reason = check_edit_failed("something edit failed something")
        assert passed is False
        assert "edit failed" in reason.lower()

    def test_edit_failed_detected_uppercase(self):
        """Should detect 'EDIT FAILED' in uppercase (case-insensitive)."""
        passed, reason = check_edit_failed("ERROR: EDIT FAILED")
        assert passed is False
        assert reason is not None

    def test_edit_failed_detected_mixed_case(self):
        """Should detect 'Edit Failed' in mixed case."""
        passed, reason = check_edit_failed("Warning: Edit Failed!")
        assert passed is False
        assert reason is not None

    def test_edit_operation_failed_pattern(self):
        """Should detect 'Edit:' with 'failed' pattern."""
        passed, reason = check_edit_failed("Edit: operation failed")
        assert passed is False
        assert reason is not None

    def test_normal_text_passes(self):
        """Normal text without 'edit failed' should pass."""
        passed, reason = check_edit_failed("All operations completed successfully")
        assert passed is True
        assert reason is None

    def test_empty_string_passes(self):
        """Empty string should pass."""
        passed, reason = check_edit_failed("")
        assert passed is True
        assert reason is None

    def test_edit_without_failed_passes(self):
        """Text with 'edit' but not 'failed' should pass."""
        passed, reason = check_edit_failed("Editing the file...")
        assert passed is True
        assert reason is None

    def test_failed_without_edit_passes(self):
        """Text with 'failed' but not 'edit' should pass."""
        passed, reason = check_edit_failed("Operation failed unexpectedly")
        assert passed is True
        assert reason is None


@pytest.mark.safety
class TestCheckSyntax:
    """Test check_syntax function."""

    def test_valid_python_passes(self):
        """Valid Python file should pass."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("x = 1\nprint(x)\n")
            temp_path = Path(f.name)
        
        try:
            passed, reason = check_syntax([temp_path])
            assert passed is True
            assert reason is None
        finally:
            temp_path.unlink()

    def test_invalid_python_fails(self):
        """Invalid Python file should fail."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("def broken(\n")  # Missing closing parenthesis
            temp_path = Path(f.name)
        
        try:
            passed, reason = check_syntax([temp_path])
            assert passed is False
            assert reason is not None
            assert "syntax error" in reason.lower()
        finally:
            temp_path.unlink()

    def test_non_python_file_ignored(self):
        """Non-Python files should be ignored."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("This is not Python code")
            temp_path = Path(f.name)
        
        try:
            passed, reason = check_syntax([temp_path])
            assert passed is True
            assert reason is None
        finally:
            temp_path.unlink()

    def test_nonexistent_file_ignored(self):
        """Non-existent files should be ignored."""
        nonexistent = Path("/nonexistent/file/that/does/not/exist.py")
        passed, reason = check_syntax([nonexistent])
        assert passed is True
        assert reason is None

    def test_empty_file_passes(self):
        """Empty Python file should pass."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("")
            temp_path = Path(f.name)
        
        try:
            passed, reason = check_syntax([temp_path])
            assert passed is True
            assert reason is None
        finally:
            temp_path.unlink()

    def test_multiple_files_all_valid(self):
        """Multiple valid Python files should all pass."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f1:
            f1.write("x = 1\n")
            temp1 = Path(f1.name)
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f2:
            f2.write("y = 2\n")
            temp2 = Path(f2.name)
        
        try:
            passed, reason = check_syntax([temp1, temp2])
            assert passed is True
            assert reason is None
        finally:
            temp1.unlink()
            temp2.unlink()

    def test_multiple_files_one_invalid(self):
        """If one file is invalid, should fail."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f1:
            f1.write("x = 1\n")
            temp1 = Path(f1.name)
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f2:
            f2.write("broken syntax here (\n")
            temp2 = Path(f2.name)
        
        try:
            passed, reason = check_syntax([temp1, temp2])
            assert passed is False
            assert reason is not None
        finally:
            temp1.unlink()
            temp2.unlink()

    def test_empty_list_passes(self):
        """Empty list of files should pass."""
        passed, reason = check_syntax([])
        assert passed is True
        assert reason is None

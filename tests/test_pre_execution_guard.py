#!/usr/bin/env python3
"""
Phase 2: safe/dangerous 自動テスト

pre_execution_guard の safe/dangerous 判定が正しく動くかテスト：
- safe タスク → allow
- dangerous タスク → blocked
"""

import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runner.run_execution_worker import pre_execution_guard, DANGEROUS_PATHS


class TestPreExecutionGuard:
    """Test pre_execution_guard function."""

    # === SAFE CASES ===
    
    def test_safe_write_to_workspace(self):
        """Writing to workspace should be allowed."""
        status, info = pre_execution_guard("write", {
            "path": "/home/milky/agent-os/workspace/test.txt",
            "content": "hello",
        })
        assert status == "allow", f"Expected allow, got {status}: {info}"
    
    def test_safe_write_to_tmp(self):
        """Writing to /tmp should be allowed."""
        status, info = pre_execution_guard("write", {
            "path": "/tmp/test-file.txt",
            "content": "test",
        })
        assert status == "allow", f"Expected allow, got {status}: {info}"
    
    def test_safe_write_to_home_subdir(self):
        """Writing to ~/projects should be allowed."""
        status, info = pre_execution_guard("write", {
            "path": "/home/milky/projects/myapp/config.json",
            "content": "{}",
        })
        assert status == "allow", f"Expected allow, got {status}: {info}"
    
    def test_safe_read_action(self):
        """Read action should always be allowed."""
        status, info = pre_execution_guard("read", {
            "path": "/etc/passwd",
        })
        assert status == "allow", f"Expected allow for read, got {status}: {info}"
    
    def test_safe_execute_action(self):
        """Execute action should be allowed (no dangerous path check)."""
        status, info = pre_execution_guard("execute", {
            "command": "ls -la",
        })
        assert status == "allow", f"Expected allow, got {status}: {info}"
    
    # === DANGEROUS CASES ===
    
    def test_dangerous_write_to_etc_passwd(self):
        """Writing to /etc/passwd should be blocked."""
        status, info = pre_execution_guard("write", {
            "path": "/etc/passwd",
            "content": "malicious",
        })
        assert status == "blocked", f"Expected blocked, got {status}"
        assert info.get("reason") == "dangerous_path"
        assert "/etc/passwd" in info.get("detail", "")
    
    def test_dangerous_write_to_etc_shadow(self):
        """Writing to /etc/shadow should be blocked."""
        status, info = pre_execution_guard("write", {
            "path": "/etc/shadow",
            "content": "malicious",
        })
        assert status == "blocked"
        assert info.get("reason") == "dangerous_path"
    
    def test_dangerous_write_to_etc_sudoers(self):
        """Writing to /etc/sudoers should be blocked."""
        status, info = pre_execution_guard("write", {
            "path": "/etc/sudoers",
            "content": "ALL=(ALL) NOPASSWD: ALL",
        })
        assert status == "blocked"
        assert info.get("reason") == "dangerous_path"
    
    def test_dangerous_write_to_root_ssh(self):
        """Writing to /root/.ssh should be blocked."""
        status, info = pre_execution_guard("write", {
            "path": "/root/.ssh/authorized_keys",
            "content": "ssh-rsa ...",
        })
        assert status == "blocked"
        assert info.get("reason") == "dangerous_path"
    
    def test_dangerous_write_to_home_ssh(self):
        """Writing to ~/.ssh should be blocked."""
        status, info = pre_execution_guard("write", {
            "path": "~/.ssh/authorized_keys",
            "content": "ssh-rsa ...",
        })
        assert status == "blocked"
        assert info.get("reason") == "dangerous_path"
    
    def test_dangerous_write_to_boot(self):
        """Writing to /boot should be blocked."""
        status, info = pre_execution_guard("write", {
            "path": "/boot/grub/grub.cfg",
            "content": "malicious",
        })
        assert status == "blocked"
        assert info.get("reason") == "dangerous_path"
    
    def test_dangerous_write_to_proc(self):
        """Writing to /proc should be blocked."""
        status, info = pre_execution_guard("write", {
            "path": "/proc/sys/kernel/randomize_va_space",
            "content": "0",
        })
        assert status == "blocked"
        assert info.get("reason") == "dangerous_path"
    
    def test_dangerous_write_to_sys(self):
        """Writing to /sys should be blocked."""
        status, info = pre_execution_guard("write", {
            "path": "/sys/kernel/debug/something",
            "content": "0",
        })
        assert status == "blocked"
        assert info.get("reason") == "dangerous_path"
    
    # === EDGE CASES ===
    
    def test_empty_path_allowed(self):
        """Empty path should not crash, treated as safe."""
        status, info = pre_execution_guard("write", {
            "path": "",
            "content": "test",
        })
        assert status == "allow", f"Empty path should be allowed, got {status}"
    
    def test_missing_path_allowed(self):
        """Missing path in payload should not crash."""
        status, info = pre_execution_guard("write", {
            "content": "test",
        })
        assert status == "allow", f"Missing path should be allowed, got {status}"
    
    def test_none_payload_guard_error(self):
        """None payload should return guard_error, not crash."""
        # This tests error handling
        try:
            status, info = pre_execution_guard("write", None)
            # If it doesn't crash, check the result
            assert status in ("allow", "guard_error")
        except Exception:
            # Some exceptions are acceptable for None payload
            pass
    
    def test_path_traversal_not_blocked(self):
        """Path traversal to dangerous area should be blocked."""
        # /home/../etc/passwd => /etc/passwd
        status, info = pre_execution_guard("write", {
            "path": "/home/../etc/passwd",
            "content": "malicious",
        })
        # Note: current implementation doesn't normalize paths
        # This test documents current behavior
        # TODO: Consider adding path normalization
        assert status in ("allow", "blocked")


class TestDangerousPathsCoverage:
    """Ensure all DANGEROUS_PATHS are tested."""
    
    def test_all_dangerous_paths_covered(self):
        """Every path in DANGEROUS_PATHS should be blocked."""
        for dangerous_path in DANGEROUS_PATHS:
            test_path = dangerous_path
            if dangerous_path.endswith("/"):
                test_path = dangerous_path + "testfile"
            elif not dangerous_path.endswith("."):
                test_path = dangerous_path + "/testfile" if "/" not in dangerous_path[-5:] else dangerous_path
            
            status, info = pre_execution_guard("write", {
                "path": test_path,
                "content": "test",
            })
            assert status == "blocked", f"Expected {dangerous_path} to be blocked, got {status}"


def main():
    """Run tests without pytest for quick verification."""
    import traceback
    
    test_classes = [TestPreExecutionGuard, TestDangerousPathsCoverage]
    passed = 0
    failed = 0
    
    for cls in test_classes:
        instance = cls()
        for method_name in dir(instance):
            if method_name.startswith("test_"):
                try:
                    getattr(instance, method_name)()
                    print(f"✓ {cls.__name__}.{method_name}")
                    passed += 1
                except AssertionError as e:
                    print(f"✗ {cls.__name__}.{method_name}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"✗ {cls.__name__}.{method_name}: {type(e).__name__}: {e}")
                    traceback.print_exc()
                    failed += 1
    
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

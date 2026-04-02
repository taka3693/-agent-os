"""
Fix Verifier for Agent OS Learning

Verifies applied fixes by running tests, checking syntax,
and generating verification reports.
"""

import subprocess
import logging
import ast
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# Configure logging
LOG_DIR = Path.home() / "agent-os" / "learning" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / f"fix_verifier_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class FixVerifierError(Exception):
    """Base exception for fix verifier errors"""
    pass


class TestError(FixVerifierError):
    """Test execution failed"""
    pass


class SyntaxErrorError(FixVerifierError):
    """Syntax check failed"""
    pass


def run_command(
    cmd: List[str],
    cwd: Optional[Path] = None,
    timeout: int = 300
) -> Tuple[int, str, str]:
    """
    Run a shell command and return exit code, stdout, stderr.

    Args:
        cmd: Command and arguments
        cwd: Working directory
        timeout: Timeout in seconds

    Returns:
        Tuple of (exit_code, stdout, stderr)

    Raises:
        subprocess.TimeoutExpired: If command times out
    """
    if cwd is None:
        cwd = Path.home() / "agent-os"

    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout
    )

    return result.returncode, result.stdout, result.stderr


def check_syntax(file_path: Path) -> Dict[str, Any]:
    """
    Check Python syntax for a file.

    Args:
        file_path: Path to Python file

    Returns:
        Dict with keys:
        - ok: True if syntax is valid
        - file: File path
        - error: Error message (if failed)
        - line: Line number of error (if failed)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        ast.parse(content)
        logger.info(f"Syntax check passed: {file_path}")
        return {
            "ok": True,
            "file": str(file_path),
            "error": None,
            "line": None
        }

    except SyntaxError as e:
        error_msg = f"{e.msg} at line {e.lineno}"
        logger.error(f"Syntax error in {file_path}: {error_msg}")
        return {
            "ok": False,
            "file": str(file_path),
            "error": e.msg,
            "line": e.lineno
        }

    except Exception as e:
        logger.error(f"Unexpected error checking {file_path}: {e}")
        return {
            "ok": False,
            "file": str(file_path),
            "error": str(e),
            "line": None
        }


def check_all_syntax(files: List[str]) -> Dict[str, Any]:
    """
    Check syntax for multiple Python files.

    Args:
        files: List of file paths

    Returns:
        Dict with keys:
        - ok: True if all files passed
        - total: Total files checked
        - passed: Number of files passed
        - failed: Number of files failed
        - results: List of individual results
    """
    if not files:
        logger.warning("No files to check syntax")
        return {
            "ok": True,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "results": []
        }

    results = []
    passed = 0
    failed = 0

    for file_path in files:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"File not found: {file_path}")
            results.append({
                "ok": False,
                "file": file_path,
                "error": "File not found",
                "line": None
            })
            failed += 1
            continue

        result = check_syntax(path)
        results.append(result)

        if result["ok"]:
            passed += 1
        else:
            failed += 1

    return {
        "ok": failed == 0,
        "total": len(files),
        "passed": passed,
        "failed": failed,
        "results": results
    }


def run_tests(
    test_path: Optional[str] = None,
    verbose: bool = False,
    timeout: int = 300
) -> Dict[str, Any]:
    """
    Run pytest tests.

    Args:
        test_path: Specific test path (default: tests/)
        verbose: Enable verbose output
        timeout: Timeout in seconds

    Returns:
        Dict with keys:
        - ok: True if all tests passed
        - exit_code: pytest exit code
        - total: Total tests run
        - passed: Number of tests passed
        - failed: Number of tests failed
        - skipped: Number of tests skipped
        - stdout: pytest stdout
        - stderr: pytest stderr
        - error: Error message (if failed to run)
    """
    result = {
        "ok": False,
        "exit_code": None,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "stdout": "",
        "stderr": "",
        "error": None
    }

    cwd = Path.home() / "agent-os"

    # Check if pytest is available
    try:
        run_command(["python3", "-m", "pytest", "--version"], cwd=cwd, timeout=10)
    except Exception as e:
        error_msg = f"pytest not available: {e}"
        logger.error(error_msg)
        result["error"] = error_msg
        return result

    # Determine test path
    if test_path is None:
        test_dir = cwd / "tests"
        if test_dir.exists():
            test_path = "tests/"
        else:
            # Look for test files in the project
            test_files = list(cwd.glob("**/test_*.py"))
            if test_files:
                test_path = str(test_files[0].relative_to(cwd))
            else:
                error_msg = "No tests found"
                logger.warning(error_msg)
                result["error"] = error_msg
                # No tests is not a failure
                result["ok"] = True
                return result

    # Build pytest command
    cmd = ["python3", "-m", "pytest", test_path, "-v" if verbose else "-q", "--tb=short"]

    try:
        logger.info(f"Running pytest: {' '.join(cmd)}")
        exit_code, stdout, stderr = run_command(cmd, cwd=cwd, timeout=timeout)

        result["exit_code"] = exit_code
        result["stdout"] = stdout
        result["stderr"] = stderr

        # Parse pytest output
        lines = stdout.split("\n")

        for line in lines:
            # Look for summary line
            if "passed" in line and "failed" in line:
                # Parse: "5 passed, 1 failed in 1.23s"
                parts = line.split()
                for part in parts:
                    if part.endswith("passed"):
                        try:
                            result["passed"] = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif part.endswith("failed"):
                        try:
                            result["failed"] = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif part.endswith("skipped"):
                        try:
                            result["skipped"] = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass

        result["total"] = result["passed"] + result["failed"] + result["skipped"]
        result["ok"] = exit_code == 0 and result["failed"] == 0

        if result["ok"]:
            logger.info(f"All tests passed: {result['total']} tests")
        else:
            logger.warning(f"Tests failed: {result['failed']}/{result['total']} failed")

    except subprocess.TimeoutExpired:
        error_msg = f"Test execution timed out after {timeout}s"
        logger.error(error_msg)
        result["error"] = error_msg
    except Exception as e:
        error_msg = f"Failed to run tests: {e}"
        logger.error(error_msg)
        result["error"] = error_msg

    return result


def generate_report(
    fix_id: str,
    syntax_results: Dict[str, Any],
    test_results: Dict[str, Any],
    additional_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate a verification report.

    Args:
        fix_id: Fix identifier
        syntax_results: Results from check_all_syntax
        test_results: Results from run_tests
        additional_info: Additional metadata to include

    Returns:
        Dict with verification report
    """
    report = {
        "fix_id": fix_id,
        "timestamp": datetime.now().isoformat(),
        "verification": {
            "syntax": {
                "ok": syntax_results.get("ok", False),
                "total": syntax_results.get("total", 0),
                "passed": syntax_results.get("passed", 0),
                "failed": syntax_results.get("failed", 0),
                "errors": [
                    {
                        "file": r["file"],
                        "error": r["error"],
                        "line": r["line"]
                    }
                    for r in syntax_results.get("results", [])
                    if not r["ok"]
                ]
            },
            "tests": {
                "ok": test_results.get("ok", False),
                "total": test_results.get("total", 0),
                "passed": test_results.get("passed", 0),
                "failed": test_results.get("failed", 0),
                "skipped": test_results.get("skipped", 0),
                "exit_code": test_results.get("exit_code"),
                "error": test_results.get("error")
            }
        },
        "overall": {
            "ok": syntax_results.get("ok", False) and test_results.get("ok", False),
            "status": "passed" if (syntax_results.get("ok", False) and test_results.get("ok", False)) else "failed"
        }
    }

    # Add additional info if provided
    if additional_info:
        report["additional"] = additional_info

    return report


def save_report(report: Dict[str, Any]) -> Path:
    """
    Save verification report to JSON file.

    Args:
        report: Verification report dict

    Returns:
        Path to saved report file
    """
    report_dir = Path.home() / "agent-os" / "learning" / "verification_reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    fix_id = report.get("fix_id", "unknown")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"verify_{fix_id}_{timestamp}.json"

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Saved verification report to {report_file}")
    return report_file


def verify_fix(
    fix_id: str,
    files: List[str],
    test_path: Optional[str] = None,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Main function to verify a fix.

    Args:
        fix_id: Fix identifier
        files: List of changed files to verify
        test_path: Specific test path (optional)
        verbose: Enable verbose output

    Returns:
        Dict with keys:
        - ok: True if verification passed
        - fix_id: Fix identifier
        - report: Full verification report
        - report_file: Path to saved report
    """
    logger.info(f"Verifying fix {fix_id}...")

    # Run syntax checks
    logger.info("Running syntax checks...")
    syntax_results = check_all_syntax(files)

    # Run tests
    logger.info("Running tests...")
    test_results = run_tests(test_path=test_path, verbose=verbose)

    # Generate report
    report = generate_report(fix_id, syntax_results, test_results)

    # Save report
    report_file = save_report(report)

    result = {
        "ok": report["overall"]["ok"],
        "fix_id": fix_id,
        "report": report,
        "report_file": str(report_file)
    }

    if result["ok"]:
        logger.info(f"Fix {fix_id} verification passed")
    else:
        logger.warning(f"Fix {fix_id} verification failed")

    return result


# Example usage
if __name__ == "__main__":
    # Test verification
    print("Testing fix verifier...")

    # Syntax check test
    syntax_test = check_all_syntax(["learning/fix_applier.py"])
    print(f"Syntax check: {syntax_test}")

    # Test run (may fail if no tests exist)
    test_test = run_tests()
    print(f"Test run: {test_test}")

    # Generate and save report
    report = generate_report("test-001", syntax_test, test_test)
    report_file = save_report(report)
    print(f"Report saved to: {report_file}")

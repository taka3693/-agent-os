"""
Fix Applier for Agent OS Learning

Applies code change proposals to the actual codebase with proper
Git branching, error handling, and logging.
"""

import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import hashlib
import json

# Configure logging
LOG_DIR = Path.home() / "agent-os" / "learning" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / f"fix_applier_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class FixApplierError(Exception):
    """Base exception for fix applier errors"""
    pass


class GitError(FixApplierError):
    """Git operation failed"""
    pass


class FileError(FixApplierError):
    """File operation failed"""
    pass


def generate_short_id(description: str) -> str:
    """Generate a short unique ID from description"""
    hash_obj = hashlib.md5(description.encode())
    return hash_obj.hexdigest()[:8]


def run_git_command(args: List[str], cwd: Optional[Path] = None) -> str:
    """
    Run a git command and return stdout.

    Args:
        args: Git command arguments (e.g., ['status', '--short'])
        cwd: Working directory (defaults to agent-os root)

    Returns:
        stdout from git command

    Raises:
        GitError: If command fails
    """
    if cwd is None:
        cwd = Path.home() / "agent-os"

    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise GitError(f"Git command failed: {' '.join(['git'] + args)}\n"
                      f"stderr: {e.stderr}") from e


def ensure_git_repo() -> bool:
    """
    Ensure we're in a git repository.

    Returns:
        True if in git repo, False otherwise
    """
    try:
        run_git_command(["rev-parse", "--is-inside-work-tree"])
        return True
    except GitError:
        return False


def get_current_branch() -> str:
    """
    Get the current git branch name.

    Returns:
        Current branch name

    Raises:
        GitError: If unable to determine current branch
    """
    return run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])


def create_fix_branch(fix_id: str) -> str:
    """
    Create a new git branch for the fix.

    Args:
        fix_id: Fix identifier (e.g., "fix-001")

    Returns:
        Created branch name (e.g., "fix/fix-001")

    Raises:
        GitError: If branch creation fails
    """
    if not ensure_git_repo():
        raise GitError("Not in a git repository")

    current_branch = get_current_branch()
    if current_branch != "main":
        logger.warning(f"Current branch is '{current_branch}', switching to 'main'")
        run_git_command(["checkout", "main"])
        run_git_command(["pull", "origin", "main"])

    branch_name = f"fix/{fix_id}"

    try:
        # Create and checkout new branch
        run_git_command(["checkout", "-b", branch_name])
        logger.info(f"Created and switched to branch: {branch_name}")
        return branch_name
    except GitError as e:
        # Branch might already exist, try to checkout
        try:
            run_git_command(["checkout", branch_name])
            logger.info(f"Switched to existing branch: {branch_name}")
            return branch_name
        except GitError:
            raise GitError(f"Failed to create or checkout branch '{branch_name}': {e}") from e


def apply_code_changes(changes: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Apply code changes to files.

    Args:
        changes: List of change dictionaries with keys:
                - file: File path
                - old: Old text to replace
                - new: New text to insert

    Returns:
        Dict with keys:
        - ok: True if all changes applied, False otherwise
        - applied: List of successfully applied changes
        - failed: List of failed changes with error messages
    """
    if not changes:
        logger.warning("No changes to apply")
        return {"ok": True, "applied": [], "failed": []}

    applied = []
    failed = []

    for i, change in enumerate(changes):
        try:
            file_path = Path(change.get("file", ""))
            old_text = change.get("old", "")
            new_text = change.get("new", "")

            if not file_path.exists():
                raise FileError(f"File not found: {file_path}")

            # Read file content
            content = file_path.read_text(encoding="utf-8")

            # Check if old text exists
            if old_text not in content:
                raise FileError(
                    f"Old text not found in file {file_path}\n"
                    f"Looking for: {old_text[:100]}..."
                )

            # Replace old text with new text
            new_content = content.replace(old_text, new_text)

            # Write back
            file_path.write_text(new_content, encoding="utf-8")

            applied.append({
                "index": i,
                "file": str(file_path),
                "old_preview": old_text[:50] + "..." if len(old_text) > 50 else old_text,
                "new_preview": new_text[:50] + "..." if len(new_text) > 50 else new_text
            })

            logger.info(f"Applied change {i} to {file_path}")

        except Exception as e:
            error_msg = f"Failed to apply change {i}: {str(e)}"
            logger.error(error_msg)
            failed.append({
                "index": i,
                "file": change.get("file", "unknown"),
                "error": str(e)
            })

    result = {
        "ok": len(failed) == 0,
        "applied": applied,
        "failed": failed
    }

    if result["ok"]:
        logger.info(f"All {len(applied)} changes applied successfully")
    else:
        logger.warning(f"Applied {len(applied)} changes, {len(failed)} failed")

    return result


def commit_fix(branch: str, description: str) -> Dict[str, Any]:
    """
    Commit the applied changes.

    Args:
        branch: Branch name
        description: Commit message / fix description

    Returns:
        Dict with keys:
        - ok: True if committed successfully
        - commit_hash: Commit hash (if successful)
        - error: Error message (if failed)
    """
    try:
        # Check if there are changes to commit
        status = run_git_command(["status", "--short"])
        if not status:
            logger.warning("No changes to commit")
            return {
                "ok": False,
                "commit_hash": None,
                "error": "No changes to commit"
            }

        # Stage all changes
        run_git_command(["add", "-A"])

        # Create commit message
        commit_msg = f"Fix: {description}\n\nApplied via fix_applier.py"
        run_git_command(["commit", "-m", commit_msg])

        # Get commit hash
        commit_hash = run_git_command(["rev-parse", "HEAD"])

        logger.info(f"Committed changes to {branch}: {commit_hash}")
        return {
            "ok": True,
            "commit_hash": commit_hash,
            "error": None
        }

    except GitError as e:
        logger.error(f"Failed to commit: {e}")
        return {
            "ok": False,
            "commit_hash": None,
            "error": str(e)
        }


def rollback_fix(branch: str) -> bool:
    """
    Rollback a fix by deleting the branch and switching back to main.

    Args:
        branch: Branch name to rollback (e.g., "fix/fix-001")

    Returns:
        True if rollback successful, False otherwise
    """
    try:
        # Switch back to main
        current_branch = get_current_branch()
        if current_branch == branch:
            run_git_command(["checkout", "main"])
            logger.info(f"Switched from {branch} to main")

        # Delete the branch
        try:
            run_git_command(["branch", "-D", branch])
            logger.info(f"Deleted branch: {branch}")
        except GitError as e:
            # Branch might not exist, that's okay
            if "not found" in str(e).lower():
                logger.warning(f"Branch {branch} not found, nothing to delete")
            else:
                raise

        return True

    except Exception as e:
        logger.error(f"Failed to rollback {branch}: {e}")
        return False


def save_fix_log(fix_proposal: Dict[str, Any], result: Dict[str, Any]) -> None:
    """
    Save fix application log to JSON file.

    Args:
        fix_proposal: Original fix proposal
        result: Result from apply_fix
    """
    log_dir = Path.home() / "agent-os" / "learning" / "fix_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "fix_id": fix_proposal.get("id"),
        "description": fix_proposal.get("description"),
        "branch": result.get("branch"),
        "ok": result.get("ok"),
        "changes_applied": len(result.get("changes", {}).get("applied", [])),
        "changes_failed": len(result.get("changes", {}).get("failed", [])),
        "commit_hash": result.get("commit_hash")
    }

    log_file = log_dir / f"fix_{fix_proposal.get('id', 'unknown')}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_entry, f, indent=2)

    logger.info(f"Saved fix log to {log_file}")


def apply_fix(fix_proposal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main function to apply a fix proposal.

    Args:
        fix_proposal: Dict with keys:
            - id: Fix identifier (e.g., "fix-001")
            - description: Human-readable description
            - code_changes: List of {file, old, new} dicts

    Returns:
        Dict with keys:
        - ok: True if fix applied successfully
        - branch: Branch name created/used
        - changes: Result from apply_code_changes
        - commit_hash: Commit hash (if committed)
        - error: Error message (if failed)
    """
    fix_id = fix_proposal.get("id", "")
    description = fix_proposal.get("description", "")
    code_changes = fix_proposal.get("code_changes", [])

    logger.info(f"Applying fix {fix_id}: {description}")

    result = {
        "ok": False,
        "branch": None,
        "changes": None,
        "commit_hash": None,
        "error": None
    }

    try:
        # Validate fix proposal
        if not fix_id:
            raise FixApplierError("Fix ID is required")

        if not code_changes:
            raise FixApplierError("No code changes provided")

        # Create fix branch
        branch = create_fix_branch(fix_id)
        result["branch"] = branch

        # Apply code changes
        changes_result = apply_code_changes(code_changes)
        result["changes"] = changes_result

        if not changes_result["ok"]:
            error_msg = f"Failed to apply {len(changes_result['failed'])} changes"
            logger.error(error_msg)
            result["error"] = error_msg
            return result

        # Commit changes
        commit_result = commit_fix(branch, description)
        result["commit_hash"] = commit_result["commit_hash"]

        if not commit_result["ok"]:
            error_msg = f"Failed to commit: {commit_result['error']}"
            logger.error(error_msg)
            result["error"] = error_msg
            return result

        result["ok"] = True
        logger.info(f"Fix {fix_id} applied successfully on branch {branch}")

    except Exception as e:
        logger.error(f"Failed to apply fix {fix_id}: {e}")
        result["error"] = str(e)

    finally:
        # Save log
        save_fix_log(fix_proposal, result)

    return result


# Example usage
if __name__ == "__main__":
    # Test fix proposal
    test_fix = {
        "id": "fix-test-001",
        "description": "Test fix: increment version number",
        "code_changes": [
            {
                "file": "README.md",
                "old": "version: 0.1.0",
                "new": "version: 0.1.1"
            }
        ]
    }

    print("Applying test fix...")
    result = apply_fix(test_fix)
    print(json.dumps(result, indent=2))

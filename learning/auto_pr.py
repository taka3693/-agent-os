"""
Auto PR Creator for Agent OS Learning

Automatically creates GitHub Pull Requests for fixes.
Handles branch pushing, PR creation, and Telegram notifications via MISO.
"""

import subprocess
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Configure logging
LOG_DIR = Path.home() / "agent-os" / "learning" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / f"auto_pr_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AutoPRError(Exception):
    """Base exception for auto PR errors"""
    pass


class GhNotInstalledError(AutoPRError):
    """GitHub CLI is not installed"""
    pass


class GhAuthError(AutoPRError):
    """GitHub CLI authentication failed"""
    pass


def run_git_command(args: list, cwd: Optional[Path] = None) -> str:
    """
    Run a git command and return stdout.

    Args:
        args: Git command arguments
        cwd: Working directory (defaults to agent-os root)

    Returns:
        stdout from git command

    Raises:
        AutoPRError: If command fails
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
        raise AutoPRError(f"Git command failed: {' '.join(['git'] + args)}\n"
                         f"stderr: {e.stderr}") from e


def run_gh_command(args: list, cwd: Optional[Path] = None) -> str:
    """
    Run a gh (GitHub CLI) command and return stdout.

    Args:
        args: gh command arguments
        cwd: Working directory (defaults to agent-os root)

    Returns:
        stdout from gh command

    Raises:
        GhNotInstalledError: If gh is not installed
        GhAuthError: If gh is not authenticated
        AutoPRError: If command fails for other reasons
    """
    if cwd is None:
        cwd = Path.home() / "agent-os"

    # Check if gh is installed
    try:
        subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise GhNotInstalledError("GitHub CLI (gh) is not installed. "
                                  "Install from https://cli.github.com/")

    try:
        result = subprocess.run(
            ["gh"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip()

        # Check for authentication errors
        if "authentication" in stderr.lower() or "not authenticated" in stderr.lower():
            raise GhAuthError("GitHub CLI is not authenticated. "
                            "Run 'gh auth login' first.")

        raise AutoPRError(f"gh command failed: {' '.join(['gh'] + args)}\n"
                         f"stderr: {stderr}") from e


def check_gh_installed() -> bool:
    """
    Check if GitHub CLI is installed.

    Returns:
        True if installed, False otherwise
    """
    try:
        subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_repo_info() -> Dict[str, str]:
    """
    Get GitHub repository info (owner and name).

    Returns:
        Dict with 'owner' and 'repo' keys

    Raises:
        AutoPRError: If not in a git repo or no remote
    """
    try:
        # Get remote URL
        remote_url = run_git_command(["config", "--get", "remote.origin.url"])

        # Parse GitHub URL (supports both https and ssh)
        # https://github.com/owner/repo.git
        # git@github.com:owner/repo.git
        if "github.com" in remote_url:
            if remote_url.startswith("git@"):
                # git@github.com:owner/repo.git
                parts = remote_url.replace("git@github.com:", "").replace(".git", "").split("/")
                owner, repo = parts[0], parts[1]
            else:
                # https://github.com/owner/repo.git
                parts = remote_url.replace("https://github.com/", "").replace(".git", "").split("/")
                owner, repo = parts[0], parts[1]

            return {"owner": owner, "repo": repo}

        raise AutoPRError(f"Not a GitHub repository: {remote_url}")

    except Exception as e:
        raise AutoPRError(f"Failed to get repo info: {e}") from e


def push_branch(branch: str, upstream: Optional[str] = None) -> Dict[str, Any]:
    """
    Push a branch to GitHub.

    Args:
        branch: Branch name to push
        upstream: Upstream branch (default: origin/branch)

    Returns:
        Dict with keys:
        - ok: True if push succeeded
        - error: Error message (if failed)
    """
    logger.info(f"Pushing branch {branch} to GitHub...")

    if upstream is None:
        upstream = f"origin/{branch}"

    try:
        # Push with -u to set upstream
        run_git_command(["push", "-u", "origin", branch])
        logger.info(f"Successfully pushed branch {branch}")
        return {"ok": True, "error": None}
    except AutoPRError as e:
        error_msg = f"Failed to push branch {branch}: {e}"
        logger.error(error_msg)
        return {"ok": False, "error": str(e)}


def create_pr(
    fix_id: str,
    branch: str,
    title: str,
    description: str,
    base: Optional[str] = "main",
    labels: Optional[list] = None
) -> Dict[str, Any]:
    """
    Create a GitHub Pull Request.

    Args:
        fix_id: Fix identifier (for reference)
        branch: Source branch name
        title: PR title
        description: PR description
        base: Target branch (default: main)
        labels: List of labels to add

    Returns:
        Dict with keys:
        - ok: True if PR created successfully
        - pr_url: URL of the created PR
        - pr_number: PR number
        - error: Error message (if failed)
    """
    logger.info(f"Creating PR for fix {fix_id} from {branch}...")

    result = {
        "ok": False,
        "pr_url": None,
        "pr_number": None,
        "error": None
    }

    try:
        # Check if gh is available
        if not check_gh_installed():
            result["error"] = "GitHub CLI (gh) is not installed"
            return result

        # Build gh pr create command
        cmd = [
            "pr", "create",
            "--base", base,
            "--title", title,
            "--body", description,
            "--json", "url,number,title,state"
        ]

        # Add labels if provided
        if labels:
            for label in labels:
                cmd.extend(["--label", label])

        # Create PR
        output = run_gh_command(cmd)

        # Parse JSON output
        pr_info = json.loads(output)

        result["ok"] = True
        result["pr_url"] = pr_info.get("url")
        result["pr_number"] = pr_info.get("number")

        logger.info(f"Successfully created PR #{result['pr_number']}: {result['pr_url']}")

    except GhNotInstalledError as e:
        result["error"] = str(e)
        logger.error(f"gh not installed: {e}")
    except GhAuthError as e:
        result["error"] = str(e)
        logger.error(f"gh auth error: {e}")
    except AutoPRError as e:
        result["error"] = str(e)
        logger.error(f"Failed to create PR: {e}")
    except json.JSONDecodeError as e:
        result["error"] = f"Failed to parse gh output: {e}"
        logger.error(f"JSON parse error: {e}")

    return result


def notify_pr_created(pr_info: Dict[str, Any], chat_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Send Telegram notification about created PR.

    Args:
        pr_info: Dict with pr_url, pr_number, fix_id, title, etc.
        chat_id: Telegram chat ID (optional, reads from config if not provided)

    Returns:
        Dict with keys:
        - ok: True if notification sent
        - error: Error message (if failed)
    """
    result = {
        "ok": False,
        "error": None
    }

    try:
        # Build notification message
        pr_url = pr_info.get("pr_url", "unknown")
        pr_number = pr_info.get("pr_number", "?")
        fix_id = pr_info.get("fix_id", "unknown")
        title = pr_info.get("title", "No title")

        message = f"""🎉 PR Created!

*Fix ID:* {fix_id}
*PR:* #{pr_number}
*Title:* {title}
*URL:* {pr_url}

Review and merge when ready.
"""

        # Import message tool at runtime to avoid import issues
        try:
            from openclaw_tools import message as msg_tool

            # Send message
            msg_tool.send(
                action="send",
                channel="telegram",
                target=chat_id,
                message=message
            )

            logger.info(f"Sent Telegram notification for PR #{pr_number}")
            result["ok"] = True

        except ImportError:
            # Fallback: log to file and mention manual notification needed
            logger.warning("Message tool not available, skipping Telegram notification")
            logger.info(f"PR created: {pr_url}")

            # Try to use subprocess to call openclaw message
            try:
                subprocess.run(
                    ["openclaw", "message", "send", "--message", message],
                    capture_output=True,
                    timeout=30
                )
                result["ok"] = True
            except Exception as e2:
                logger.warning(f"Failed to send notification via subprocess: {e2}")

    except Exception as e:
        error_msg = f"Failed to send notification: {e}"
        logger.error(error_msg)
        result["error"] = str(e)

    return result


def save_pr_log(pr_info: Dict[str, Any]) -> Path:
    """
    Save PR creation log to JSON file.

    Args:
        pr_info: Dict with PR creation details

    Returns:
        Path to saved log file
    """
    log_dir = Path.home() / "agent-os" / "learning" / "pr_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "fix_id": pr_info.get("fix_id"),
        "branch": pr_info.get("branch"),
        "pr_number": pr_info.get("pr_number"),
        "pr_url": pr_info.get("pr_url"),
        "title": pr_info.get("title"),
        "ok": pr_info.get("ok"),
        "error": pr_info.get("error"),
        "notification_sent": pr_info.get("notification_sent", False)
    }

    fix_id = pr_info.get("fix_id", "unknown")
    log_file = log_dir / f"pr_{fix_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_entry, f, indent=2)

    logger.info(f"Saved PR log to {log_file}")
    return log_file


def auto_pr_workflow(
    fix_id: str,
    branch: str,
    title: str,
    description: str,
    labels: Optional[list] = None,
    notify: bool = True
) -> Dict[str, Any]:
    """
    Complete workflow: push branch, create PR, notify.

    Args:
        fix_id: Fix identifier
        branch: Branch name (without 'fix/' prefix if already included)
        title: PR title
        description: PR description
        labels: List of labels to add
        notify: Whether to send Telegram notification

    Returns:
        Dict with complete workflow results
    """
    logger.info(f"Starting auto PR workflow for fix {fix_id}...")

    result = {
        "fix_id": fix_id,
        "branch": branch,
        "title": title,
        "push_ok": False,
        "pr_ok": False,
        "pr_url": None,
        "pr_number": None,
        "notification_sent": False,
        "error": None
    }

    # Push branch
    push_result = push_branch(branch)
    result["push_ok"] = push_result["ok"]

    if not push_result["ok"]:
        result["error"] = f"Push failed: {push_result['error']}"
        return result

    # Create PR
    pr_result = create_pr(fix_id, branch, title, description, labels=labels)
    result["pr_ok"] = pr_result["ok"]
    result["pr_url"] = pr_result.get("pr_url")
    result["pr_number"] = pr_result.get("pr_number")

    if not pr_result["ok"]:
        result["error"] = pr_result["error"]
        # Still save log even if PR creation failed
        save_pr_log(result)
        return result

    # Send notification
    if notify:
        notify_result = notify_pr_created({
            "fix_id": fix_id,
            "branch": branch,
            "title": title,
            "pr_url": result["pr_url"],
            "pr_number": result["pr_number"]
        })
        result["notification_sent"] = notify_result.get("ok", False)

    # Save log
    save_pr_log(result)

    logger.info(f"Auto PR workflow completed: push_ok={result['push_ok']}, "
               f"pr_ok={result['pr_ok']}, notify={result['notification_sent']}")

    return result


# Example usage
if __name__ == "__main__":
    print("Testing auto PR creator...")

    # Check if gh is installed
    if check_gh_installed():
        print("✓ GitHub CLI is installed")
    else:
        print("✗ GitHub CLI is not installed")

    # Get repo info
    try:
        repo_info = get_repo_info()
        print(f"Repository: {repo_info['owner']}/{repo_info['repo']}")
    except Exception as e:
        print(f"Failed to get repo info: {e}")

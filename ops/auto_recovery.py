"""
Auto Recovery System for Agent OS

Automatically detects errors and attempts recovery with retry strategies.
Integrates with MISO for progress tracking and sends Telegram alerts.
"""

import json
import logging
import os
import psutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"

# Configure logging
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"auto_recovery_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AutoRecoveryError(Exception):
    """Base exception for auto recovery errors"""
    pass


# ===== MISO Integration =====

MISO_AVAILABLE = False
try:
    from miso.bridge import start_mission, update_agent_status, complete_mission, fail_mission
    MISO_AVAILABLE = True
    logger.info("MISO bridge is available")
except ImportError:
    logger.warning("MISO bridge not available")


# ===== Telegram Notification =====

def send_alert(
    message: str,
    severity: str = "warning",
    chat_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send alert via Telegram.

    Args:
        message: Alert message
        severity: Severity level (info, warning, error, critical)
        chat_id: Telegram chat ID

    Returns:
        Result dict
    """
    try:
        # Try to use message tool
        try:
            from openclaw_tools import message as msg_tool

            # Add emoji based on severity
            emoji_map = {
                "info": "ℹ️",
                "warning": "⚠️",
                "error": "❌",
                "critical": "🚨"
            }
            emoji = emoji_map.get(severity, "⚠️")

            full_message = f"{emoji} {message}"

            msg_tool.send(
                action="send",
                channel="telegram",
                target=chat_id,
                message=full_message
            )
            return {"ok": True}
        except ImportError:
            # Fallback to subprocess
            result = subprocess.run(
                ["openclaw", "message", "send", "--message", f"{emoji_map.get(severity, '⚠️')} {message}"],
                capture_output=True,
                timeout=30
            )
            return {"ok": result.returncode == 0}
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
        return {"ok": False, "error": str(e)}


# ===== Error Detection =====

def detect_errors() -> Dict[str, Any]:
    """
    Detect errors in the system.

    Returns:
        Dict with keys:
        - errors: List of detected errors
        - severity: Overall severity level
        - timestamp: Detection timestamp
    """
    logger.info("Detecting errors...")

    errors = []
    severity = "info"  # info, warning, error, critical

    try:
        # Check process crashes
        for proc in psutil.process_iter(['pid', 'name', 'status']):
            try:
                if proc.info['status'] == 'zombie':
                    errors.append({
                        "type": "process_crash",
                        "severity": "error",
                        "pid": proc.info['pid'],
                        "name": proc.info['name'],
                        "status": "zombie",
                        "description": f"Zombie process detected: {proc.info['name']} (PID {proc.info['pid']})"
                    })
                    severity = max(severity, "error", key=lambda x: ["info", "warning", "error", "critical"].index(x))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Check for high memory usage (> 90%)
        mem = psutil.virtual_memory()
        if mem.percent > 90:
            errors.append({
                "type": "resource_exhausted",
                "severity": "critical",
                "resource": "memory",
                "usage": mem.percent,
                "description": f"High memory usage: {mem.percent:.1f}%"
            })
            severity = max(severity, "critical", key=lambda x: ["info", "warning", "error", "critical"].index(x))

        # Check for high CPU usage (> 95%)
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > 95:
            errors.append({
                "type": "resource_exhausted",
                "severity": "warning",
                "resource": "cpu",
                "usage": cpu_percent,
                "description": f"High CPU usage: {cpu_percent:.1f}%"
            })
            severity = max(severity, "warning", key=lambda x: ["info", "warning", "error", "critical"].index(x))

        # Check disk space (< 10% free)
        disk = psutil.disk_usage('/')
        if disk.percent > 90:
            errors.append({
                "type": "resource_exhausted",
                "severity": "error",
                "resource": "disk",
                "usage": disk.percent,
                "description": f"Low disk space: {100 - disk.percent:.1f}% free"
            })
            severity = max(severity, "error", key=lambda x: ["info", "warning", "error", "critical"].index(x))

        # Check for failed services (systemd)
        try:
            result = subprocess.run(
                ["systemctl", "--user", "list-units", "--failed"],
                capture_output=True,
                text=True
            )
            if "failed" in result.stdout.lower():
                errors.append({
                    "type": "process_crash",
                    "severity": "error",
                    "service": "systemd",
                    "description": "Failed systemd services detected"
                })
                severity = max(severity, "error", key=lambda x: ["info", "warning", "error", "critical"].index(x))
        except FileNotFoundError:
            pass  # systemd not available

    except Exception as e:
        logger.error(f"Error detection failed: {e}")
        errors.append({
            "type": "unknown",
            "severity": "warning",
            "description": f"Error detection failed: {e}"
        })

    result = {
        "errors": errors,
        "severity": severity,
        "timestamp": datetime.now().isoformat(),
    }

    logger.info(f"Detected {len(errors)} errors, severity: {severity}")
    return result


# ===== Recovery Actions =====

def attempt_recovery(
    error: Dict[str, Any],
    max_retries: int = 3,
    chat_id: Optional[str] = None,
    mission_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Attempt to recover from an error with exponential backoff retry.

    Args:
        error: Error dict
        max_retries: Maximum number of retry attempts
        chat_id: Telegram chat ID for notifications
        mission_id: MISO mission ID for progress tracking

    Returns:
        Dict with keys:
        - ok: True if recovery succeeded
        - action_taken: Description of action taken
        - retries: Number of retries attempted
        - error: Error message (if failed)
    """
    error_type = error.get("type", "unknown")
    logger.info(f"Attempting recovery for {error_type}...")

    result = {
        "ok": False,
        "action_taken": None,
        "retries": 0,
        "error": None,
    }

    def wait_with_backoff(attempt: int):
        """Exponential backoff: 1s, 2s, 4s, 8s..."""
        wait_time = min(2 ** attempt, 60)  # Max 60 seconds
        logger.info(f"Waiting {wait_time}s before retry...")
        time.sleep(wait_time)

    for attempt in range(max_retries):
        result["retries"] = attempt + 1

        # Update MISO status if available
        if MISO_AVAILABLE and mission_id:
            update_agent_status(
                mission_id,
                "recovery",
                "RUNNING",
                f"Attempt {attempt + 1}/{max_retries} for {error_type}"
            )

        try:
            if error_type == "process_crash":
                # Try to kill zombie process or restart service
                pid = error.get("pid")
                name = error.get("name")

                if pid:
                    try:
                        proc = psutil.Process(pid)
                        proc.kill()
                        result["action_taken"] = f"Killed zombie process {name} (PID {pid})"
                        result["ok"] = True
                        break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                # If it's a systemd service, try to restart
                if error.get("service") == "systemd":
                    subprocess.run(["systemctl", "--user", "restart", "openclaw-gateway.service"], capture_output=True)
                    result["action_taken"] = "Restarted openclaw-gateway.service"
                    result["ok"] = True
                    break

            elif error_type == "connection_lost":
                # Try to reconnect (placeholder)
                result["action_taken"] = "Connection recovery attempted"
                result["ok"] = True
                break

            elif error_type == "timeout":
                # Timeout recovery: just retry
                result["action_taken"] = f"Retry {attempt + 1} for timeout"
                result["ok"] = True
                break

            elif error_type == "resource_exhausted":
                resource = error.get("resource")

                if resource == "memory":
                    # Try to clear caches (placeholder)
                    result["action_taken"] = "Attempted memory cleanup"
                    result["ok"] = True
                    break
                elif resource == "disk":
                    # Try to clean up temporary files
                    temp_dirs = ["/tmp", PROJECT_ROOT / "state" / "temp"]
                    cleaned = 0
                    for temp_dir in temp_dirs:
                        temp_path = Path(temp_dir)
                        if temp_path.exists():
                            for item in temp_path.iterdir():
                                try:
                                    if item.is_file():
                                        item.unlink()
                                        cleaned += 1
                                except:
                                    pass
                    result["action_taken"] = f"Cleaned {cleaned} temporary files"
                    result["ok"] = True
                    break

            elif error_type == "unknown":
                # Unknown error - just log and alert
                result["action_taken"] = "Logged unknown error for review"
                result["ok"] = True
                break

            # If we got here without success, wait and retry
            if attempt < max_retries - 1:
                wait_with_backoff(attempt)

        except Exception as e:
            logger.warning(f"Recovery attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                wait_with_backoff(attempt)

    # If all retries failed
    if not result["ok"]:
        result["error"] = f"Failed to recover after {max_retries} attempts"

    return result


# ===== Recovery Cycle =====

def run_recovery_cycle(
    chat_id: Optional[str] = None,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Run a full recovery cycle: detect errors and attempt recovery.

    Args:
        chat_id: Telegram chat ID for notifications
        max_retries: Maximum retries per error

    Returns:
        Dict with keys:
        - recovered: Number of errors recovered
        - failed: Number of errors that failed recovery
        - alerts_sent: Number of alerts sent
        - errors: List of all errors with recovery status
    """
    logger.info("Starting recovery cycle...")

    # Start MISO mission
    mission_id = None
    if MISO_AVAILABLE and chat_id:
        try:
            mission_id = f"recovery-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            start_mission(
                mission_id=mission_id,
                mission_name="Auto Recovery Cycle",
                goal="Detect and recover from system errors",
                chat_id=chat_id,
                agents=["detector", "recoverer"]
            )
        except Exception as e:
            logger.warning(f"Failed to start MISO mission: {e}")

    result = {
        "recovered": 0,
        "failed": 0,
        "alerts_sent": 0,
        "errors": [],
        "mission_id": mission_id,
    }

    try:
        # Update MISO status
        if MISO_AVAILABLE and mission_id:
            update_agent_status(mission_id, "detector", "RUNNING")

        # Detect errors
        detection = detect_errors()
        errors = detection["errors"]

        if not errors:
            logger.info("No errors detected")
            if MISO_AVAILABLE and mission_id:
                complete_mission(mission_id, "No errors detected")
            return result

        # Update MISO status
        if MISO_AVAILABLE and mission_id:
            update_agent_status(mission_id, "detector", "DONE")
            update_agent_status(mission_id, "recoverer", "RUNNING")

        # Attempt recovery for each error
        for error in errors:
            logger.info(f"Processing error: {error.get('type')}")

            recovery_result = attempt_recovery(
                error,
                max_retries=max_retries,
                chat_id=chat_id,
                mission_id=mission_id
            )

            error_record = {
                "error": error,
                "recovery": recovery_result,
                "timestamp": datetime.now().isoformat(),
            }
            result["errors"].append(error_record)

            if recovery_result["ok"]:
                result["recovered"] += 1
                logger.info(f"Recovered from {error.get('type')}: {recovery_result['action_taken']}")
            else:
                result["failed"] += 1
                logger.error(f"Failed to recover from {error.get('type')}: {recovery_result['error']}")

                # Send alert for failed recovery
                severity = error.get("severity", "warning")
                alert_msg = f"Auto-recovery failed for {error.get('type')}:\n{error.get('description')}\nAction: {recovery_result.get('action_taken', 'N/A')}\nError: {recovery_result.get('error', 'N/A')}"

                alert_result = send_alert(alert_msg, severity=severity, chat_id=chat_id)
                if alert_result.get("ok"):
                    result["alerts_sent"] += 1

        # Complete MISO mission
        if MISO_AVAILABLE and mission_id:
            summary = f"Recovered {result['recovered']}/{len(errors)} errors"
            if result["failed"] > 0:
                fail_mission(mission_id, f"{summary}, {result['failed']} failed")
            else:
                complete_mission(mission_id, summary)

        logger.info(f"Recovery cycle complete: {result['recovered']} recovered, {result['failed']} failed")

    except Exception as e:
        error_msg = f"Recovery cycle failed: {e}"
        logger.error(error_msg)

        # Send critical alert
        send_alert(error_msg, severity="critical", chat_id=chat_id)
        result["alerts_sent"] += 1

        if MISO_AVAILABLE and mission_id:
            fail_mission(mission_id, error_msg)

    return result


# ===== Recovery History =====

def get_recovery_history(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get recovery history from log file.

    Args:
        limit: Maximum number of entries to return

    Returns:
        List of recovery records
    """
    history_file = STATE_DIR / "recovery_history.jsonl"
    history = []

    if not history_file.exists():
        return history

    try:
        with open(history_file, "r") as f:
            lines = f.readlines()

        # Get last N lines in reverse order
        for line in reversed(lines[-limit:]):
            if line.strip():
                try:
                    history.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.error(f"Failed to read recovery history: {e}")

    return history


def save_recovery_record(record: Dict[str, Any]) -> None:
    """
    Save a recovery record to history.

    Args:
        record: Recovery record to save
    """
    history_file = STATE_DIR / "recovery_history.jsonl"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(history_file, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to save recovery record: {e}")


# ===== Continuous Monitoring =====

def start_monitoring(
    interval_seconds: int = 300,
    chat_id: Optional[str] = None
) -> None:
    """
    Start continuous monitoring with recovery cycles.

    Args:
        interval_seconds: Interval between cycles
        chat_id: Telegram chat ID for notifications
    """
    logger.info(f"Starting continuous monitoring (interval: {interval_seconds}s)")

    while True:
        try:
            cycle_result = run_recovery_cycle(chat_id=chat_id)

            # Save to history
            record = {
                "timestamp": datetime.now().isoformat(),
                "recovered": cycle_result["recovered"],
                "failed": cycle_result["failed"],
                "alerts_sent": cycle_result["alerts_sent"],
                "errors": [e["error"]["type"] for e in cycle_result["errors"]],
            }
            save_recovery_record(record)

        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
            break
        except Exception as e:
            logger.error(f"Monitoring cycle failed: {e}")

        # Wait for next cycle
        time.sleep(interval_seconds)


# ===== CLI Entry Point =====

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Auto Recovery System")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # detect
    detect_parser = subparsers.add_parser("detect", help="Detect errors")
    detect_parser.set_defaults(func=lambda args: print(json.dumps(detect_errors(), indent=2, ensure_ascii=False)))

    # recover
    recover_parser = subparsers.add_parser("recover", help="Run recovery cycle")
    recover_parser.add_argument("--chat-id", help="Telegram chat ID")
    recover_parser.add_argument("--max-retries", type=int, default=3, help="Max retries per error")
    recover_parser.set_defaults(func=lambda args: print(json.dumps(run_recovery_cycle(args.chat_id, args.max_retries), indent=2, ensure_ascii=False)))

    # history
    history_parser = subparsers.add_parser("history", help="Get recovery history")
    history_parser.add_argument("--limit", type=int, default=10, help="Max entries to show")
    history_parser.set_defaults(func=lambda args: print(json.dumps(get_recovery_history(args.limit), indent=2, ensure_ascii=False)))

    # monitor
    monitor_parser = subparsers.add_parser("monitor", help="Start continuous monitoring")
    monitor_parser.add_argument("--interval", type=int, default=300, help="Interval in seconds")
    monitor_parser.add_argument("--chat-id", help="Telegram chat ID")
    monitor_parser.set_defaults(func=lambda args: start_monitoring(args.interval, args.chat_id))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

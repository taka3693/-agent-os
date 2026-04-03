"""
Continuous Runner for Agent OS

Provides 24/7 continuous operation with scheduled tasks,
auto-recovery integration, and daily reporting.
Supports graceful shutdown with SIGTERM/SIGINT.
"""

import json
import logging
import os
import signal
import threading
import time
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"
LOG_DIR = PROJECT_ROOT / "logs"

# Create directories
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"continuous_runner_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ScheduledTask:
    """A scheduled task with cron-like expression"""

    def __init__(self, name: str, cron_expr: str, func: Callable, description: str = ""):
        self.name = name
        self.cron_expr = cron_expr
        self.func = func
        self.description = description
        self.last_run: Optional[datetime] = None
        self.run_count = 0
        self.error_count = 0
        self.last_error: Optional[str] = None

    def should_run(self, now: datetime) -> bool:
        """
        Check if task should run based on cron expression.

        Simple cron format: "MM HH * * *" (minute hour * * *)
        Examples:
        - "*/15 * * * *" - Every 15 minutes
        - "0 * * * *" - Every hour
        - "0 9 * * *" - Every day at 9:00
        - "0 0 * * *" - Every day at midnight
        """
        if self.last_run is None:
            return True

        # Parse cron expression (simplified: only minute and hour supported)
        parts = self.cron_expr.split()
        if len(parts) < 2:
            logger.warning(f"Invalid cron expression: {self.cron_expr}")
            return False

        minute_expr = parts[0]
        hour_expr = parts[1]

        # Check minute
        if minute_expr == "*":
            minute_match = True
        elif minute_expr.startswith("*/"):
            interval = int(minute_expr[2:])
            minute_match = (now.minute % interval == 0)
        else:
            minute_match = (now.minute == int(minute_expr))

        # Check hour
        if hour_expr == "*":
            hour_match = True
        elif hour_expr.startswith("*/"):
            interval = int(hour_expr[2:])
            hour_match = (now.hour % interval == 0)
        else:
            hour_match = (now.hour == int(hour_expr))

        # Check if already run this time slot
        time_diff = (now - self.last_run).total_seconds()
        if time_diff < 60:  # Don't run twice in same minute
            return False

        return minute_match and hour_match

    def run(self) -> bool:
        """Execute the task function"""
        try:
            logger.info(f"Running scheduled task: {self.name}")
            self.func()
            self.last_run = datetime.now()
            self.run_count += 1
            self.last_error = None
            return True
        except Exception as e:
            logger.error(f"Task {self.name} failed: {e}")
            self.error_count += 1
            self.last_error = str(e)
            return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "cron_expr": self.cron_expr,
            "description": self.description,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
        }


class ContinuousRunner:
    """Manages continuous operation with scheduled tasks"""

    def __init__(self):
        self.running = False
        self.started_at: Optional[datetime] = None
        self.tasks: Dict[str, ScheduledTask] = {}
        self.thread: Optional[threading.Thread] = None
        self.state_file = STATE_DIR / "continuous_state.json"

        # Stats
        self.total_tasks_run = 0
        self.total_errors = 0

        # Register default tasks
        self._register_default_tasks()

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _register_default_tasks(self) -> None:
        """Register default scheduled tasks"""

        # Task: Run proactive observer every 15 minutes
        def run_proactive_observer():
            try:
                from ops.proactive_runner import run_proactive_cycle
                result = run_proactive_cycle()
                logger.info(f"Proactive cycle completed: {result.get('ok', False)}")
            except Exception as e:
                logger.error(f"Proactive cycle failed: {e}")

        self.schedule_task(
            name="proactive_observer",
            cron_expr="*/15 * * * *",
            func=run_proactive_observer,
            description="Run proactive observer cycle"
        )

        # Task: Health check every hour
        def run_health_check():
            try:
                from ops.watchdog import get_watchdog
                watchdog = get_watchdog()
                status = watchdog.get_status()
                logger.info(f"Health check: {status['monitored_processes']} processes monitored")
            except Exception as e:
                logger.error(f"Health check failed: {e}")

        self.schedule_task(
            name="health_check",
            cron_expr="0 * * * *",
            func=run_health_check,
            description="Hourly health check"
        )

        # Task: Daily summary at 9:00
        def send_daily_summary():
            try:
                summary = self.generate_daily_report()
                logger.info(f"Daily summary: {summary['tasks_completed']} tasks, {summary['errors']} errors")

                # Send to Telegram if available
                try:
                    from openclaw_tools import message as msg_tool
                    msg_text = f"📊 Daily Summary ({summary['date']})\n"
                    msg_text += f"Tasks completed: {summary['tasks_completed']}\n"
                    msg_text += f"Errors: {summary['errors']}\n"
                    msg_text += f"Uptime: {summary['uptime']:.1f} hours"

                    msg_tool.send(
                        action="send",
                        channel="telegram",
                        message=msg_text
                    )
                    logger.info("Daily summary sent to Telegram")
                except ImportError:
                    pass
            except Exception as e:
                logger.error(f"Daily summary failed: {e}")

        self.schedule_task(
            name="daily_summary",
            cron_expr="0 9 * * *",
            func=send_daily_summary,
            description="Send daily summary at 9:00"
        )

        # Task: Generate daily report at midnight
        def generate_and_save_report():
            try:
                report = self.generate_daily_report()
                report_file = STATE_DIR / f"daily_report_{datetime.now().strftime('%Y%m%d')}.json"
                with open(report_file, "w") as f:
                    json.dump(report, f, indent=2, default=str)
                logger.info(f"Daily report saved to {report_file}")
            except Exception as e:
                logger.error(f"Daily report generation failed: {e}")

        self.schedule_task(
            name="daily_report",
            cron_expr="0 0 * * *",
            func=generate_and_save_report,
            description="Generate daily report at midnight"
        )

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.stop_continuous_mode()

    def _save_state(self) -> None:
        """Save current state to file"""
        state = {
            "running": self.running,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "total_tasks_run": self.total_tasks_run,
            "total_errors": self.total_errors,
            "tasks": {name: task.to_dict() for name, task in self.tasks.items()},
            "saved_at": datetime.now().isoformat(),
        }

        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2, default=str)

    def _load_state(self) -> None:
        """Load state from file"""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)

            self.total_tasks_run = state.get("total_tasks_run", 0)
            self.total_errors = state.get("total_errors", 0)

            # Restore task stats
            for name, task_data in state.get("tasks", {}).items():
                if name in self.tasks:
                    self.tasks[name].last_run = datetime.fromisoformat(task_data["last_run"]) if task_data.get("last_run") else None
                    self.tasks[name].run_count = task_data.get("run_count", 0)
                    self.tasks[name].error_count = task_data.get("error_count", 0)
                    self.tasks[name].last_error = task_data.get("last_error")

            logger.info(f"State loaded from {self.state_file}")
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")

    def schedule_task(self, name: str, cron_expr: str, func: Callable, description: str = "") -> Dict[str, Any]:
        """
        Register a scheduled task.

        Args:
            name: Task name
            cron_expr: Cron expression (simplified: "MM HH * * *")
            func: Function to execute
            description: Task description

        Returns:
            Result dict
        """
        if name in self.tasks:
            logger.warning(f"Task {name} already registered, updating...")
            del self.tasks[name]

        task = ScheduledTask(name, cron_expr, func, description)
        self.tasks[name] = task
        logger.info(f"Scheduled task: {name} ({cron_expr}) - {description}")

        self._save_state()
        return {"ok": True, "message": "Task scheduled"}

    def unschedule_task(self, name: str) -> Dict[str, Any]:
        """Remove a scheduled task"""
        if name not in self.tasks:
            return {"ok": False, "error": f"Task {name} not found"}

        del self.tasks[name]
        logger.info(f"Unscheduled task: {name}")

        self._save_state()
        return {"ok": True, "message": "Task unscheduled"}

    def start_continuous_mode(self, chat_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Start continuous operation mode.

        Args:
            chat_id: Telegram chat ID for notifications

        Returns:
            Result dict
        """
        if self.running:
            return {"ok": False, "error": "Already running"}

        logger.info("Starting continuous operation mode...")
        self.running = True
        self.started_at = datetime.now()

        # Load previous state
        self._load_state()

        # Start runner thread
        self.thread = threading.Thread(
            target=self._run_loop,
            kwargs={"chat_id": chat_id},
            daemon=True
        )
        self.thread.start()

        logger.info("Continuous operation mode started")
        self._save_state()

        return {
            "ok": True,
            "started_at": self.started_at.isoformat(),
            "tasks_scheduled": len(self.tasks)
        }

    def stop_continuous_mode(self) -> Dict[str, Any]:
        """Stop continuous operation mode"""
        if not self.running:
            return {"ok": False, "error": "Not running"}

        logger.info("Stopping continuous operation mode...")
        self.running = False

        # Wait for thread to finish
        if self.thread:
            self.thread.join(timeout=30)

        uptime = self.get_uptime()
        logger.info(f"Continuous operation stopped (uptime: {uptime['uptime_hours']:.2f} hours)")

        self._save_state()
        return {
            "ok": True,
            "stopped_at": datetime.now().isoformat(),
            "uptime": uptime
        }

    def _run_loop(self, chat_id: Optional[str] = None) -> None:
        """Main loop for continuous operation"""
        logger.info("Runner loop started")

        try:
            while self.running:
                now = datetime.now()

                # Check and run scheduled tasks
                for name, task in self.tasks.items():
                    if task.should_run(now):
                        logger.info(f"Triggering task: {name}")
                        if task.run():
                            self.total_tasks_run += 1
                        else:
                            self.total_errors += 1

                        self._save_state()

                # Run auto-recovery if available
                try:
                    from ops.auto_recovery import run_recovery_cycle
                    recovery_result = run_recovery_cycle(chat_id=chat_id, max_retries=2)
                    if recovery_result.get("errors"):
                        logger.info(f"Recovery: {recovery_result['recovered']} recovered, {recovery_result['failed']} failed")
                except ImportError:
                    pass
                except Exception as e:
                    logger.warning(f"Recovery cycle failed: {e}")

                # Save state every minute
                self._save_state()

                # Sleep until next check
                time.sleep(60)

        except Exception as e:
            logger.error(f"Runner loop failed: {e}")
            self.running = False
            self._save_state()

    def get_uptime(self) -> Dict[str, Any]:
        """
        Get current uptime information.

        Returns:
            Dict with started_at and uptime_hours
        """
        if not self.started_at:
            return {
                "started_at": None,
                "uptime_hours": 0.0,
                "uptime_seconds": 0.0
            }

        uptime_seconds = (datetime.now() - self.started_at).total_seconds()
        return {
            "started_at": self.started_at.isoformat(),
            "uptime_hours": uptime_seconds / 3600.0,
            "uptime_seconds": uptime_seconds
        }

    def generate_daily_report(self) -> Dict[str, Any]:
        """
        Generate a daily report.

        Returns:
            Dict with report data
        """
        uptime = self.get_uptime()

        report = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "generated_at": datetime.now().isoformat(),
            "uptime_hours": uptime["uptime_hours"],
            "tasks_completed": self.total_tasks_run,
            "errors": self.total_errors,
            "tasks": {
                name: {
                    "run_count": task.run_count,
                    "error_count": task.error_count,
                    "last_run": task.last_run.isoformat() if task.last_run else None,
                }
                for name, task in self.tasks.items()
            }
        }

        return report


# ===== Global instance =====

_runner: Optional[ContinuousRunner] = None


def get_runner() -> ContinuousRunner:
    """Get or create the global runner instance"""
    global _runner
    if _runner is None:
        _runner = ContinuousRunner()
    return _runner


# ===== Convenience functions =====

def start_continuous_mode(chat_id: Optional[str] = None) -> Dict[str, Any]:
    """Start continuous operation mode"""
    return get_runner().start_continuous_mode(chat_id)


def stop_continuous_mode() -> Dict[str, Any]:
    """Stop continuous operation mode"""
    return get_runner().stop_continuous_mode()


def get_uptime() -> Dict[str, Any]:
    """Get uptime information"""
    return get_runner().get_uptime()


def schedule_task(name: str, cron_expr: str, func: Callable, description: str = "") -> Dict[str, Any]:
    """Schedule a task"""
    return get_runner().schedule_task(name, cron_expr, func, description)


def generate_daily_report() -> Dict[str, Any]:
    """Generate daily report"""
    return get_runner().generate_daily_report()


# ===== CLI Entry Point =====

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Continuous Runner for Agent OS")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # start
    start_parser = subparsers.add_parser("start", help="Start continuous mode")
    start_parser.add_argument("--chat-id", help="Telegram chat ID")
    start_parser.set_defaults(
        func=lambda args: print(json.dumps(start_continuous_mode(args.chat_id), indent=2, ensure_ascii=False))
    )

    # stop
    stop_parser = subparsers.add_parser("stop", help="Stop continuous mode")
    stop_parser.set_defaults(
        func=lambda args: print(json.dumps(stop_continuous_mode(), indent=2, ensure_ascii=False))
    )

    # status
    status_parser = subparsers.add_parser("status", help="Get status")
    status_parser.set_defaults(
        func=lambda args: (
            runner := get_runner(),
            print(json.dumps({
                "running": runner.running,
                "started_at": runner.started_at.isoformat() if runner.started_at else None,
                "uptime": runner.get_uptime(),
                "tasks_scheduled": len(runner.tasks),
                "total_tasks_run": runner.total_tasks_run,
                "total_errors": runner.total_errors,
                "tasks": {name: task.to_dict() for name, task in runner.tasks.items()},
            }, indent=2, ensure_ascii=False))
        )
    )

    # uptime
    uptime_parser = subparsers.add_parser("uptime", help="Get uptime")
    uptime_parser.set_defaults(
        func=lambda args: print(json.dumps(get_uptime(), indent=2, ensure_ascii=False))
    )

    # report
    report_parser = subparsers.add_parser("report", help="Generate daily report")
    report_parser.set_defaults(
        func=lambda args: print(json.dumps(generate_daily_report(), indent=2, ensure_ascii=False))
    )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

"""
Watchdog for Agent OS

Monitors critical processes and automatically restarts them.
Integrates with systemd services and provides health checking.
"""

import json
import logging
import os
import signal
import subprocess
import threading
import time
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
LOG_DIR = PROJECT_ROOT / "logs"
STATE_DIR = PROJECT_ROOT / "state"

# Create directories
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "watchdog.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ProcessInfo:
    """Information about a monitored process"""

    def __init__(
        self,
        name: str,
        command: List[str],
        health_check: Optional[str] = None,
        max_restarts: int = 3,
        restart_delay: int = 10,
        systemd_service: Optional[str] = None
    ):
        self.name = name
        self.command = command
        self.health_check = health_check
        self.max_restarts = max_restarts
        self.restart_delay = restart_delay
        self.systemd_service = systemd_service

        self.pid: Optional[int] = None
        self.started_at: Optional[datetime] = None
        self.restarts = 0
        self.last_check: Optional[datetime] = None
        self.last_healthy: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "command": " ".join(self.command),
            "health_check": self.health_check,
            "pid": self.pid,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "uptime": (datetime.now() - self.started_at).total_seconds() if self.started_at else None,
            "restarts": self.restarts,
            "max_restarts": self.max_restarts,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "last_healthy": self.last_healthy.isoformat() if self.last_healthy else None,
            "systemd_service": self.systemd_service,
        }


class Watchdog:
    """Process watchdog with auto-restart capabilities"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or (CONFIG_DIR / "watchdog.yaml")
        self.processes: Dict[str, ProcessInfo] = {}
        self.running = False
        self.watchdog_thread: Optional[threading.Thread] = None
        self.state_file = STATE_DIR / "watchdog_state.json"

        # Load config
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML file"""
        if not self.config_path.exists():
            # Create default config
            default_config = {
                "processes": [
                    {
                        "name": "openclaw-gateway",
                        "systemd_service": "openclaw-gateway.service",
                        "max_restarts": 5,
                        "restart_delay": 10,
                    },
                ],
                "watchdog": {
                    "interval_seconds": 60,
                    "health_check_timeout": 10,
                },
            }
            with open(self.config_path, "w") as f:
                yaml.dump(default_config, f, default_flow_style=False)
            logger.info(f"Created default config at {self.config_path}")

        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f)

        # Register processes from config
        for proc_config in config.get("processes", []):
            self.register_process(
                name=proc_config["name"],
                command=proc_config.get("command", []),
                health_check=proc_config.get("health_check"),
                max_restarts=proc_config.get("max_restarts", 3),
                restart_delay=proc_config.get("restart_delay", 10),
                systemd_service=proc_config.get("systemd_service")
            )

    def _save_state(self) -> None:
        """Save current state to file"""
        state = {
            "timestamp": datetime.now().isoformat(),
            "processes": {name: proc.to_dict() for name, proc in self.processes.items()},
            "running": self.running,
        }

        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2, default=str)

    def register_process(
        self,
        name: str,
        command: List[str],
        health_check: Optional[str] = None,
        max_restarts: int = 3,
        restart_delay: int = 10,
        systemd_service: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register a process for monitoring.

        Args:
            name: Process name
            command: Command to start the process
            health_check: Health check URL or command
            max_restarts: Maximum number of restarts before giving up
            restart_delay: Delay between restarts (seconds)
            systemd_service: systemd service name (if applicable)

        Returns:
            Result dict
        """
        if name in self.processes:
            logger.warning(f"Process {name} already registered, updating...")
            self.processes[name].command = command
            self.processes[name].health_check = health_check
            return {"ok": True, "message": "Updated existing process"}

        proc = ProcessInfo(
            name=name,
            command=command,
            health_check=health_check,
            max_restarts=max_restarts,
            restart_delay=restart_delay,
            systemd_service=systemd_service
        )

        self.processes[name] = proc
        logger.info(f"Registered process: {name}")

        self._save_state()
        return {"ok": True, "message": "Process registered"}

    def unregister_process(self, name: str) -> Dict[str, Any]:
        """
        Unregister a process from monitoring.

        Args:
            name: Process name

        Returns:
            Result dict
        """
        if name not in self.processes:
            return {"ok": False, "error": f"Process {name} not found"}

        del self.processes[name]
        logger.info(f"Unregistered process: {name}")

        self._save_state()
        return {"ok": True, "message": "Process unregistered"}

    def check_process(self, name: str) -> Dict[str, Any]:
        """
        Check if a process is alive and healthy.

        Args:
            name: Process name

        Returns:
            Dict with alive status, pid, uptime, health status
        """
        if name not in self.processes:
            return {"ok": False, "error": f"Process {name} not found"}

        proc = self.processes[name]
        proc.last_check = datetime.now()

        result = {
            "ok": True,
            "name": name,
            "alive": False,
            "pid": None,
            "uptime": None,
            "healthy": False,
            "restarts": proc.restarts,
        }

        # Check if process is running
        if proc.pid:
            try:
                import psutil
                psutil_proc = psutil.Process(proc.pid)
                if psutil_proc.is_running():
                    result["alive"] = True
                    result["pid"] = proc.pid
                    if proc.started_at:
                        result["uptime"] = (datetime.now() - proc.started_at).total_seconds()
            except (psutil.NoSuchProcess, psutil.AccessDenied, ImportError):
                pass

        # If using systemd service, check service status
        if proc.systemd_service and not result["alive"]:
            try:
                systemctl_result = subprocess.run(
                    ["systemctl", "--user", "is-active", proc.systemd_service],
                    capture_output=True,
                    text=True
                )
                if "active" in systemctl_result.stdout:
                    # Get main PID from service
                    show_result = subprocess.run(
                        ["systemctl", "--user", "show", "-p", "MainPID", proc.systemd_service],
                        capture_output=True,
                        text=True
                    )
                    main_pid = show_result.stdout.split("=")[1].strip()
                    if main_pid and int(main_pid) > 0:
                        result["alive"] = True
                        result["pid"] = int(main_pid)
                        proc.pid = int(main_pid)
            except Exception as e:
                logger.warning(f"Failed to check systemd service: {e}")

        # Perform health check if configured
        if result["alive"] and proc.health_check:
            result["healthy"] = self._perform_health_check(proc.health_check)
            if result["healthy"]:
                proc.last_healthy = datetime.now()

        return result

    def _perform_health_check(self, health_check: str, timeout: int = 10) -> bool:
        """
        Perform a health check.

        Args:
            health_check: Health check URL or command
            timeout: Timeout in seconds

        Returns:
            True if healthy, False otherwise
        """
        try:
            if health_check.startswith("http://") or health_check.startswith("https://"):
                # HTTP health check
                import urllib.request
                import urllib.error

                request = urllib.request.Request(health_check, method="GET")
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return response.status == 200
            else:
                # Command health check
                result = subprocess.run(
                    health_check.split(),
                    capture_output=True,
                    timeout=timeout
                )
                return result.returncode == 0
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    def restart_process(self, name: str) -> Dict[str, Any]:
        """
        Restart a process.

        Args:
            name: Process name

        Returns:
            Result dict with new_pid if successful
        """
        if name not in self.processes:
            return {"ok": False, "error": f"Process {name} not found"}

        proc = self.processes[name]

        # Check if max restarts exceeded
        if proc.restarts >= proc.max_restarts:
            logger.error(f"Max restarts exceeded for {name}")
            return {
                "ok": False,
                "error": f"Max restarts ({proc.max_restarts}) exceeded"
            }

        # Stop existing process if running
        if proc.pid:
            try:
                import psutil
                psutil_proc = psutil.Process(proc.pid)
                psutil_proc.terminate()
                psutil_proc.wait(timeout=10)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired, ImportError):
                try:
                    os.kill(proc.pid, signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    pass

        # Restart using systemd if available
        if proc.systemd_service:
            try:
                logger.info(f"Restarting systemd service: {proc.systemd_service}")
                subprocess.run(
                    ["systemctl", "--user", "restart", proc.systemd_service],
                    check=True
                )
                proc.restarts += 1

                # Wait for service to start and get new PID
                time.sleep(2)
                check_result = subprocess.run(
                    ["systemctl", "--user", "show", "-p", "MainPID", proc.systemd_service],
                    capture_output=True,
                    text=True
                )
                main_pid = check_result.stdout.split("=")[1].strip()
                if main_pid and int(main_pid) > 0:
                    proc.pid = int(main_pid)
                    proc.started_at = datetime.now()

                logger.info(f"Restarted {name}, new PID: {proc.pid}")
                self._save_state()

                return {
                    "ok": True,
                    "new_pid": proc.pid,
                    "method": "systemd"
                }
            except Exception as e:
                logger.error(f"Failed to restart systemd service: {e}")

        # Fallback: start with command
        if proc.command:
            try:
                logger.info(f"Starting process with command: {' '.join(proc.command)}")
                proc_obj = subprocess.Popen(
                    proc.command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                proc.pid = proc_obj.pid
                proc.started_at = datetime.now()
                proc.restarts += 1

                logger.info(f"Started {name}, PID: {proc.pid}")
                self._save_state()

                return {
                    "ok": True,
                    "new_pid": proc.pid,
                    "method": "command"
                }
            except Exception as e:
                logger.error(f"Failed to start process: {e}")
                return {
                    "ok": False,
                    "error": str(e)
                }

        return {
            "ok": False,
            "error": "No restart method available"
        }

    def _check_all_processes(self) -> Dict[str, Any]:
        """
        Check all registered processes and restart if needed.

        Returns:
            Summary of checks and actions taken
        """
        results = {
            "checked": 0,
            "alive": 0,
            "restarted": 0,
            "failed": 0,
            "details": []
        }

        for name, proc in self.processes.items():
            results["checked"] += 1

            check_result = self.check_process(name)

            if check_result["alive"]:
                results["alive"] += 1

                # Check if unhealthy
                if not check_result.get("healthy", True):
                    logger.warning(f"Process {name} is unhealthy, restarting...")
                    restart_result = self.restart_process(name)
                    if restart_result["ok"]:
                        results["restarted"] += 1
                    else:
                        results["failed"] += 1
            else:
                logger.warning(f"Process {name} is not running, restarting...")
                restart_result = self.restart_process(name)
                if restart_result["ok"]:
                    results["restarted"] += 1
                else:
                    results["failed"] += 1

            results["details"].append({
                "name": name,
                "check": check_result,
            })

        return results

    def run_watchdog(self, interval_seconds: int = 60) -> None:
        """
        Start continuous watchdog monitoring.

        Args:
            interval_seconds: Interval between checks
        """
        logger.info(f"Starting watchdog with {interval_seconds}s interval")
        self.running = True
        self._save_state()

        while self.running:
            try:
                logger.info("--- Watchdog Cycle ---")
                results = self._check_all_processes()

                logger.info(
                    f"Checked: {results['checked']}, "
                    f"Alive: {results['alive']}, "
                    f"Restarted: {results['restarted']}, "
                    f"Failed: {results['failed']}"
                )

                self._save_state()

            except Exception as e:
                logger.error(f"Watchdog cycle failed: {e}")

            time.sleep(interval_seconds)

    def stop_watchdog(self) -> None:
        """Stop the watchdog"""
        logger.info("Stopping watchdog...")
        self.running = False
        self._save_state()

    def get_status(self) -> Dict[str, Any]:
        """
        Get current watchdog status.

        Returns:
            Status dict with process information
        """
        process_statuses = []

        for name, proc in self.processes.items():
            check_result = self.check_process(name)
            process_statuses.append(check_result)

        return {
            "running": self.running,
            "monitored_processes": len(self.processes),
            "processes": process_statuses,
            "state_file": str(self.state_file),
            "config_file": str(self.config_path),
        }


# ===== Global instance =====

_watchdog: Optional[Watchdog] = None
_watchdog_thread: Optional[threading.Thread] = None


def get_watchdog() -> Watchdog:
    """Get or create the global watchdog instance"""
    global _watchdog
    if _watchdog is None:
        _watchdog = Watchdog()
    return _watchdog


# ===== Convenience functions =====

def register_process(name: str, command: List[str], health_check: Optional[str] = None) -> Dict[str, Any]:
    """Register a process with the global watchdog"""
    return get_watchdog().register_process(name, command, health_check)


def unregister_process(name: str) -> Dict[str, Any]:
    """Unregister a process from the global watchdog"""
    return get_watchdog().unregister_process(name)


def check_process(name: str) -> Dict[str, Any]:
    """Check a process with the global watchdog"""
    return get_watchdog().check_process(name)


def restart_process(name: str) -> Dict[str, Any]:
    """Restart a process with the global watchdog"""
    return get_watchdog().restart_process(name)


def run_watchdog(interval_seconds: int = 60) -> None:
    """Run the global watchdog in a background thread"""
    global _watchdog_thread

    watchdog = get_watchdog()

    if _watchdog_thread and _watchdog_thread.is_alive():
        logger.warning("Watchdog already running")
        return

    _watchdog_thread = threading.Thread(
        target=watchdog.run_watchdog,
        args=(interval_seconds,),
        daemon=True
    )
    _watchdog_thread.start()
    logger.info("Watchdog thread started")


def stop_watchdog() -> None:
    """Stop the global watchdog"""
    global _watchdog
    if _watchdog:
        _watchdog.stop_watchdog()


def get_status() -> Dict[str, Any]:
    """Get the status of the global watchdog"""
    return get_watchdog().get_status()


# ===== CLI Entry Point =====

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Watchdog for Agent OS")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # register
    register_parser = subparsers.add_parser("register", help="Register a process")
    register_parser.add_argument("name", help="Process name")
    register_parser.add_argument("--command", nargs="+", help="Command to start process")
    register_parser.add_argument("--health-check", help="Health check URL or command")
    register_parser.add_argument("--systemd-service", help="systemd service name")
    register_parser.add_argument("--max-restarts", type=int, default=3, help="Max restarts")
    register_parser.add_argument("--restart-delay", type=int, default=10, help="Restart delay")
    register_parser.set_defaults(
        func=lambda args: print(json.dumps(
            register_process(
                args.name,
                args.command or [],
                args.health_check,
                max_restarts=args.max_restarts,
                restart_delay=args.restart_delay,
                systemd_service=args.systemd_service
            ),
            indent=2,
            ensure_ascii=False
        ))
    )

    # unregister
    unregister_parser = subparsers.add_parser("unregister", help="Unregister a process")
    unregister_parser.add_argument("name", help="Process name")
    unregister_parser.set_defaults(
        func=lambda args: print(json.dumps(unregister_process(args.name), indent=2, ensure_ascii=False))
    )

    # check
    check_parser = subparsers.add_parser("check", help="Check process status")
    check_parser.add_argument("name", help="Process name")
    check_parser.set_defaults(
        func=lambda args: print(json.dumps(check_process(args.name), indent=2, ensure_ascii=False))
    )

    # restart
    restart_parser = subparsers.add_parser("restart", help="Restart a process")
    restart_parser.add_argument("name", help="Process name")
    restart_parser.set_defaults(
        func=lambda args: print(json.dumps(restart_process(args.name), indent=2, ensure_ascii=False))
    )

    # status
    status_parser = subparsers.add_parser("status", help="Get watchdog status")
    status_parser.set_defaults(
        func=lambda args: print(json.dumps(get_status(), indent=2, ensure_ascii=False))
    )

    # start
    start_parser = subparsers.add_parser("start", help="Start watchdog monitoring")
    start_parser.add_argument("--interval", type=int, default=60, help="Check interval")
    start_parser.set_defaults(
        func=lambda args: (
            run_watchdog(args.interval),
            print("Watchdog started. Press Ctrl+C to stop.")
        )
    )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

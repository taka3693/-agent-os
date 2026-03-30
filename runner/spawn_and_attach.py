#!/usr/bin/env python3
"""spawn_and_attach: Production entry point with parallel worker support."""
from __future__ import annotations
import json, os, signal, sys, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runner.task_scheduler import find_executable_tasks, create_scheduled_task, _atomic_write_json, _load_task

DEFAULT_WORKERS = 4
POLL_INTERVAL = 1.0
TASKS_DIR = PROJECT_ROOT / "state" / "tasks"

def _now_iso(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def _gen_id(): return f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

class WorkerPool:
    def __init__(self, workers=DEFAULT_WORKERS, tasks_dir=None, executor_fn=None):
        self.workers = workers
        self.tasks_dir = tasks_dir or TASKS_DIR
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self._executor_fn = executor_fn or self._default_executor
        self._pool = None
        self._running = False
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def _default_executor(self, task):
        from runner.run_task_once import process_one
        return process_one(self.tasks_dir / f"{task.get('task_id','unknown')}.json")

    def start(self):
        with self._lock:
            if self._running: return self
            self._pool = ThreadPoolExecutor(max_workers=self.workers)
            self._running = True
            self._stop.clear()
        return self

    def stop(self):
        with self._lock:
            self._running = False
            self._stop.set()
            if self._pool: self._pool.shutdown(wait=True); self._pool = None

    def submit(self, query, skill="research", skill_chain=None, run_at=None):
        task_id = _gen_id()
        task = create_scheduled_task(task_id, query, skill_chain or [skill], run_at)
        _atomic_write_json(self.tasks_dir / f"{task_id}.json", task)
        return task_id

    def wait(self, task_id, timeout=None):
        path = self.tasks_dir / f"{task_id}.json"
        start = time.time()
        while True:
            if timeout and (time.time() - start) > timeout:
                raise TimeoutError(f"Task {task_id} timeout")
            task = _load_task(path)
            if task.get("status") in ("completed","failed","partial"): return task
            time.sleep(POLL_INTERVAL)

    def get_status(self, task_id): return _load_task(self.tasks_dir / f"{task_id}.json")

    def _cycle(self):
        if not self._running or not self._pool: return 0
        tasks = find_executable_tasks(self.tasks_dir, f"pool-{os.getpid()}", self.workers)
        for t in tasks: self._pool.submit(self._executor_fn, t)
        return len(tasks)

    def run_once(self):
        if not self._running: self.start()
        return {"ok": True, "tasks_started": self._cycle(), "timestamp": _now_iso()}

    def run_forever(self):
        if not self._running: self.start()
        signal.signal(signal.SIGINT, lambda *_: self.stop())
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        print(f"[spawn_and_attach] Workers={self.workers}, watching {self.tasks_dir}")
        while self._running and not self._stop.is_set():
            try:
                n = self._cycle()
                if n: print(f"[spawn_and_attach] Started {n} task(s)")
            except Exception as e: print(f"[spawn_and_attach] Error: {e}")
            self._stop.wait(POLL_INTERVAL)
        print("[spawn_and_attach] Stopped")

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--workers","-w",type=int,default=DEFAULT_WORKERS)
    p.add_argument("--once",action="store_true")
    p.add_argument("--submit",type=str)
    p.add_argument("--skill",default="research")
    p.add_argument("--wait",type=str)
    p.add_argument("--status",type=str)
    a = p.parse_args()
    pool = WorkerPool(workers=a.workers)
    if a.submit: pool.start(); print(json.dumps({"ok":True,"task_id":pool.submit(a.submit,a.skill)})); return 0
    if a.wait: print(json.dumps(pool.wait(a.wait),ensure_ascii=False,indent=2)); return 0
    if a.status: print(json.dumps(pool.get_status(a.status),ensure_ascii=False,indent=2)); return 0
    if a.once: pool.start(); print(json.dumps(pool.run_once(),indent=2)); pool.stop(); return 0
    pool.run_forever(); return 0

if __name__ == "__main__": raise SystemExit(main())

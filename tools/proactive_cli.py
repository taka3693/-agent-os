#!/usr/bin/env python3
"""Proactive Task Generation CLI

Usage:
    python tools/proactive_cli.py run [--dry-run]
    python tools/proactive_cli.py status
    python tools/proactive_cli.py observe
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from ops.proactive_observer import observe_system
from ops.proactive_runner import run_proactive_cycle, get_proactive_status


def get_paths():
    project_root = Path(__file__).parent.parent
    return {
        "state_root": project_root / "state",
        "tasks_root": project_root / "workspace" / "tasks",
    }


def cmd_run(args):
    """Proactiveサイクルを実行"""
    paths = get_paths()
    result = run_proactive_cycle(
        state_root=paths["state_root"],
        tasks_root=paths["tasks_root"],
        dry_run=args.dry_run,
    )
    
    print(f"{'[DRY RUN] ' if args.dry_run else ''}Proactive Cycle Complete")
    print(f"  Generated tasks: {result['generated_tasks']}")
    print(f"  Queued for approval: {result['queued_for_approval']}")
    
    if result["tasks"]:
        print("\nTasks:")
        for task in result["tasks"]:
            status = "→ approval queue" if task.get("requires_approval") else "(notification)"
            print(f"  [{task['priority']}] {task['type']}: {task['query'][:50]}... {status}")
    
    return 0


def cmd_status(args):
    """Proactiveサイクルの状態を表示"""
    paths = get_paths()
    status = get_proactive_status(paths["state_root"])
    
    print(f"Status: {status['status']}")
    if status.get("total_cycles"):
        print(f"Total cycles: {status['total_cycles']}")
    if status.get("last_cycle"):
        last = status["last_cycle"]
        print(f"Last run: {last['executed_at']}")
        print(f"  Tasks generated: {last['generated_tasks']}")
    
    return 0


def cmd_observe(args):
    """現在のシステム状態を観察（タスク生成なし）"""
    paths = get_paths()
    obs = observe_system(paths["state_root"], paths["tasks_root"])
    
    print("=== System Observation ===")
    print(f"Time: {obs['observed_at']}")
    print(f"\nHealth: {obs['health']['status']}")
    for issue in obs['health'].get('issues', []):
        print(f"  ⚠ {issue['type']}: {issue['detail']}")
    
    print(f"\nFailures: {obs['failures']['count']} recent")
    for p in obs['failures'].get('patterns', []):
        print(f"  - {p['error_type']}: {p['count']}x ({p['severity']})")
    
    print(f"\nLearning: {obs['learning']['episode_count']} episodes")
    for i in obs['learning'].get('insights', []):
        print(f"  💡 {i['type']}: {i['detail']}")
    
    print(f"\nIdle: {'Yes' if obs['idle']['is_idle'] else 'No'}")
    print(f"  Pending: {obs['idle']['pending_count']}, Running: {obs['idle']['running_count']}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(description="Proactive Task Generation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # run
    run_parser = subparsers.add_parser("run", help="Run proactive cycle")
    run_parser.add_argument("--dry-run", action="store_true", help="Don't queue tasks")
    run_parser.set_defaults(func=cmd_run)
    
    # status
    status_parser = subparsers.add_parser("status", help="Show proactive status")
    status_parser.set_defaults(func=cmd_status)
    
    # observe
    observe_parser = subparsers.add_parser("observe", help="Observe system state")
    observe_parser.set_defaults(func=cmd_observe)
    
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

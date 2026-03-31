#!/usr/bin/env python3
"""Goal Management CLI

Usage:
    python tools/goal_cli.py create "タイトル" "説明" [--priority high]
    python tools/goal_cli.py list [--active]
    python tools/goal_cli.py show <goal_id>
    python tools/goal_cli.py progress <goal_id> <percent>
    python tools/goal_cli.py complete <goal_id>
    python tools/goal_cli.py decompose <goal_id> [--auto]
    python tools/goal_cli.py report
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ops.goal_store import (
    create_goal, load_goals, get_goal_by_id, get_active_goals,
    update_goal, update_progress, add_note,
)
from ops.goal_decomposer import decompose_goal, suggest_decomposition, auto_decompose
from ops.progress_tracker import generate_progress_report, get_goal_tree, format_goal_tree


def cmd_create(args):
    goal = create_goal(
        title=args.title,
        description=args.description,
        priority=args.priority,
    )
    print(f"Created: {goal['id']}")
    print(f"  Title: {goal['title']}")
    return 0


def cmd_list(args):
    goals = get_active_goals() if args.active else load_goals()
    
    print(f"=== Goals ({len(goals)}) ===")
    for g in goals:
        status = "✅" if g["status"] == "completed" else "🔵"
        print(f"{status} [{g['priority'][0].upper()}] {g['id']}: {g['title']} ({g['progress']}%)")
    return 0


def cmd_show(args):
    goal = get_goal_by_id(args.goal_id)
    if not goal:
        print(f"Goal not found: {args.goal_id}")
        return 1
    
    tree = get_goal_tree(args.goal_id)
    print(format_goal_tree(tree))
    return 0


def cmd_progress(args):
    result = update_progress(args.goal_id, args.percent)
    if result:
        print(f"Updated progress: {args.goal_id} → {args.percent}%")
    else:
        print(f"Goal not found: {args.goal_id}")
        return 1
    return 0


def cmd_complete(args):
    result = update_goal(args.goal_id, status="completed")
    if result:
        print(f"Completed: {args.goal_id}")
    else:
        print(f"Goal not found: {args.goal_id}")
        return 1
    return 0


def cmd_decompose(args):
    if args.auto:
        subgoals = auto_decompose(args.goal_id)
        print(f"Auto-decomposed into {len(subgoals)} subgoals:")
    else:
        goal = get_goal_by_id(args.goal_id)
        if not goal:
            print(f"Goal not found: {args.goal_id}")
            return 1
        
        suggestions = suggest_decomposition(goal)
        print(f"Suggested decomposition ({len(suggestions)} subgoals):")
        for s in suggestions:
            print(f"  - {s['title']}: {s['description']}")
        print("\nUse --auto to apply")
        return 0
    
    for sg in subgoals:
        print(f"  - {sg['id']}: {sg['title']}")
    return 0


def cmd_report(args):
    report = generate_progress_report()
    
    print("=== Progress Report ===")
    print(f"Generated: {report['generated_at']}")
    
    s = report["summary"]
    print(f"\nSummary:")
    print(f"  Total: {s['total_goals']}, Active: {s['active']}, Completed: {s['completed']}")
    print(f"  Completion rate: {s['completion_rate']}%")
    
    if report["high_priority"]:
        print(f"\nHigh Priority:")
        for g in report["high_priority"]:
            print(f"  - {g['title']} ({g['progress']}%)")
    
    if report["stalled_goals"]:
        print(f"\nStalled (<20%):")
        for g in report["stalled_goals"]:
            print(f"  - {g['title']} ({g['progress']}%)")
    
    return 0


def main():
    parser = argparse.ArgumentParser(description="Goal Management")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # create
    p = subparsers.add_parser("create", help="Create a new goal")
    p.add_argument("title")
    p.add_argument("description")
    p.add_argument("--priority", default="medium", choices=["high", "medium", "low"])
    p.set_defaults(func=cmd_create)
    
    # list
    p = subparsers.add_parser("list", help="List goals")
    p.add_argument("--active", action="store_true")
    p.set_defaults(func=cmd_list)
    
    # show
    p = subparsers.add_parser("show", help="Show goal details")
    p.add_argument("goal_id")
    p.set_defaults(func=cmd_show)
    
    # progress
    p = subparsers.add_parser("progress", help="Update progress")
    p.add_argument("goal_id")
    p.add_argument("percent", type=int)
    p.set_defaults(func=cmd_progress)
    
    # complete
    p = subparsers.add_parser("complete", help="Mark goal as completed")
    p.add_argument("goal_id")
    p.set_defaults(func=cmd_complete)
    
    # decompose
    p = subparsers.add_parser("decompose", help="Decompose goal into subgoals")
    p.add_argument("goal_id")
    p.add_argument("--auto", action="store_true")
    p.set_defaults(func=cmd_decompose)
    
    # report
    p = subparsers.add_parser("report", help="Generate progress report")
    p.set_defaults(func=cmd_report)
    
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

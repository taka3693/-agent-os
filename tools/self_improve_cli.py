#!/usr/bin/env python3
"""Self-Improvement CLI

Usage:
    python tools/self_improve_cli.py run [--dry-run]
    python tools/self_improve_cli.py status
    python tools/self_improve_cli.py fixes
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from learning.self_improve import run_self_improvement_cycle, get_self_improvement_status
from learning.fix_proposer import load_pending_fixes


def cmd_run(args):
    """自己改善サイクルを実行"""
    result = run_self_improvement_cycle(dry_run=args.dry_run)
    
    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"{prefix}Self-Improvement Cycle Complete")
    print(f"  Issues analyzed: {result['issues_analyzed']}")
    print(f"  Fixes proposed: {result['fixes_proposed']}")
    
    for fix in result["fixes"]:
        print(f"\n  → [{fix['priority']}] {fix['description']}")
    return 0


def cmd_status(args):
    """状態を表示"""
    status = get_self_improvement_status()
    
    print(f"Total cycles: {status['total_cycles']}")
    print(f"Pending fixes: {status['pending_fixes']}")
    
    if status.get("last_cycle"):
        last = status["last_cycle"]
        print(f"\nLast run: {last['executed_at']}")
        print(f"  Issues: {last['issues_analyzed']}")
        print(f"  Fixes: {last['fixes_proposed']}")
    return 0


def cmd_fixes(args):
    """保留中の修正案を表示"""
    fixes = load_pending_fixes()
    
    print(f"=== Pending Fixes ({len(fixes)}) ===")
    for fix in fixes:
        print(f"\n[{fix.get('priority', '?')}] {fix.get('description')}")
        print(f"   Type: {fix.get('fix_type')}")
        print(f"   Category: {fix.get('category')}")
        for change in fix.get("code_changes", []):
            print(f"   → {change.get('description', change)}")
    
    if not fixes:
        print("  No pending fixes")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Self-Improvement System")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # run
    run_parser = subparsers.add_parser("run", help="Run self-improvement cycle")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.set_defaults(func=cmd_run)
    
    # status
    status_parser = subparsers.add_parser("status", help="Show status")
    status_parser.set_defaults(func=cmd_status)
    
    # fixes
    fixes_parser = subparsers.add_parser("fixes", help="Show pending fixes")
    fixes_parser.set_defaults(func=cmd_fixes)
    
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Learning CLI

Usage:
    python tools/learning_cli.py run [--dry-run]
    python tools/learning_cli.py status
    python tools/learning_cli.py patterns
    python tools/learning_cli.py policies
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from learning.learning_runner import run_learning_cycle, get_learning_status
from learning.pattern_extractor import extract_patterns, get_recommendations
from learning.action_policy import load_policies, get_active_policies


def cmd_run(args):
    """学習サイクルを実行"""
    result = run_learning_cycle(dry_run=args.dry_run)
    
    print(f"{'[DRY RUN] ' if args.dry_run else ''}Learning Cycle Complete")
    print(f"  Patterns found: {result['patterns_found']}")
    print(f"  Recommendations: {result['recommendations']}")
    print(f"  Policies saved: {result['policies_saved']}")
    return 0


def cmd_status(args):
    """学習状態を表示"""
    status = get_learning_status()
    
    print(f"Status: {status['status']}")
    if status.get("total_cycles"):
        print(f"Total cycles: {status['total_cycles']}")
    if status.get("last_cycle"):
        last = status["last_cycle"]
        print(f"Last run: {last['executed_at']}")
        print(f"  Patterns: {last['patterns_found']}")
        print(f"  Policies saved: {last['policies_saved']}")
    return 0


def cmd_patterns(args):
    """抽出されたパターンを表示"""
    patterns = extract_patterns()
    
    print(f"=== Patterns ({patterns['summary']['total_episodes']} episodes) ===")
    print(f"Outcome distribution: {patterns['summary']['outcome_distribution']}")
    
    if patterns["patterns"]:
        print("\nDetected patterns:")
        for p in patterns["patterns"]:
            print(f"  - [{p['type']}] {p.get('area', p.get('factor', p.get('failure_code')))}")
            print(f"    Recommendation: {p['recommendation']}")
    else:
        print("\nNo patterns detected yet (need more data)")
    return 0


def cmd_policies(args):
    """アクティブなポリシーを表示"""
    policies = get_active_policies()
    
    print(f"=== Active Policies ({len(policies)}) ===")
    for p in policies:
        print(f"  [{p.get('priority', '?')}] {p.get('action')}: {p.get('target')}")
        print(f"       Reason: {p.get('reason')}")
    
    if not policies:
        print("  No policies yet")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Learning System")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # run
    run_parser = subparsers.add_parser("run", help="Run learning cycle")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.set_defaults(func=cmd_run)
    
    # status
    status_parser = subparsers.add_parser("status", help="Show learning status")
    status_parser.set_defaults(func=cmd_status)
    
    # patterns
    patterns_parser = subparsers.add_parser("patterns", help="Show extracted patterns")
    patterns_parser.set_defaults(func=cmd_patterns)
    
    # policies
    policies_parser = subparsers.add_parser("policies", help="Show active policies")
    policies_parser.set_defaults(func=cmd_policies)
    
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

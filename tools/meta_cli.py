#!/usr/bin/env python3
"""Meta-Cognition CLI

Usage:
    python tools/meta_cli.py capabilities
    python tools/meta_cli.py assess "タスク説明"
    python tools/meta_cli.py limitations
    python tools/meta_cli.py report
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ops.capability_model import get_capabilities, get_limitations
from ops.self_assessor import assess_task, generate_self_report, should_ask_for_help
from ops.limitation_detector import get_limitation_stats


def cmd_capabilities(args):
    """能力一覧を表示"""
    caps = get_capabilities()
    
    print("=== Agent-OS Capabilities ===\n")
    for name, cap in sorted(caps.items(), key=lambda x: -x[1]["confidence"]):
        bar = "█" * int(cap["confidence"] * 10) + "░" * (10 - int(cap["confidence"] * 10))
        print(f"[{bar}] {cap['confidence']:.0%} {cap['name']}")
        print(f"       {cap['description']}")
        if cap["limitations"]:
            print(f"       ⚠️  {cap['limitations'][0]}")
        print()
    return 0


def cmd_assess(args):
    """タスクを評価"""
    task = {"query": args.task, "description": args.task}
    assessment = assess_task(task)
    
    print(f"=== Task Assessment ===\n")
    print(f"Task: {args.task[:50]}...")
    print(f"Type: {assessment['task_type']}")
    print(f"Can proceed: {'✅ Yes' if assessment['can_proceed'] else '❌ No'}")
    print(f"Confidence: {assessment['confidence']:.0%}")
    print(f"Complexity: {assessment['complexity']}")
    
    if assessment["warnings"]:
        print(f"\n⚠️ Warnings:")
        for w in assessment["warnings"]:
            print(f"   - {w}")
    
    if assessment["recommendations"]:
        print(f"\n💡 Recommendations:")
        for r in assessment["recommendations"]:
            print(f"   - {r}")
    
    # 助けを求めるべきか
    help_check = should_ask_for_help(assessment)
    if help_check["should_ask"]:
        print(f"\n🤔 Should ask for help:")
        for reason in help_check["reasons"]:
            print(f"   - {reason}")
        if help_check["suggested_question"]:
            print(f"\n   Suggested: \"{help_check['suggested_question']}\"")
    
    return 0


def cmd_limitations(args):
    """制限一覧と統計を表示"""
    limits = get_limitations()
    stats = get_limitation_stats()
    
    print("=== Known Limitations ===\n")
    for lim in limits:
        print(f"[{lim['category']}] {lim['description']}")
        print(f"   Reason: {lim['reason']}")
        print(f"   Mitigation: {lim['mitigation']}")
        print()
    
    if stats["total_events"] > 0:
        print(f"\n=== Limitation Events ===")
        print(f"Total events: {stats['total_events']}")
        print(f"Most common: {stats['most_common']}")
        for pattern, count in stats["patterns"].items():
            print(f"   {pattern}: {count}")
    
    return 0


def cmd_report(args):
    """自己認識レポート"""
    report = generate_self_report()
    
    print("=== Self-Awareness Report ===\n")
    print(f"Generated: {report['generated_at']}")
    
    s = report["summary"]
    print(f"\nSummary:")
    print(f"   Capabilities: {s['total_capabilities']}")
    print(f"   Limitations: {s['total_limitations']}")
    print(f"   Average confidence: {s['average_confidence']:.0%}")
    
    print(f"\nStrongest: {report['strongest_capability']['name']} ({report['strongest_capability']['confidence']:.0%})")
    print(f"Weakest: {report['weakest_capability']['name']} ({report['weakest_capability']['confidence']:.0%})")
    
    print(f"\nKey Limitations:")
    for lim in report["key_limitations"]:
        print(f"   - {lim}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(description="Meta-Cognition System")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # capabilities
    p = subparsers.add_parser("capabilities", help="Show capabilities")
    p.set_defaults(func=cmd_capabilities)
    
    # assess
    p = subparsers.add_parser("assess", help="Assess a task")
    p.add_argument("task", help="Task description")
    p.set_defaults(func=cmd_assess)
    
    # limitations
    p = subparsers.add_parser("limitations", help="Show limitations")
    p.set_defaults(func=cmd_limitations)
    
    # report
    p = subparsers.add_parser("report", help="Generate self-report")
    p.set_defaults(func=cmd_report)
    
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

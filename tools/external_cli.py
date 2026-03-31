#!/usr/bin/env python3
"""External Environment CLI

Usage:
    python tools/external_cli.py github
    python tools/external_cli.py env
    python tools/external_cli.py events [--react]
    python tools/external_cli.py status
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ops.github_observer import analyze_github_state, get_open_prs
from ops.environment_monitor import analyze_environment, get_system_resources
from ops.event_reactor import react_to_events, get_event_summary


def cmd_github(args):
    """GitHub状態を表示"""
    state = analyze_github_state()
    
    print("=== GitHub Status ===\n")
    
    # PRs
    prs = state.get("prs", {})
    if prs.get("count", 0) > 0:
        print(f"Open PRs: {prs['count']}")
        for pr in prs.get("prs", [])[:5]:
            draft = " [DRAFT]" if pr.get("isDraft") else ""
            print(f"  #{pr['number']}: {pr['title']}{draft}")
    else:
        print("Open PRs: 0")
    
    # CI
    ci = state.get("ci", {})
    if ci.get("failed_count", 0) > 0:
        print(f"\n❌ CI Failures: {ci['failed_count']}")
        for check in ci.get("failed_checks", [])[:3]:
            print(f"  - {check.get('name')}")
    else:
        print("\n✅ CI: All passing")
    
    # Actions
    if state.get("suggested_actions"):
        print("\n💡 Suggested Actions:")
        for action in state["suggested_actions"]:
            print(f"  - [{action['type']}] {action.get('reason', '')}")
    
    return 0


def cmd_env(args):
    """環境状態を表示"""
    env = analyze_environment()
    res = env["resources"]
    
    print("=== Environment Status ===\n")
    
    # CPU
    cpu = res.get("cpu", {})
    print(f"CPU: {cpu.get('usage_percent', 'N/A')}% (load: {cpu.get('load_1m', 'N/A')})")
    
    # Memory
    mem = res.get("memory", {})
    bar = "█" * int(mem.get("usage_percent", 0) / 10) + "░" * (10 - int(mem.get("usage_percent", 0) / 10))
    print(f"Memory: [{bar}] {mem.get('usage_percent', 'N/A')}% ({mem.get('used_gb', 0):.1f}/{mem.get('total_gb', 0):.1f} GB)")
    
    # Disk
    disk = res.get("disk", {})
    bar = "█" * int(disk.get("usage_percent", 0) / 10) + "░" * (10 - int(disk.get("usage_percent", 0) / 10))
    print(f"Disk: [{bar}] {disk.get('usage_percent', 'N/A')}% ({disk.get('used_gb', 0):.1f}/{disk.get('total_gb', 0):.1f} GB)")
    
    # OpenClaw
    oc = env.get("openclaw", {})
    status = "✅ Running" if oc.get("healthy") else "❌ Down"
    print(f"\nOpenClaw: {status}")
    
    # Warnings
    if env.get("warnings"):
        print("\n⚠️ Warnings:")
        for w in env["warnings"]:
            print(f"  - {w['type']}: {w.get('suggestion', '')}")
    
    return 0


def cmd_events(args):
    """イベントを収集して表示"""
    result = react_to_events(auto_execute=args.react)
    
    print(f"=== External Events ({result['events_count']}) ===\n")
    
    if result["events_count"] == 0:
        print("No events detected - environment is healthy!")
        return 0
    
    for r in result["reactions"]:
        event = r["event"]
        priority = "🔴" if r.get("action") == "investigate" else "🟡" if r.get("action") != "log_only" else "🟢"
        print(f"{priority} [{event['source']}] {event['type']}")
        print(f"   {r['message']}")
        if r.get("suggested_command"):
            print(f"   → {r['suggested_command']}")
        print()
    
    if result.get("auto_executed"):
        print("Auto-executed:")
        for ex in result["auto_executed"]:
            print(f"  ✅ {ex['action']}")
    
    return 0


def cmd_status(args):
    """全体ステータス"""
    github = analyze_github_state()
    env = analyze_environment()
    events = get_event_summary()
    
    print("=== Agent-OS External Status ===\n")
    
    # 健康度
    issues = len(github.get("warnings", [])) + len(env.get("warnings", []))
    health = "✅ Healthy" if issues == 0 else f"⚠️ {issues} issue(s)"
    print(f"Overall: {health}")
    
    # サマリー
    print(f"\nGitHub: {github.get('prs', {}).get('count', 0)} PRs, {github.get('ci', {}).get('failed_count', 0)} CI failures")
    print(f"Environment: CPU {env['resources'].get('cpu', {}).get('usage_percent', 0)}%, Mem {env['resources'].get('memory', {}).get('usage_percent', 0)}%")
    print(f"Event History: {events['total_events']} total events")
    
    return 0


def main():
    parser = argparse.ArgumentParser(description="External Environment")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    subparsers.add_parser("github", help="Show GitHub status").set_defaults(func=cmd_github)
    subparsers.add_parser("env", help="Show environment status").set_defaults(func=cmd_env)
    
    p = subparsers.add_parser("events", help="Show and react to events")
    p.add_argument("--react", action="store_true", help="Auto-execute reactions")
    p.set_defaults(func=cmd_events)
    
    subparsers.add_parser("status", help="Overall status").set_defaults(func=cmd_status)
    
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

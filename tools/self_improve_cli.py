#!/usr/bin/env python3
"""Self-Improvement CLI

Usage:
    python tools/self_improve_cli.py run [--dry-run]
    python tools/self_improve_cli.py full [--auto-apply] [--auto-pr] [--chat-id ID]
    python tools/self_improve_cli.py approve <fix_id> [--auto-pr]
    python tools/self_improve_cli.py status
    python tools/self_improve_cli.py fixes
    python tools/self_improve_cli.py skills
    python tools/self_improve_cli.py generate-skill <name> <description>
    python tools/self_improve_cli.py arch
    python tools/self_improve_cli.py refactor <proposal_id> [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from learning.self_improve import (
    run_self_improvement_cycle,
    get_self_improvement_status,
    run_full_self_improvement_cycle,
    approve_and_apply_fix,
)
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



def cmd_llm(args):
    """LLMを使った自己改善サイクル"""
    from learning.llm_fix_proposer import run_llm_improvement_cycle

    result = run_llm_improvement_cycle(dry_run=args.dry_run, max_fixes=args.max)

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"{prefix}LLM Self-Improvement Cycle")
    print(f"  Issues analyzed: {result.get('issues_analyzed', 0)}")
    print(f"  Fixes generated: {result['fixes_generated']}")

    for fix in result.get("fixes", []):
        print(f"\n  === Fix ({fix.get('generated_by', 'unknown')}) ===")
        print(f"  Type: {fix.get('fix_type', 'N/A')}")
        print(f"  Priority: {fix.get('priority', 'N/A')}")
        print(f"  Analysis: {fix.get('analysis', 'N/A')[:100]}...")

        for change in fix.get("changes", [])[:2]:
            print(f"  → {change.get('file', 'N/A')}: {change.get('description', 'N/A')[:50]}")

    return 0


def cmd_full(args):
    """完全自己改善サイクルを実行"""
    result = run_full_self_improvement_cycle(
        auto_apply=args.auto_apply,
        auto_pr=args.auto_pr,
        chat_id=args.chat_id,
    )

    print("=== Full Self-Improvement Cycle ===")
    print(f"  Issues analyzed: {result.get('issues_analyzed', 0)}")
    print(f"  Fixes proposed: {result.get('fixes_proposed', 0)}")

    if args.auto_apply:
        print(f"  Auto-apply: {'✅' if result.get('apply_ok') else '❌'}")
        if result.get('apply_ok'):
            print(f"  Verification: {'✅' if result.get('verify_ok') else '❌'}")
            if result.get('verify_ok') and args.auto_pr:
                print(f"  PR created: {result.get('pr_url', 'N/A')}")
            elif not result.get('verify_ok'):
                print(f"  Rollback: {'✅' if result.get('rollback_ok') else '❌'}")

    if result.get('error'):
        print(f"  Error: {result['error']}")

    if result.get('mission_id'):
        print(f"  MISO mission: {result['mission_id']}")

    return 0 if result.get('ok') else 1


def cmd_approve(args):
    """修正を承認して適用"""
    result = approve_and_apply_fix(
        fix_id=args.fix_id,
        auto_pr=args.auto_pr,
    )

    print(f"=== Approve & Apply Fix: {args.fix_id} ===")
    print(f"  Apply: {'✅' if result.get('apply_ok') else '❌'}")
    print(f"  Verify: {'✅' if result.get('verify_ok') else '❌'}")

    if result.get('verify_ok') and args.auto_pr:
        print(f"  PR: {result.get('pr_url', 'N/A')}")
    elif not result.get('verify_ok'):
        print(f"  Rollback: {'✅' if result.get('rollback_ok') else '❌'}")

    if result.get('error'):
        print(f"  Error: {result['error']}")

    return 0 if result.get('ok') else 1


def cmd_skills(args):
    """スキルギャップを分析"""
    from learning.skill_generator import analyze_skill_gaps, generate_skill

    gaps = analyze_skill_gaps()

    print(f"=== Skill Gap Analysis ===")
    print(f"  Existing skills: {len(gaps['existing'])}")
    print(f"  Missing capabilities: {len(gaps['missing'])}")
    print(f"  Suggestions: {len(gaps['suggestions'])}")

    print("\n--- Missing Capabilities (first 10) ---")
    for cap in gaps['missing'][:10]:
        print(f"  • {cap}")
    if len(gaps['missing']) > 10:
        print(f"  ... and {len(gaps['missing']) - 10} more")

    print("\n--- Skill Suggestions ---")
    for suggestion in gaps['suggestions']:
        print(f"\n  [{suggestion['name']}] (priority: {suggestion['priority']})")
        print(f"  {suggestion['description']}")
        print(f"  Capabilities: {', '.join(suggestion['capabilities'])}")

    return 0


def cmd_generate_skill(args):
    """新しいスキルを生成"""
    from learning.skill_generator import generate_skill, validate_skill, deploy_skill
    from pathlib import Path

    # Generate skill
    result = generate_skill(
        skill_name=args.name,
        description=args.description,
        capabilities=args.capabilities or [],
    )

    if not result.get('ok'):
        print(f"❌ Generation failed: {result.get('error')}")
        return 1

    print(f"✅ Skill generated at: {result['path']}")

    # Validate
    if args.validate:
        validation = validate_skill(Path(result['path']))
        if validation['ok']:
            print(f"✅ Validation passed")
        else:
            print(f"❌ Validation failed:")
            for err in validation.get('errors', []):
                print(f"  • {err}")
            for warn in validation.get('warnings', []):
                print(f"  ⚠️  {warn}")

    # Deploy
    if args.deploy:
        deploy_result = deploy_skill(Path(result['path']))
        if deploy_result['ok']:
            print(f"✅ Deployed to: {deploy_result['deployed_path']}")
        else:
            print(f"❌ Deploy failed: {deploy_result.get('error')}")
            return 1

    return 0


def cmd_arch(args):
    """アーキテクチャを分析"""
    from learning.architecture_evolver import analyze_architecture, propose_improvements

    analysis = analyze_architecture()

    print(f"=== Architecture Analysis ===")
    print(f"  Modules: {len(analysis['modules'])}")
    print(f"  Issues: {len(analysis['issues'])}")
    print(f"  Circular dependencies: {len(analysis['dependencies'].get('cycles', []))}")

    # Show issues by type
    issues_by_type = {}
    for issue in analysis['issues']:
        issue_type = issue['type']
        if issue_type not in issues_by_type:
            issues_by_type[issue_type] = []
        issues_by_type[issue_type].append(issue)

    print("\n--- Issues by Type ---")
    for issue_type, issues in sorted(issues_by_type.items()):
        print(f"\n  {issue_type}: {len(issues)}")
        for issue in issues[:3]:
            print(f"    • {issue.get('description', 'N/A')}")
        if len(issues) > 3:
            print(f"    ... and {len(issues) - 3} more")

    # Get and show proposals
    proposals = propose_improvements(analysis)
    print(f"\n--- Improvement Proposals (first 10 of {len(proposals['proposals'])}) ---")
    for proposal in proposals['proposals'][:10]:
        print(f"\n  [{proposal['id']}] (priority: {proposal['priority']})")
        print(f"  {proposal['description']}")
        print(f"  Estimated effort: {proposal.get('estimated_effort', 'unknown')}")

    return 0


def cmd_refactor(args):
    """リファクタリングを実行"""
    from learning.architecture_evolver import create_refactoring_plan, execute_refactoring

    # Create plan
    plan = create_refactoring_plan(args.proposal_id)
    if not plan.get('ok'):
        print(f"❌ Failed to create plan: {plan.get('error')}")
        return 1

    print(f"=== Refactoring Plan: {args.proposal_id} ===")
    print(f"  Description: {plan['proposal']['description']}")
    print(f"  Estimated impact: {plan['estimated_impact']}")
    print("\n  Steps:")
    for i, step in enumerate(plan['steps'], 1):
        print(f"    {i}. {step}")

    if args.dry_run:
        print("\n[DRY RUN] Skipping execution")
        return 0

    # Execute
    print("\nExecuting refactoring...")
    result = execute_refactoring(plan, dry_run=args.dry_run, chat_id=args.chat_id)

    if result['ok']:
        print(f"✅ Refactoring completed")
        print(f"  Changes: {len(result['changes'])}")
    else:
        print(f"❌ Refactoring failed:")
        for err in result.get('errors', []):
            print(f"  • {err}")

    return 0 if result['ok'] else 1


def main():
    parser = argparse.ArgumentParser(description="Self-Improvement System")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    run_parser = subparsers.add_parser("run", help="Run self-improvement cycle")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.set_defaults(func=cmd_run)

    # full
    full_parser = subparsers.add_parser("full", help="Run full self-improvement cycle with apply/PR")
    full_parser.add_argument("--auto-apply", action="store_true", help="Automatically apply fixes")
    full_parser.add_argument("--auto-pr", action="store_true", help="Automatically create PRs")
    full_parser.add_argument("--chat-id", help="Telegram chat ID for MISO notification")
    full_parser.set_defaults(func=cmd_full)

    # approve
    approve_parser = subparsers.add_parser("approve", help="Approve and apply a specific fix")
    approve_parser.add_argument("fix_id", help="Fix ID to approve")
    approve_parser.add_argument("--auto-pr", action="store_true", help="Auto-create PR after apply")
    approve_parser.set_defaults(func=cmd_approve)

    # status
    status_parser = subparsers.add_parser("status", help="Show status")
    status_parser.set_defaults(func=cmd_status)

    # fixes
    fixes_parser = subparsers.add_parser("fixes", help="Show pending fixes")
    fixes_parser.set_defaults(func=cmd_fixes)

    # llm
    llm_parser = subparsers.add_parser("llm", help="Run LLM-powered improvement cycle")
    llm_parser.add_argument("--dry-run", action="store_true")
    llm_parser.add_argument("--max", type=int, default=3, help="Max fixes to generate")
    llm_parser.set_defaults(func=cmd_llm)

    # skills
    skills_parser = subparsers.add_parser("skills", help="Analyze skill gaps")
    skills_parser.set_defaults(func=cmd_skills)

    # generate-skill
    gen_skill_parser = subparsers.add_parser("generate-skill", help="Generate a new skill")
    gen_skill_parser.add_argument("name", help="Skill name (snake_case)")
    gen_skill_parser.add_argument("description", help="Skill description")
    gen_skill_parser.add_argument("--capabilities", nargs="+", help="List of capabilities")
    gen_skill_parser.add_argument("--validate", action="store_true", help="Validate after generation")
    gen_skill_parser.add_argument("--deploy", action="store_true", help="Deploy to skills/")
    gen_skill_parser.set_defaults(func=cmd_generate_skill)

    # arch
    arch_parser = subparsers.add_parser("arch", help="Analyze architecture")
    arch_parser.set_defaults(func=cmd_arch)

    # refactor
    refactor_parser = subparsers.add_parser("refactor", help="Execute refactoring plan")
    refactor_parser.add_argument("proposal_id", help="Proposal ID to refactor")
    refactor_parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    refactor_parser.add_argument("--chat-id", help="Telegram chat ID for MISO")
    refactor_parser.set_defaults(func=cmd_refactor)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

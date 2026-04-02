"""Self-Improvement Runner - 自己改善サイクル

1. 失敗・問題を分析
2. 修正案を生成
3. 承認キューに登録（または自動適用）
4. 修正適用・検証・PR作成（拡張フロー）
"""
from __future__ import annotations
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"

# Configure logging
LOG_DIR = PROJECT_ROOT / "learning" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"self_improve_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from learning.failure_analyzer import run_full_analysis, get_improvement_suggestions
from learning.fix_proposer import propose_fixes_offline, save_fix_proposals

# Extended modules for full self-improvement cycle
try:
    from learning.fix_applier import apply_fix, rollback_fix
    FIX_APPLIER_AVAILABLE = True
except ImportError:
    FIX_APPLIER_AVAILABLE = False
    logger.warning("fix_applier not available")

try:
    from learning.fix_verifier import verify_fix
    FIX_VERIFIER_AVAILABLE = True
except ImportError:
    FIX_VERIFIER_AVAILABLE = False
    logger.warning("fix_verifier not available")

try:
    from learning.auto_pr import auto_pr_workflow
    AUTO_PR_AVAILABLE = True
except ImportError:
    AUTO_PR_AVAILABLE = False
    logger.warning("auto_pr not available")

# MISO bridge integration
try:
    from miso.bridge import start_mission, update_agent_status, complete_mission, fail_mission
    MISO_AVAILABLE = True
except ImportError:
    MISO_AVAILABLE = False
    logger.warning("MISO bridge not available")


def run_self_improvement_cycle(
    dry_run: bool = False,
) -> Dict[str, Any]:
    """自己改善サイクルを実行
    
    Args:
        dry_run: Trueの場合、修正案を保存しない
    
    Returns:
        サイクル実行結果
    """
    # 1. 問題分析
    analysis = run_full_analysis()
    
    # 2. 修正案生成
    fixes = propose_fixes_offline(analysis["suggestions"])
    
    # 3. 保存（dry_runでなければ）
    saved_file = None
    if not dry_run and fixes:
        saved_file = save_fix_proposals(fixes)
    
    result = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "issues_analyzed": analysis["issues_found"],
        "suggestions_generated": len(analysis["suggestions"]),
        "fixes_proposed": len(fixes),
        "saved_to": str(saved_file) if saved_file else None,
        "fixes": fixes,
    }
    
    # ログに記録
    if not dry_run:
        log_file = STATE_DIR / "self_improvement_cycles.jsonl"
        log_entry = {k: v for k, v in result.items() if k != "fixes"}
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    
    return result


def get_self_improvement_status() -> Dict[str, Any]:
    """自己改善サイクルの状態を取得"""
    log_file = STATE_DIR / "self_improvement_cycles.jsonl"
    fix_file = STATE_DIR / "fix_proposals.jsonl"

    status = {
        "total_cycles": 0,
        "last_cycle": None,
        "pending_fixes": 0,
    }

    if log_file.exists():
        lines = [l for l in log_file.read_text().strip().split("\n") if l.strip()]
        status["total_cycles"] = len(lines)
        if lines:
            try:
                status["last_cycle"] = json.loads(lines[-1])
            except json.JSONDecodeError:
                pass

    if fix_file.exists():
        pending = 0
        for line in fix_file.read_text().strip().split("\n"):
            if line.strip():
                try:
                    fix = json.loads(line)
                    if fix.get("status") == "proposed":
                        pending += 1
                except json.JSONDecodeError:
                    continue
        status["pending_fixes"] = pending

    return status


# ===== Extended Full Self-Improvement Cycle =====

def notify_cycle_result(
    cycle_type: str,
    result: Dict[str, Any],
    chat_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    自己改善サイクルの結果をTelegram通知する

    Args:
        cycle_type: サイクル種別 ("full" or "approve")
        result: サイクル実行結果
        chat_id: Telegram chat ID (optional)

    Returns:
        通知結果
    """
    try:
        if cycle_type == "full":
            emoji = "🔄" if result.get("ok") else "⚠️"
            title = "Full Self-Improvement Cycle" if result.get("ok") else "Cycle Failed"

            # Build message
            lines = [
                f"{emoji} {title}",
                f"Status: {'✅ Success' if result.get('ok') else '❌ Failed'}",
                f"Issues Analyzed: {result.get('issues_analyzed', 0)}",
                f"Fixes Proposed: {result.get('fixes_proposed', 0)}",
            ]

            if result.get("auto_apply"):
                lines.append(f"Auto-Apply: {'✅ Applied' if result.get('apply_ok') else '❌ Failed'}")
                if result.get("apply_ok"):
                    lines.append(f"Verification: {'✅ Passed' if result.get('verify_ok') else '❌ Failed'}")
                    if result.get("verify_ok") and result.get("auto_pr"):
                        pr_url = result.get("pr_url")
                        lines.append(f"PR Created: {pr_url if pr_url else '❌ Failed'}")
                    elif not result.get("verify_ok") and result.get("rollback_ok"):
                        lines.append("Rollback: ✅ Executed")

            if result.get("error"):
                lines.append(f"Error: {result['error']}")

        elif cycle_type == "approve":
            fix_id = result.get("fix_id", "unknown")
            emoji = "✅" if result.get("ok") else "❌"
            title = f"Fix Approved & Applied: {fix_id}"

            lines = [
                f"{emoji} {title}",
                f"Apply: {'✅ Success' if result.get('apply_ok') else '❌ Failed'}",
                f"Verify: {'✅ Passed' if result.get('verify_ok') else '❌ Failed'}",
            ]

            if result.get("verify_ok") and result.get("auto_pr"):
                pr_url = result.get("pr_url")
                lines.append(f"PR: {pr_url if pr_url else '❌ Failed'}")
            elif not result.get("verify_ok") and result.get("rollback_ok"):
                lines.append("Rollback: ✅ Executed")

            if result.get("error"):
                lines.append(f"Error: {result['error']}")
        else:
            return {"ok": False, "error": f"Unknown cycle type: {cycle_type}"}

        message = "\n".join(lines)

        # Try to use message tool
        try:
            from openclaw_tools import message as msg_tool
            msg_tool.send(
                action="send",
                channel="telegram",
                target=chat_id,
                message=message
            )
            logger.info(f"Sent Telegram notification: {cycle_type} cycle")
            return {"ok": True}
        except ImportError:
            # Fallback to subprocess
            try:
                subprocess.run(
                    ["openclaw", "message", "send", "--message", message],
                    capture_output=True,
                    timeout=30
                )
                return {"ok": True}
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")
                return {"ok": False, "error": str(e)}

    except Exception as e:
        logger.error(f"Failed to notify cycle result: {e}")
        return {"ok": False, "error": str(e)}


def run_full_self_improvement_cycle(
    auto_apply: bool = False,
    auto_pr: bool = False,
    chat_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    完全自己改善サイクルを実行

    1. 問題分析
    2. 修正案生成
    3. 修正適用 (auto_apply=True時)
    4. 検証 (auto_apply=True時)
    5. PR作成 (auto_apply=True & auto_pr=True & 検証成功時)
    6. ロールバック (検証失敗時)
    7. Telegram通知

    Args:
        auto_apply: Trueで自動適用、Falseで承認キュー登録のみ
        auto_pr: Trueで検証成功時に自動PR作成
        chat_id: Telegram chat ID (for MISO notification)

    Returns:
        サイクル実行結果
    """
    logger.info(f"Starting full self-improvement cycle (auto_apply={auto_apply}, auto_pr={auto_pr})")

    # Generate mission ID
    mission_id = f"si-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Define agents
    agents = ["analyzer", "proposer"]
    if auto_apply:
        agents.extend(["applier", "verifier"])
        if auto_pr:
            agents.append("pr_creator")

    # Start MISO mission
    miso_started = False
    if MISO_AVAILABLE and chat_id:
        try:
            goal = "Analyze issues, generate fixes" if not auto_apply else "Full self-improvement: analyze, propose, apply, verify"
            start_mission(
                mission_id=mission_id,
                mission_name="Self-Improvement Cycle",
                goal=goal,
                chat_id=chat_id,
                agents=agents
            )
            miso_started = True
            logger.info(f"Started MISO mission: {mission_id}")
        except Exception as e:
            logger.warning(f"Failed to start MISO mission: {e}")

    result = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "cycle_type": "full",
        "auto_apply": auto_apply,
        "auto_pr": auto_pr,
        "ok": False,
        "error": None,
        "mission_id": mission_id if miso_started else None,
    }

    try:
        # Step 1: 問題分析
        logger.info("Step 1: Analyzing issues...")
        if miso_started:
            update_agent_status(mission_id, "analyzer", "RUNNING")
        analysis = run_full_analysis()
        result["issues_analyzed"] = analysis["issues_found"]
        if miso_started:
            update_agent_status(mission_id, "analyzer", "DONE")

        # Step 2: 修正案生成
        logger.info("Step 2: Generating fix proposals...")
        if miso_started:
            update_agent_status(mission_id, "proposer", "RUNNING")
        fixes = propose_fixes_offline(analysis["suggestions"])
        result["fixes_proposed"] = len(fixes)
        result["fixes"] = fixes
        if miso_started:
            update_agent_status(mission_id, "proposer", "DONE")

        # Save proposals
        saved_file = save_fix_proposals(fixes)
        result["saved_to"] = str(saved_file) if saved_file else None

        # If not auto_apply, we're done
        if not auto_apply:
            result["ok"] = True
            logger.info("Cycle completed (proposals saved, awaiting approval)")
            if miso_started:
                complete_mission(mission_id, f"Generated {len(fixes)} fix proposals")
            notify_cycle_result("full", result, chat_id)
            return result

        # Step 3: 修正適用
        logger.info("Step 3: Applying fixes...")
        if miso_started:
            update_agent_status(mission_id, "applier", "RUNNING")
        result["apply_ok"] = False
        result["apply_result"] = None
        result["branch"] = None

        if not FIX_APPLIER_AVAILABLE:
            raise Exception("fix_applier not available")

        # Apply each fix
        applied_fixes = []
        failed_fixes = []

        for fix in fixes:
            apply_result = apply_fix(fix)
            if apply_result["ok"]:
                applied_fixes.append({
                    "fix_id": fix.get("id"),
                    "branch": apply_result.get("branch"),
                    "commit_hash": apply_result.get("commit_hash")
                })
            else:
                failed_fixes.append({
                    "fix_id": fix.get("id"),
                    "error": apply_result.get("error")
                })

        result["apply_result"] = {
            "applied": len(applied_fixes),
            "failed": len(failed_fixes),
            "details": applied_fixes
        }

        if not applied_fixes:
            result["error"] = "No fixes were applied successfully"
            if miso_started:
                fail_mission(mission_id, result["error"])
            notify_cycle_result("full", result, chat_id)
            return result

        result["apply_ok"] = True
        result["branch"] = applied_fixes[0]["branch"]  # Use first branch
        if miso_started:
            update_agent_status(mission_id, "applier", "DONE")

        # Step 4: 検証
        logger.info("Step 4: Verifying fixes...")
        if miso_started:
            update_agent_status(mission_id, "verifier", "RUNNING")
        result["verify_ok"] = False
        result["verify_result"] = None

        if not FIX_VERIFIER_AVAILABLE:
            raise Exception("fix_verifier not available")

        # Collect all changed files for verification
        changed_files = []
        for fix in fixes:
            for change in fix.get("code_changes", []):
                file_path = change.get("file")
                if file_path and file_path not in changed_files:
                    changed_files.append(file_path)

        # Verify each fix
        verification_results = []
        for applied in applied_fixes:
            fix_id = applied["fix_id"]
            verify_result = verify_fix(fix_id, changed_files)
            verification_results.append(verify_result)

            if not verify_result["ok"]:
                # Rollback this fix
                logger.warning(f"Fix {fix_id} verification failed, rolling back...")
                rollback_ok = rollback_fix(applied["branch"])
                result["rollback_ok"] = rollback_ok
                result["error"] = f"Fix {fix_id} verification failed and was rolled back"

                if miso_started:
                    fail_mission(mission_id, result["error"])
                notify_cycle_result("full", result, chat_id)
                return result

        result["verify_ok"] = True
        result["verify_result"] = verification_results
        if miso_started:
            update_agent_status(mission_id, "verifier", "DONE")

        # Step 5: PR作成 (auto_pr=True時のみ)
        result["pr_created"] = False
        result["pr_url"] = None
        result["pr_number"] = None

        if auto_pr and AUTO_PR_AVAILABLE:
            logger.info("Step 5: Creating PRs...")
            if miso_started:
                update_agent_status(mission_id, "pr_creator", "RUNNING")

            for i, (applied, fix) in enumerate(zip(applied_fixes, fixes)):
                pr_result = auto_pr_workflow(
                    fix_id=applied["fix_id"],
                    branch=applied["branch"],
                    title=fix.get("description", f"Fix {applied['fix_id']}"),
                    description=f"Automated fix for {applied['fix_id']}\n\n"
                               f"Changes:\n{json.dumps(fix.get('code_changes', []), indent=2)}",
                    labels=["automated", "self-improvement"],
                    notify=False  # We'll notify once at the end
                )

                if pr_result["ok"] and i == 0:
                    result["pr_created"] = True
                    result["pr_url"] = pr_result.get("pr_url")
                    result["pr_number"] = pr_result.get("pr_number")

            if miso_started:
                update_agent_status(mission_id, "pr_creator", "DONE")

        result["ok"] = True
        logger.info("Full self-improvement cycle completed successfully")

        if miso_started:
            summary = f"Completed: {result['issues_analyzed']} issues, {len(applied_fixes)} fixes applied"
            if result["pr_created"]:
                summary += f", PR #{result['pr_number']} created"
            complete_mission(mission_id, summary)

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Full self-improvement cycle failed: {e}")
        if miso_started:
            fail_mission(mission_id, str(e))

    # Notify result
    notify_cycle_result("full", result, chat_id)

    return result


def get_pending_fixes() -> List[Dict[str, Any]]:
    """
    承認待ちの修正案を取得

    Returns:
        承認待ちの修正案リスト
    """
    fix_file = STATE_DIR / "fix_proposals.jsonl"
    pending = []

    if fix_file.exists():
        for line in fix_file.read_text().strip().split("\n"):
            if line.strip():
                try:
                    fix = json.loads(line)
                    if fix.get("status") == "proposed":
                        pending.append(fix)
                except json.JSONDecodeError:
                    continue

    return pending


def approve_fix(fix_id: str) -> Dict[str, Any]:
    """
    修正案を承認済みにマーク

    Args:
        fix_id: 承認する修正ID

    Returns:
        承認結果
    """
    fix_file = STATE_DIR / "fix_proposals.jsonl"

    if not fix_file.exists():
        return {"ok": False, "error": "No fix proposals file found"}

    lines = fix_file.read_text().split("\n")
    updated_lines = []
    found = False

    for line in lines:
        if line.strip():
            try:
                fix = json.loads(line)
                if fix.get("id") == fix_id:
                    fix["status"] = "approved"
                    fix["approved_at"] = datetime.now(timezone.utc).isoformat()
                    found = True
                updated_lines.append(json.dumps(fix, ensure_ascii=False))
            except json.JSONDecodeError:
                updated_lines.append(line)
        else:
            updated_lines.append(line)

    if not found:
        return {"ok": False, "error": f"Fix {fix_id} not found"}

    fix_file.write_text("\n".join(updated_lines))
    logger.info(f"Fix {fix_id} approved")

    return {"ok": True, "fix_id": fix_id}


def approve_and_apply_fix(fix_id: str, auto_pr: bool = False, chat_id: Optional[str] = None) -> Dict[str, Any]:
    """
    承認キューから修正を適用

    1. 修正案を承認済みにマーク
    2. 修正を適用
    3. 検証
    4. 検証成功ならPR作成
    5. 検証失敗ならロールバック
    6. Telegram通知

    Args:
        fix_id: 適用する修正ID
        auto_pr: Trueで検証成功時に自動PR作成
        chat_id: Telegram chat ID (for MISO notification)

    Returns:
        適用結果
    """
    logger.info(f"Starting approve and apply workflow for fix {fix_id}")

    # Generate mission ID
    mission_id = f"fix-{fix_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Define agents
    agents = ["approver", "applier", "verifier"]
    if auto_pr:
        agents.append("pr_creator")

    # Start MISO mission
    miso_started = False
    if MISO_AVAILABLE and chat_id:
        try:
            start_mission(
                mission_id=mission_id,
                mission_name=f"Fix Application: {fix_id}",
                goal=f"Apply approved fix {fix_id}",
                chat_id=chat_id,
                agents=agents
            )
            miso_started = True
            logger.info(f"Started MISO mission: {mission_id}")
        except Exception as e:
            logger.warning(f"Failed to start MISO mission: {e}")

    result = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "cycle_type": "approve",
        "fix_id": fix_id,
        "auto_pr": auto_pr,
        "ok": False,
        "error": None,
        "mission_id": mission_id if miso_started else None,
    }

    try:
        # Get the fix proposal
        if miso_started:
            update_agent_status(mission_id, "approver", "RUNNING")
        pending_fixes = get_pending_fixes()
        target_fix = None
        for fix in pending_fixes:
            if fix.get("id") == fix_id:
                target_fix = fix
                break

        if not target_fix:
            result["error"] = f"Fix {fix_id} not found in pending fixes"
            if miso_started:
                fail_mission(mission_id, result["error"])
            notify_cycle_result("approve", result, chat_id)
            return result

        # Approve the fix
        approve_result = approve_fix(fix_id)
        if not approve_result["ok"]:
            result["error"] = f"Failed to approve fix: {approve_result['error']}"
            if miso_started:
                fail_mission(mission_id, result["error"])
            notify_cycle_result("approve", result, chat_id)
            return result
        if miso_started:
            update_agent_status(mission_id, "approver", "DONE")

        # Apply the fix
        logger.info(f"Applying fix {fix_id}...")
        if miso_started:
            update_agent_status(mission_id, "applier", "RUNNING")
        if not FIX_APPLIER_AVAILABLE:
            raise Exception("fix_applier not available")

        apply_result = apply_fix(target_fix)
        result["apply_ok"] = apply_result["ok"]
        result["branch"] = apply_result.get("branch")

        if not apply_result["ok"]:
            result["error"] = apply_result.get("error")
            if miso_started:
                fail_mission(mission_id, result["error"])
            notify_cycle_result("approve", result, chat_id)
            return result
        if miso_started:
            update_agent_status(mission_id, "applier", "DONE")

        # Verify the fix
        logger.info(f"Verifying fix {fix_id}...")
        if miso_started:
            update_agent_status(mission_id, "verifier", "RUNNING")
        if not FIX_VERIFIER_AVAILABLE:
            raise Exception("fix_verifier not available")

        # Collect changed files
        changed_files = [
            change.get("file")
            for change in target_fix.get("code_changes", [])
            if change.get("file")
        ]

        verify_result = verify_fix(fix_id, changed_files)
        result["verify_ok"] = verify_result["ok"]
        result["verify_result"] = verify_result

        if not verify_result["ok"]:
            # Rollback
            logger.warning(f"Fix {fix_id} verification failed, rolling back...")
            rollback_ok = rollback_fix(apply_result.get("branch"))
            result["rollback_ok"] = rollback_ok
            result["error"] = f"Verification failed and rolled back"
            if miso_started:
                fail_mission(mission_id, result["error"])
            notify_cycle_result("approve", result, chat_id)
            return result
        if miso_started:
            update_agent_status(mission_id, "verifier", "DONE")

        # Create PR (if auto_pr)
        result["pr_created"] = False
        result["pr_url"] = None

        if auto_pr and AUTO_PR_AVAILABLE:
            logger.info(f"Creating PR for fix {fix_id}...")
            if miso_started:
                update_agent_status(mission_id, "pr_creator", "RUNNING")
            pr_result = auto_pr_workflow(
                fix_id=fix_id,
                branch=apply_result.get("branch"),
                title=target_fix.get("description", f"Fix {fix_id}"),
                description=f"Approved and applied fix for {fix_id}\n\n"
                           f"Changes:\n{json.dumps(target_fix.get('code_changes', []), indent=2)}",
                labels=["automated", "approved"],
                notify=False
            )

            if pr_result["ok"]:
                result["pr_created"] = True
                result["pr_url"] = pr_result.get("pr_url")
                result["pr_number"] = pr_result.get("pr_number")
            if miso_started:
                update_agent_status(mission_id, "pr_creator", "DONE")

        result["ok"] = True
        logger.info(f"Fix {fix_id} approved and applied successfully")

        if miso_started:
            summary = f"Fix {fix_id} applied successfully"
            if result["pr_created"]:
                summary += f", PR #{result['pr_number']} created"
            complete_mission(mission_id, summary)

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Approve and apply workflow failed: {e}")
        if miso_started:
            fail_mission(mission_id, str(e))

    # Notify result
    notify_cycle_result("approve", result, chat_id)

    return result

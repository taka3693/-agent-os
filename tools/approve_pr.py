#!/usr/bin/env python3
"""
Approve PR - 承認と次アクション提示

責務:
- 承認待ち状態を読み込み
- リスク/チェックを再表示
- 次アクションを提示
- 承認済み状態を更新
"""
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state" / "pr_gate"

def load_state(state_file: str) -> Dict[str, Any]:
    """状態ファイルを読み込み"""
    path = Path(state_file)
    if not path.exists():
        return {"ok": False, "error": "state_file_not_found", "path": state_file}
    
    return json.loads(path.read_text())

def determine_next_action(state: Dict[str, Any]) -> str:
    """次アクションを決定"""
    risk_level = state.get("risk_level", "medium")
    status = state.get("status", "pending_approval")
    
    if status == "approved":
        return "ready_to_merge"
    
    if risk_level == "high":
        return "manual_review_required"
    
    if risk_level == "medium":
        return "manual_review_recommended"
    
    return "eligible_for_merge"

def update_state(state: Dict[str, Any], status: str) -> None:
    """状態を更新"""
    state_file = Path(state.get("state_file", ""))
    if not state_file.exists():
        return
    
    state["status"] = status
    state["approved_at"] = datetime.now().isoformat()
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))

def main():
    """メインエントリーポイント"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Approve PR")
    parser.add_argument("--state", required=True, help="State file path")
    
    args = parser.parse_args()
    
    # 状態読み込み
    state = load_state(args.state)
    
    if not state.get("ok", True):
        print(json.dumps(state, ensure_ascii=False, indent=2))
        sys.exit(1)
    
    # 現在の状態確認
    if state.get("status") == "approved":
        result = {
            "ok": True,
            "status": "already_approved",
            "risk_level": state.get("risk_level"),
            "next_action": determine_next_action(state),
            "state_file": state.get("state_file")
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    
    # 承認
    risk_level = state.get("risk_level", "medium")
    next_action = determine_next_action(state)
    
    # 状態更新
    update_state(state, "approved")
    
    result = {
        "ok": True,
        "status": "approved",
        "risk_level": risk_level,
        "next_action": next_action,
        "state_file": state.get("state_file"),
        "branch": state.get("branch"),
        "base": state.get("base"),
        "pr_title": state.get("pr_title"),
        "merge_command": f"git checkout {state.get('base')} && git merge {state.get('branch')}"
    }
    
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

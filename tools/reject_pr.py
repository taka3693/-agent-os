#!/usr/bin/env python3
"""
Reject PR - PR却下

責務:
- 承認待ち状態を読み込み
- 却下状態を記録
- 却下結果を返す
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


def update_state(state: Dict[str, Any]) -> None:
    """却下状態を更新"""
    state_file = Path(state.get("state_file", ""))
    if not state_file.exists():
        return
    
    state["status"] = "rejected"
    state["rejected_at"] = datetime.now().isoformat()
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def format_result(state: Dict[str, Any]) -> Dict[str, Any]:
    """却下結果を整形"""
    return {
        "ok": True,
        "status": "rejected",
        "pr_title": state.get("pr_title", ""),
        "branch": state.get("branch", ""),
        "risk_level": state.get("risk_level", "medium"),
        "state_file": state.get("state_file", ""),
        "rejected_at": state.get("rejected_at", ""),
        "message": "PRが却下されました"
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Reject PR")
    parser.add_argument("--state", required=True, help="State file path")
    args = parser.parse_args()
    
    # state読み込み
    state = load_state(args.state)
    if not state.get("ok", True):
        print(json.dumps({
            "ok": False,
            "error": state.get("error", "unknown_error"),
            "state_file": args.state
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    
    # 既にapproved/rejected/mergedの場合は警告
    current_status = state.get("status", "")
    if current_status in ["approved", "rejected", "merged"]:
        print(json.dumps({
            "ok": False,
            "error": f"already_{current_status}",
            "current_status": current_status,
            "state_file": args.state,
            "message": f"既に{current_status}状態です"
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    
    # 却下状態を更新
    update_state(state)
    
    # 結果を出力
    result = format_result(state)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
AgentOS Single Entrypoint
OpenClawからの最小接続用エントリーポイント

責務:
- リクエスト受付
- 適切な内部処理への振り分け
- 結果の要約
"""
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any

# agentOSルートディレクトリ
ROOT = Path(__file__).resolve().parents[1]

def decision_cycle(request: str, cycles: int = 2) -> Dict[str, Any]:
    """
    decision → execution → evaluation → feedback ループを実行
    
    Args:
        request: ユーザーリクエスト
        cycles: ループ回数
    
    Returns:
        要約結果
    """
    script_path = ROOT / "tools" / "decision_cycle.sh"
    
    if not script_path.exists():
        return {
            "ok": False,
            "error": "decision_cycle_not_found",
            "path": str(script_path)
        }
    
    # decision_cycle.shを実行
    try:
        result = subprocess.run(
            ["bash", str(script_path), request, str(cycles)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(ROOT)
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": "decision_cycle_timeout"
        }
    except Exception as e:
        return {
            "ok": False,
            "error": "decision_cycle_error",
            "detail": str(e)
        }
    
    if result.returncode != 0:
        return {
            "ok": False,
            "error": "decision_cycle_failed",
            "detail": result.stderr[-500:] if result.stderr else "Unknown error"
        }
    
    # 結果をパースして要約
    lines = result.stdout.strip().split('\n')
    
    # 最終推奨を抽出
    final_recommendation = None
    for line in reversed(lines):
        if '"option"' in line and '"score"' in line:
            try:
                # JSONとしてパース試行
                if line.strip().startswith('{'):
                    final_recommendation = json.loads(line)
                break
            except:
                pass
    
    # weights変化を抽出
    weights_history = []
    for line in lines:
        if 'Weights:' in line:
            weights_history.append(line)
    
    # feedbackを抽出
    feedback_history = []
    for line in lines:
        if 'success_rate' in line and 'Feedback:' in line:
            try:
                feedback_str = line.split('Feedback:')[1].strip()
                feedback_history.append(json.loads(feedback_str))
            except:
                pass
    
    return {
        "ok": True,
        "recommendation": final_recommendation,
        "weights_history": weights_history,
        "feedback_history": feedback_history,
        "cycles_executed": cycles
    }

def main():
    """メインエントリーポイント"""
    if len(sys.argv) < 2:
        print(json.dumps({
            "ok": False,
            "error": "missing_action",
            "usage": "entrypoint.py <action> [args...]",
            "available_actions": ["decision_cycle", "health"]
        }, ensure_ascii=False))
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == "decision_cycle":
        if len(sys.argv) < 3:
            print(json.dumps({
                "ok": False,
                "error": "missing_request"
            }, ensure_ascii=False))
            sys.exit(1)
        
        request = sys.argv[2]
        if len(sys.argv) > 3:
            try:
                cycles = int(sys.argv[3])
                if cycles <= 0:
                    raise ValueError("cycles must be > 0")
                if cycles > 10:
                    raise ValueError("cycles too large")
            except ValueError:
                print(json.dumps({
                    "ok": False,
                    "error": "invalid_cycles",
                    "detail": f"cycles must be integer between 1 and 10, got: {sys.argv[3]}"
                }, ensure_ascii=False))
                sys.exit(1)
        else:
            cycles = 2
        result = decision_cycle(request, cycles)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    elif action == "health":
        print(json.dumps({
            "ok": True,
            "status": "healthy",
            "version": "1.0.0",
            "agentos_root": str(ROOT)
        }, ensure_ascii=False))
    
    else:
        print(json.dumps({
            "ok": False,
            "error": f"unknown_action: {action}",
            "available_actions": ["decision_cycle", "health"]
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()

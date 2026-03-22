import json
import sys

# action_type別の重み付け
# plan/acknowledged: 計画段階なので0.5
# 実action（write, session.archive等）: 1.0
ACTION_WEIGHTS = {
    "plan": 0.5,
    "acknowledged": 0.5,
    "write": 1.0,
    "session.archive": 1.0,
    "test.transient_fail": 1.0,
}

def evaluate(results):
    weighted_success = 0.0
    real_action_count = 0
    
    for r in results:
        action_type = r.get("action_type", "plan")
        weight = ACTION_WEIGHTS.get(action_type, 0.5)  # 未知は0.5
        
        # status == "done" を評価
        if r.get("status") == "done":
            weighted_success += weight
            if action_type not in ("plan", "acknowledged"):
                real_action_count += 1
        # フォールバック: output文字列チェック
        elif r.get("output") and "executed" in str(r.get("output")):
            weighted_success += weight

    total = len(results)
    # 重み付き成功率（0.0-1.0）
    max_possible = total * 1.0  # 全て実action成功の場合
    score = weighted_success / max_possible if max_possible else 0
    
    # 実action成功率（実actionのみ）
    real_action_total = sum(1 for r in results if r.get("action_type") not in ("plan", "acknowledged"))
    real_action_success_rate = real_action_count / real_action_total if real_action_total > 0 else 1.0

    return {
        "success_rate": round(score, 2),
        "weighted_success": round(weighted_success, 2),
        "completed": int(weighted_success),
        "total": total,
        "real_action_count": real_action_count,
        "real_action_total": real_action_total,
        "real_action_success_rate": round(real_action_success_rate, 2),
        "plan_count": sum(1 for r in results if r.get("action_type") in ("plan", "acknowledged")),
    }

if __name__ == "__main__":
    data = json.loads(sys.stdin.read())
    print(json.dumps(evaluate(data), ensure_ascii=False, indent=2))

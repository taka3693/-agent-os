#!/bin/bash
# decision_cycle.sh - decision → execution → evaluation → feedback付きdecision
# 最小ループを1コマンドで実行

set -e
cd "$(dirname "$0")/.."

REQUEST="${1:-月額モデルとコンサルならどっちがいい？}"
CYCLES="${2:-2}"

echo "=== Decision Cycle ==="
echo "Request: $REQUEST"
echo "Cycles: $CYCLES"
echo ""

FEEDBACK=""
LAST_DECISION=""

for i in $(seq 1 "$CYCLES"); do
    echo "--- Cycle $i ---"
    
    # Decision (with feedback if available)
    if [ -z "$FEEDBACK" ]; then
        echo "[DECISION] Initial run (no feedback)"
        LAST_DECISION=$(python3 tools/run_decision.py --request "$REQUEST")
    else
        echo "[DECISION] With feedback: $FEEDBACK"
        LAST_DECISION=$(echo "$FEEDBACK" | python3 tools/run_decision.py --request "$REQUEST")
    fi
    
    # Show recommendation
    echo "$LAST_DECISION" | python3 -c "import sys,json; d=json.load(sys.stdin); r=d['task_result']['recommendation']; w=d['task_result']['weights']; print(f\"Recommendation: {r}\"); print(f\"Weights: speed={w['speed']:.2f}, predictability={w['predictability']:.2f}, scalability={w['scalability']:.2f}\")"
    
    # Execution (adapter経由でexecutor呼び出し)
    echo "[EXECUTION] Running tasks..."
    EXEC_RESULT=$(echo "$LAST_DECISION" | python3 tools/run_execution_adapter.py 2>/dev/null)
    
    # Evaluation
    echo "[EVALUATION] Evaluating results..."
    FEEDBACK=$(echo "$EXEC_RESULT" | python3 tools/evaluate_execution.py)
    
    echo "Feedback: $FEEDBACK"
    echo ""
done

echo "=== Final Result ==="
echo "$LAST_DECISION" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['task_result']['recommendation'], ensure_ascii=False, indent=2))"

#!/usr/bin/env python3
import subprocess
import json

def test_decision_task():
    payload = {
        "text": "aos decision: 次のアクションを決めたい",
        "source": "telegram",
        "chain_count": 0,
        "allowed_skills": ["decision"]
    }

    # サブプロセスで decision タスクを実行
    result = subprocess.run(
        ["python3", "/home/milky/agent-os/bridge/route_to_task.py"],
        input=json.dumps(payload),
        text=True,
        capture_output=True
    )

    assert result.returncode == 0, "Decision task failed"
    task_response = json.loads(result.stdout)
    assert task_response.get("ok") is True, "Error in task response"

    # モデルと skill が選ばれているか確認
    assert task_response.get("selected_skill") == "decision", "Selected skill is incorrect"
    assert task_response.get("model") == "anthropic/claude-sonnet-4-6", "Model is not correctly assigned"

    print("Decision task test passed!")

if __name__ == "__main__":
    test_decision_task()

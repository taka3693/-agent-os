import json
import sys

def run(tasks):
    results = []

    for t in tasks:
        task = t["task"]
        print(f"[EXEC] {task}", file=sys.stderr)

        status = "done"
        output = f"executed:{task}"

        # 擬似失敗条件
        if "集客" in task:
            status = "failed"
            output = f"failed:{task}"

        results.append({
            "task": task,
            "status": status,
            "output": output
        })

    return results

if __name__ == "__main__":
    data = json.loads(sys.stdin.read())

    tasks = data.get("execution_tasks")
    if not tasks and "task_result" in data:
        tasks = data["task_result"].get("execution_tasks", [])

    result = run(tasks or [])
    print(json.dumps(result, ensure_ascii=False, indent=2))

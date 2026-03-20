
import json
import sys
from skills.decision.generate_decision import generate_decision

def main():
    inputs = [
        "サブスクか買い切りどっちがいい？",
        "短期で稼ぐなら？",
        "安定収益なら？"
    ]

    results = []
    for req in inputs:
        res = generate_decision(req, context=req)
        results.append({
            "request": req,
            "result": res
        })

    print(json.dumps(results, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

import sys, json

data = json.load(sys.stdin)
r = data["task_result"]

def j(v, d=""):
    return v if v is not None else d

best = r["recommendation"]["option"]
conf = r["recommendation"]["confidence"]
preset = r.get("preset", "default")

lines = []
lines.append("# 意思決定提案書")
lines.append("")
lines.append("## 1. 結論")
lines.append(f"- 推奨案: {best}")
lines.append(f"- 判断モード: {preset}")
lines.append(f"- 確信度: {conf}")
lines.append(f"- 要約: {j(r.get('summary'))}")
lines.append("")
lines.append("## 2. 背景と目的")
lines.append(j(r.get("goal")))
lines.append("")
lines.append("## 3. 比較対象")
for o in r["options"]:
    lines.append(f"- {o}")
lines.append("")
lines.append("## 4. 評価軸")
for c in r["criteria"]:
    lines.append(f"- {c}（重み {r['weights'].get(c, 1)}）")
lines.append("")
lines.append("## 5. 評価結果")
for s in r["scores"]:
    lines.append(f"### {s['option']}")
    lines.append(f"- 総合点: {s['total']}")
    for k in r["criteria"]:
        base = s["breakdown"][k]
        w = r["weights"].get(k, 1)
        weighted = s["weighted_breakdown"][k]
        lines.append(f"  - {k}: {base} × {w} = {weighted}")
    lines.append("")
lines.append("## 6. 採用理由")
lines.append(j(r.get("reasoning")))
lines.append("")
lines.append("## 7. 非採用理由")
for x in r["rejected"]:
    lines.append(f"- {x['option']}: {x['reason']}")
lines.append("")
lines.append("## 8. 推奨アクション")
for i, a in enumerate(r["next_actions"], 1):
    lines.append(f"{i}. {a}")

print("\n".join(lines))

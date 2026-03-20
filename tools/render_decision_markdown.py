import sys, json

data = json.load(sys.stdin)
r = data["task_result"]

lines = []
lines.append("# 意思決定レポート")
lines.append("")
lines.append("## 要約")
lines.append(r.get("summary", ""))
lines.append("")
lines.append("## 目的")
lines.append(r["goal"])
lines.append("")
lines.append("## 推奨案")
lines.append(f"- 推奨: {r['recommendation']['option']}")
lines.append(f"- preset: {r.get('preset', 'default')}")
lines.append(f"- 確信度: {r['recommendation']['confidence']}")
lines.append("")
lines.append("## 候補")
for o in r["options"]:
    lines.append(f"- {o}")
lines.append("")
lines.append("## 比較軸と重み")
for c in r["criteria"]:
    lines.append(f"- {c}: {r['weights'].get(c, 1)}")
lines.append("")
lines.append("## スコア")
for s in r["scores"]:
    lines.append(f"### {s['option']}")
    lines.append(f"- weighted total: {s['total']}")
    for k, v in s["breakdown"].items():
        w = r["weights"].get(k, 1)
        lines.append(f"  - {k}: {v} × {w} = {s['weighted_breakdown'][k]}")
    lines.append("")
lines.append("## 採用理由")
lines.append(r["reasoning"])
lines.append("")
lines.append("## 却下理由")
for x in r["rejected"]:
    lines.append(f"- {x['option']}: {x['reason']}")
lines.append("")
lines.append("## 次の行動")
for a in r["next_actions"]:
    lines.append(f"- {a}")

print("\n".join(lines))

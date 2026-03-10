#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path

R = Path("/home/milky/agent-os")

def run_json(cmd, payload=None):
    p = subprocess.run(
        cmd,
        input=(json.dumps(payload, ensure_ascii=False) if payload is not None else None),
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip())
    out = (p.stdout or "").strip()
    if not out:
        raise RuntimeError("empty stdout")
    return json.loads(out)

text = sys.argv[1]
chat = sys.argv[2] if len(sys.argv) > 2 else ""

bridge_payload = {
    "text": text,
    "source": "telegram",
    "chain_count": 0,
    "allowed_skills": None,
    "chat_id": chat,
}

b = run_json(["python3", str(R / "bridge/route_to_task.py")], bridge_payload)

if not b.get("ok"):
    print(b.get("reply") or b.get("error") or "bridge failed")
    raise SystemExit

if b.get("selected_skill") != "research":
    print(b.get("reply") or "unsupported skill")
    raise SystemExit

run_json(["python3", str(R / "runner/run_research_task.py"), b["task_path"]])
t = json.loads(Path(b["task_path"]).read_text(encoding="utf-8"))
print(((((t.get("result") or {}).get("summary")) or b.get("reply") or f'research completed (task: {b["task_id"]})')).strip())

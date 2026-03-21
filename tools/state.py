import json
from pathlib import Path

def read_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    with p.open() as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except:
                pass
    return rows

def append_jsonl(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(obj) + "\n")

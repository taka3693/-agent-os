import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_strict_flag_exits_nonzero_on_hard_block():
    code = """
import json
from tools.pr_gate import decide_merge_recommendation
merge = decide_merge_recommendation("high", ["tools/approve_pr.py"])
print(json.dumps({"merge_recommendation": merge}))
raise SystemExit(1 if merge == "hard_block" else 0)
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    data = json.loads(proc.stdout.strip())
    assert data["merge_recommendation"] == "hard_block"

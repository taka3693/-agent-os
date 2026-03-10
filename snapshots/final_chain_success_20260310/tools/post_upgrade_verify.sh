#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/milky/agent-os"
UNIT="openclaw-gateway.service"

echo "== openclaw version =="
openclaw --version || true

echo
echo "== patch verify =="
python3 "$ROOT/tools/verify_agent_os_patch.py"

echo
echo "== service status =="
systemctl --user --no-pager --full status "$UNIT" || true

echo
echo "== mismatch check =="
journalctl --user -u "$UNIT" --since "10 min ago" --no-pager | grep -i 'newer OpenClaw' || echo 'no mismatch warning'

echo
echo "== local success-path test =="
python3 "$ROOT/tools/test_agent_os_pipeline.py"

echo
echo "== route parser test =="
python3 "$ROOT/tools/test_route_parser.py"

echo
echo "== model routing test =="
python3 "$ROOT/tools/test_model_routing.py"

echo
echo "== local failure-path test =="
python3 "$ROOT/tools/test_runner_failure_path.py"

echo
echo "== latest tasks =="
python3 - <<'PY'
import json, glob
paths = sorted(glob.glob('/home/milky/agent-os/state/tasks/task-*.json'))[-5:]
for p in paths:
    try:
        d = json.load(open(p))
        print(json.dumps({
            "task": p,
            "status": d.get("status"),
            "selected_skill": d.get("selected_skill"),
            "summary": ((d.get("result") or {}).get("summary")),
            "error": d.get("error")
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"task": p, "read_error": str(e)}, ensure_ascii=False))
PY

echo
echo "DONE"

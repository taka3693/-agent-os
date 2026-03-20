#!/usr/bin/env bash
set -euo pipefail

fuser -k 8000/tcp 2>/dev/null || true

cd /home/milky/agent-os
source .venv/bin/activate
exec uvicorn tools.decision_api:app --host 0.0.0.0 --port 8000

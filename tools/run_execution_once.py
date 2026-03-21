#!/usr/bin/env python3
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.run_execution_worker import run_execution_worker
print(json.dumps(run_execution_worker(), ensure_ascii=False, indent=2))

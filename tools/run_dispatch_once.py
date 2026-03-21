#!/usr/bin/env python3
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runner.dispatch_approved_actions import dispatch_approved_actions
print(json.dumps(dispatch_approved_actions(), ensure_ascii=False, indent=2))

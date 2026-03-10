#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

cmd = [
    sys.executable,
    str(ROOT / "tools" / "run_agent_os_request.py"),
    'aos json {"validate_only":true,"steps":[{"id":"scan","command":"aos ls workspace"},{"id":"danger","command":"aos rm x","continue_on_error":true},{"id":"read","command":"aos read notes/todo.md"}]}',
]

cp = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)

print("=== returncode ===")
print(cp.returncode)
print("=== stdout ===")
print(cp.stdout)
if cp.stderr:
    print("=== stderr ===")
    print(cp.stderr)

# validated_with_errors は ok=false なので rc=1 でも正常系
assert cp.returncode in (0, 1), f"unexpected rc={cp.returncode}"

stdout = cp.stdout.strip()
assert stdout, "stdout is empty"

try:
    obj = json.loads(stdout)
except json.JSONDecodeError as e:
    raise SystemExit(f"NG: stdout is not valid JSON: {e}")

reply_text = obj.get("reply_text")
telegram_reply_text = obj.get("telegram_reply_text")

assert isinstance(reply_text, str) and reply_text, "reply_text missing"
assert isinstance(telegram_reply_text, str) and telegram_reply_text, "telegram_reply_text missing"

# CLI は詳細文を維持
assert "json 検証完了" in reply_text or "json 実行完了" in reply_text or "json 実行失敗" in reply_text, \
    "CLI reply_text should remain detailed"
assert "最初の失敗:" in reply_text, "CLI reply_text should include detailed failure section"
assert "---" in reply_text, "CLI reply_text should include per-step detail sections"

# Telegram は短縮 summary
assert telegram_reply_text.startswith("検証: NGあり"), "telegram summary must start with compact validation summary"
assert "最初の失敗(1始まり): step=danger / step#2 / 種別=ポリシー / 理由=削除コマンドは未対応" in telegram_reply_text
assert "補足: NG後も継続" in telegram_reply_text

# CLI 詳細と Telegram 要約は分離されていること
assert reply_text != telegram_reply_text, "CLI detail and Telegram summary must be split"

# JSON 本体にも期待値が残っていること
assert obj.get("status") == "validated_with_errors", "unexpected status"
assert obj.get("validate_only") is True, "validate_only should be true"
assert obj.get("ok") is False, "validated_with_errors batch should have ok=false"

print("PASS: Step71 CLI vs Telegram split OK")

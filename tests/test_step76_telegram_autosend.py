#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ = ROOT / "tools" / "run_agent_os_request.py"
spec = importlib.util.spec_from_file_location("run_agent_os_request", str(REQ))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

sent = {}

def fake_send_telegram_message(chat_id, text):
    sent["chat_id"] = str(chat_id)
    sent["text"] = text
    return {"ok": True, "chat_id": str(chat_id), "text": text}

mod.send_telegram_message = fake_send_telegram_message

out = mod.run_router_command("aos router 比較して整理したい", chat_id="6474742983")

assert out["ok"] is True
assert out["mode"] == "router"
assert out["status"] == "completed"
assert isinstance(out.get("telegram_send"), dict)
assert out["telegram_send"]["ok"] is True
assert sent["chat_id"] == "6474742983"
assert sent["text"] == out["telegram_reply_text"]
assert sent["text"].startswith("router 受付完了")

print("PASS: Step76 telegram autosend OK")

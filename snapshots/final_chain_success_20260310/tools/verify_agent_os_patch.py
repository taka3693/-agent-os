#!/usr/bin/env python3
import json, re, subprocess
from pathlib import Path

DIST = Path.home() / ".npm-global/lib/node_modules/openclaw/dist"
A1 = 'const processInboundMessage = async (params) => {'
A2 = 'const isCommandLike = (text ?? "").trim().startsWith("/");'
B = "/* AGENT_OS_HOOK_BEGIN */"
E = "/* AGENT_OS_HOOK_END */"

def find_bundles():
    xs = []
    for p in sorted(DIST.glob("reply-*.js")):
        try:
            s = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if A1 in s and A2 in s:
            xs.append(p)
    return xs

def check(p):
    r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
    return r.returncode == 0, ((r.stderr or "").strip() or (r.stdout or "").strip())

xs = find_bundles()
if len(xs) != 1:
    print(json.dumps({"ok": False, "error": "candidate bundle count != 1", "candidates": [str(x) for x in xs]}, ensure_ascii=False, indent=2))
    raise SystemExit(1)

bundle = xs[0]
s = bundle.read_text(encoding="utf-8")
ok_syntax, msg = check(bundle)

m = re.search(re.escape(B) + r"(.*?)" + re.escape(E), s, re.DOTALL)
hook = m.group(1) if m else ""

checks = {
    "hook_begin_count": s.count(B),
    "hook_end_count": s.count(E),
    "hook_found": bool(m),
    "prefix_guard_present": '/^(aos:|task:)/i.test(text.trim())' in hook,
    "entry_present": 'telegram_agent_os_entry.py' in hook,
    "spawn_sync_present": 'require("node:child_process").spawnSync(' in hook,
    "send_message_telegram_present": 'await sendMessageTelegram(String(chatId), __reply, {' in hook,
    "resolve_token_present": 'token: resolveTelegramToken(cfg, { accountId }).token' in hook,
    "thread_id_present": 'messageThreadId: resolvedThreadId ?? void 0' in hook,
    "ctx_api_absent_in_hook": 'ctx.api.sendMessage' not in hook,
    "ctx_reply_absent_in_hook": 'ctx.reply(' not in hook,
    "syntax_check": ok_syntax,
}

ok = (
    checks["hook_begin_count"] == 1 and
    checks["hook_end_count"] == 1 and
    checks["hook_found"] and
    checks["prefix_guard_present"] and
    checks["entry_present"] and
    checks["spawn_sync_present"] and
    checks["send_message_telegram_present"] and
    checks["resolve_token_present"] and
    checks["thread_id_present"] and
    checks["ctx_api_absent_in_hook"] and
    checks["ctx_reply_absent_in_hook"] and
    checks["syntax_check"]
)

out = {"ok": ok, "bundle": str(bundle), **checks, "syntax_message": msg}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if ok else 1)

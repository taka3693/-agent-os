#!/usr/bin/env python3
import json, os, re, shutil, subprocess, tempfile
from datetime import datetime
from pathlib import Path

DIST = Path.home() / ".npm-global/lib/node_modules/openclaw/dist"
A1 = 'const processInboundMessage = async (params) => {'
A2 = 'const isCommandLike = (text ?? "").trim().startsWith("/");'
B = "/* AGENT_OS_HOOK_BEGIN */"
E = "/* AGENT_OS_HOOK_END */"

def out(ok, **kw):
    print(json.dumps({"ok": ok, **kw}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 1)

def find_bundle():
    xs = []
    for p in sorted(DIST.glob("reply-*.js")):
        try:
            s = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if A1 in s and A2 in s:
            xs.append(p)
    if len(xs) != 1:
        out(False, error="candidate bundle count != 1", candidates=[str(x) for x in xs])
    return xs[0]

def check(p):
    r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
    return r.returncode == 0, ((r.stderr or "").strip() or (r.stdout or "").strip())

def write_atomic(path, content):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent)) as f:
        f.write(content)
        tmp = Path(f.name)
    os.replace(tmp, path)

bundle = find_bundle()
s = bundle.read_text(encoding="utf-8")

if B not in s and E not in s:
    ok, msg = check(bundle)
    out(ok, bundle=str(bundle), changed=False, syntax_check=ok, syntax_message=msg, note="hook not present")

pat = re.compile(r'\n?/\* AGENT_OS_HOOK_BEGIN \*/.*?/\* AGENT_OS_HOOK_END \*/\n?', re.DOTALL)
new_s, n = pat.subn("\n", s, count=1)
if n != 1:
    out(False, error="failed to remove hook block cleanly", bundle=str(bundle))

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = bundle.with_name(f"{bundle.name}.bak.agent_os_revert.{ts}")
shutil.copy2(bundle, bak)
write_atomic(bundle, new_s)

ok, msg = check(bundle)
if not ok:
    shutil.copy2(bak, bundle)
    out(False, error="syntax check failed; restored backup", bundle=str(bundle), backup=str(bak), syntax_message=msg)

out(True, bundle=str(bundle), changed=True, backup=str(bak), syntax_check=ok, syntax_message=msg)

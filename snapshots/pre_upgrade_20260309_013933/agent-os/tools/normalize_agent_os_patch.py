#!/usr/bin/env python3
from pathlib import Path
import re

p = Path.home() / ".npm-global/lib/node_modules/openclaw/dist/reply-DhtejUNZ.js"
s = p.read_text()

if "AGENT_OS_PATCH_BEGIN" in s or "AGENT_OS_PATCH_END" in s:
    print("already normalized:", p)
    raise SystemExit(0)

start_pat = re.compile(
    r'^[ \t]*const ROUTE_BRIDGE_PATH = "/home/milky/agent-os/bridge/route_to_task\.py";\n',
    re.M,
)
end_pat = re.compile(
    r'^[ \t]*const isCommandLike = \(text \?\? ""\)\.trim\(\)\.startsWith\("/"\);\n',
    re.M,
)

m1 = start_pat.search(s)
if not m1:
    raise SystemExit("start anchor not found")

m2 = end_pat.search(s, m1.start())
if not m2:
    raise SystemExit("end anchor not found")

block = s[m1.start():m2.start()]

wrapped = (
    (' ' * 8) + '// AGENT_OS_PATCH_BEGIN\n'
    + block
    + (' ' * 8) + '// AGENT_OS_PATCH_END\n'
)

s2 = s[:m1.start()] + wrapped + s[m2.start():]
p.write_text(s2)
print("normalized with markers:", p)

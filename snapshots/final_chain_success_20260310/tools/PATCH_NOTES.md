# Agent-OS Patch Notes

## Purpose
Stabilize Telegram -> OpenClaw -> Agent-OS Router -> Research Runner -> Telegram reply flow.

## Live Patch Target
~/.npm-global/lib/node_modules/openclaw/dist/reply-DhtejUNZ.js

## Patch Markers
AGENT_OS_PATCH_BEGIN
AGENT_OS_PATCH_END

## External Patch Block
/home/milky/agent-os/tools/agent_os_patch_block.js.txt

## Management Scripts
verify_agent_os_patch.py
apply_agent_os_patch.py
revert_agent_os_patch.py

## Standard Recovery Flow
python3 verify_agent_os_patch.py
python3 revert_agent_os_patch.py
python3 apply_agent_os_patch.py
python3 verify_agent_os_patch.py
systemctl --user restart openclaw-gateway

## Debug Toggle
Enable debug:
mkdir -p ~/.config/systemd/user/openclaw-gateway.service.d
cat > ~/.config/systemd/user/openclaw-gateway.service.d/10-agent-os-debug.conf <<'EOF'
[Service]
Environment=AGENT_OS_DEBUG=1
EOF
systemctl --user daemon-reload
systemctl --user restart openclaw-gateway

Disable debug:
rm -f ~/.config/systemd/user/openclaw-gateway.service.d/10-agent-os-debug.conf
systemctl --user daemon-reload
systemctl --user restart openclaw-gateway

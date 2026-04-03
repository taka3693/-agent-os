#!/bin/bash
# セッション監視 - 1時間ごとに実行

cd ~/agent-os
python3 tools/session_monitor.py >> /tmp/session_monitor.log 2>&1

# ログローテーション（1000行以上で切り詰め）
if [ $(wc -l < /tmp/session_monitor.log 2>/dev/null || echo 0) -gt 1000 ]; then
    tail -500 /tmp/session_monitor.log > /tmp/session_monitor.log.tmp
    mv /tmp/session_monitor.log.tmp /tmp/session_monitor.log
fi

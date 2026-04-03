#!/bin/bash
# 時間帯に応じてProactiveサイクルを実行
# 日中(9-21時): 15分ごと、夜間: 1時間ごと

HOUR=$(date +%H)
MINUTE=$(date +%M)

# 日中（9:00-20:59）
if [ "$HOUR" -ge 9 ] && [ "$HOUR" -lt 21 ]; then
    # 15分ごと（0,15,30,45分）に実行
    if [ "$((MINUTE % 15))" -eq 0 ]; then
        /usr/bin/python3 /home/milky/agent-os/tools/proactive_cli.py run
        # MISOアラートチェック
        /usr/bin/python3 /home/milky/agent-os/miso/alert_checker.py --chat-id 6474742983 --threshold 30
        # コンテキスト監視
        /usr/bin/python3 /home/milky/agent-os/miso/context_manager.py check --session-id main --chat-id 6474742983
    fi
else
    # 夜間: 正時（0分）のみ実行
    if [ "$MINUTE" -eq 0 ]; then
        /usr/bin/python3 /home/milky/agent-os/tools/proactive_cli.py run
        # MISOアラートチェック（夜間は1時間ごと）
        /usr/bin/python3 /home/milky/agent-os/miso/alert_checker.py --chat-id 6474742983 --threshold 60
        # コンテキスト監視（夜間は1時間ごと）
        /usr/bin/python3 /home/milky/agent-os/miso/context_manager.py check --session-id main --chat-id 6474742983
    fi
fi

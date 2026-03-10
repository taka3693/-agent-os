# Telegram Research Patch Playbook (Agent-OS 最小構成)

## 目的
OpenClaw `dist` 更新で Telegram research 連携が消えた場合に、
最小フローを短時間で復旧する。

---

## Agent-OS 側ファイル

/home/milky/agent-os/router/router.py  
/home/milky/agent-os/bridge/route_to_task.py  
/home/milky/agent-os/runner/run_research_task.py  
/home/milky/agent-os/state/tasks/*.json  

---

## OpenClaw 側パッチ対象

/home/milky/.npm-global/lib/node_modules/openclaw/dist/subagent-registry-CkqrXKq4.js

---

## パッチ挿入位置

検索キー

bot.on("message", async (ctx) =>

---

## Telegram処理フロー

Telegram  
→ Router  
→ task queued 保存  
→ research runner 実行  

成功

research completed: <summary> (task: <task_id>)

失敗

research failed: <task_id>

---

## task status

queued  
running  
completed  

queued  
running  
failed  

---

## バックアップ

cp /home/milky/.npm-global/lib/node_modules/openclaw/dist/subagent-registry-CkqrXKq4.js \
/home/milky/.npm-global/lib/node_modules/openclaw/dist/subagent-registry-CkqrXKq4.js.bak.$(date +%Y%m%d-%H%M%S)

---

## 構文確認

node --check /home/milky/.npm-global/lib/node_modules/openclaw/dist/subagent-registry-CkqrXKq4.js

---

## gateway再起動

openclaw gateway restart

---

## 動作確認

Telegram送信

比較して整理したい

期待返信

research completed: <summary> (task: task-YYYYMMDD-XXX)

---

## task確認

ls -lt /home/milky/agent-os/state/tasks | head

cat /home/milky/agent-os/state/tasks/task-YYYYMMDD-XXX.json


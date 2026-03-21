# AgentOS Task Lifecycle Status

**Last Updated:** 2026-03-18

## Summary

Task lifecycle for research/decision/critique/retrospective skills is unified and operational.

## Important Rules

1. **初期task生成は `router/task_factory.py` 経由を必須とする**
   - `create_skill_task()` または `create_followup_task()` を使用
   - 手組み dict は禁止

2. **保存順序リスクは「低減」であり「解消」ではない**
   - child作成とparent更新を同一関数内に集約したが、真の原子性はない
   - クラッシュ時の孤立child可能性は低減したが排除ではない

## Components

| Component | Purpose |
|-----------|---------|
| `router/model_policy.py` | skill → role → model resolution |
| `router/task_factory.py` | unified task creation (必須) |
| `runner/run_research_task.py` | task execution with follow-up chaining |

## Known Issues

1. **初期task生成入口が不明確** - 外部から最初のtaskを投入する際、task_factory経由を必須ルールとする
2. **Execution tasks use separate schema** - `bridge/route_to_task.py` は別系統（今回対象外）
3. **真の原子性なし** - 保存順序リスクは低減したが排除ではない

## Safe to Use

- Follow-up task chaining (execution → critique → retrospective)
- Model resolution (follows OpenClaw roles automatically)
- Task factory-based task creation

## Requires Attention

- **Initial task creation**: `router/task_factory.create_skill_task()` を使用すること
- **Execution tasks**: Use `bridge/route_to_task.py` (separate system)
- **After crash**: Orphaned children may exist but can be recovered via idempotency check on re-run

## Task Schema (research系)

```json
{
  "task_id": "task-...",
  "created_at": "ISO timestamp",
  "updated_at": "ISO timestamp",
  "selected_skill": "research|decision|critique|retrospective",
  "input_text": "query text",
  "run_input": {"query": "query text"},
  "status": "queued|running|completed|failed",
  "chain_count": 0,
  "model": "resolved via model_policy",
  "parent_task_id": null or parent task_id,
  "source": "agent_os",
  "result": null,
  "error": null
}
```

## Tests

```bash
python3 tools/test_model_policy.py      # Model resolution
python3 tools/test_task_factory.py      # Task factory
python3 tools/test_task_idempotency.py  # Follow-up idempotency
```

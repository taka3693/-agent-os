# Agent-OS

AGI指向の自律エージェントフレームワーク。意思決定、実行、自己改善のサイクルを統合管理します。

## アーキテクチャ
```
┌─────────────────────────────────────────────────────────────┐
│                        Agent-OS                              │
├─────────────────────────────────────────────────────────────┤
│  Skills Layer                                                │
│  ┌──────────┬──────────┬───────────┬──────────┬───────────┐ │
│  │ Research │ Decision │ Execution │ Critique │Retrospect │ │
│  └──────────┴──────────┴───────────┴──────────┴───────────┘ │
├─────────────────────────────────────────────────────────────┤
│  Runner Layer                                                │
│  • Orchestrator (Coordinator/Worker pattern)                 │
│  • Parallel Executor, Task Scheduler, Recovery               │
│  • Budget Control (subtasks, duration, retries)              │
├─────────────────────────────────────────────────────────────┤
│  Ops Layer                                                   │
│  • Approval Workflow (Human-in-the-Loop)                     │
│  • Health Monitoring, Cooldown Policy                        │
├─────────────────────────────────────────────────────────────┤
│  Integrations                                                │
│  • Bridge: Telegram, MISO                                    │
│  • ClawHub, Obsidian                                         │
└─────────────────────────────────────────────────────────────┘
```

## セットアップ
```bash
git clone https://github.com/taka3693/agent-os.git
cd agent-os
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## モデル構成

| Role | Model |
|------|-------|
| Main | zai/glm-5 |
| Main Fallback | openrouter/moonshotai/kimi-k2.5 |
| Subagents | openrouter/moonshotai/kimi-k2.5 |
| Codex | openai-codex/gpt-5.4 |

## 主要コンポーネント

### Skills
- **research**: 調査・情報収集
- **decision**: 意思決定生成
- **execution**: 計画実行
- **critique**: 自己批判・評価
- **experiment**: 実験・検証
- **retrospective**: 振り返り・学習

### Runner
- **orchestrator.py**: Coordinator/Workerパターンによるタスク分解・統合
- **parallel_executor.py**: 並列実行エンジン
- **task_scheduler.py**: タスクスケジューリング
- **task_recovery.py**: 障害復旧

### Ops
- **approval_***: 承認ワークフロー
- **health_***: ヘルスモニタリング
- **cooldown_***: 実行間隔制御

## テスト
```bash
pytest tests/ -v
```

## 開発ワークフロー

1. `main` から feature branch を作成
2. 実装・テスト
3. `git push -u origin <branch>`
4. Pull Request → merge
5. `git checkout main && git pull`

## License

MIT

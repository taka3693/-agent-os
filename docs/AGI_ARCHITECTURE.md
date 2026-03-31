# Agent-OS AGI アーキテクチャ

## 概要

Agent-OSは自律的なAGIシステムを目指して設計されています。

**AGIスコア: 8.7/10**

## コア能力

| 能力 | スコア | モジュール |
|------|--------|-----------|
| 自律実行 | 9/10 | proactive_* |
| 学習・適応 | 8/10 | learning/* |
| 自己改善 | 7/10 | self_improve |
| 目標管理 | 8/10 | goal_* |
| メタ認知 | 8/10 | capability_model, self_assessor |
| マルチモーダル | 7/10 | multimodal_*, vision_* |
| 外部環境適応 | 8/10 | github_observer, environment_monitor |

## CLI一覧

| コマンド | 説明 |
|----------|------|
| `proactive_cli.py run` | 能動的タスク生成 |
| `learning_cli.py run` | 学習サイクル実行 |
| `self_improve_cli.py run` | 自己改善サイクル |
| `goal_cli.py create/list/show` | 目標管理 |
| `meta_cli.py capabilities/assess` | メタ認知 |
| `multimodal_cli.py analyze/suggest` | マルチモーダル |
| `external_cli.py status` | 外部環境監視 |

## Telegram連携
```
aos queue              → 承認キュー一覧
aos queue approve <id> → 承認して実行
aos queue reject <id>  → 拒否
```

## 定期実行

cronで自動実行:
- 日中(9-21時): 15分ごと
- 夜間: 1時間ごと
```bash
# cron設定
*/1 * * * * /home/milky/agent-os/tools/proactive_scheduler.sh
```

## データフロー
```
観察 → タスク生成 → メタ認知評価 → 承認キュー → 実行 → 学習 → ポリシー更新
```

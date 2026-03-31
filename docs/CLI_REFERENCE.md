# Agent-OS CLI リファレンス

## Proactive (能動的タスク生成)
```bash
python tools/proactive_cli.py run [--dry-run]  # サイクル実行
python tools/proactive_cli.py status           # 状態確認
python tools/proactive_cli.py observe          # 観察のみ
```

## Learning (学習)
```bash
python tools/learning_cli.py run [--dry-run]   # 学習サイクル
python tools/learning_cli.py status            # 状態
python tools/learning_cli.py patterns          # パターン表示
python tools/learning_cli.py policies          # ポリシー表示
```

## Self-Improvement (自己改善)
```bash
python tools/self_improve_cli.py run [--dry-run]  # 改善サイクル
python tools/self_improve_cli.py status           # 状態
python tools/self_improve_cli.py fixes            # 保留中の修正
```

## Goal (目標管理)
```bash
python tools/goal_cli.py create "タイトル" "説明" [--priority high]
python tools/goal_cli.py list [--active]
python tools/goal_cli.py show <goal_id>
python tools/goal_cli.py progress <goal_id> <percent>
python tools/goal_cli.py complete <goal_id>
python tools/goal_cli.py decompose <goal_id> [--auto]
python tools/goal_cli.py report
```

## Meta-Cognition (メタ認知)
```bash
python tools/meta_cli.py capabilities      # 能力一覧
python tools/meta_cli.py assess "タスク"   # タスク評価
python tools/meta_cli.py limitations       # 制限一覧
python tools/meta_cli.py report            # 自己認識レポート
```

## Multimodal (マルチモーダル)
```bash
python tools/multimodal_cli.py detect <path>           # ファイルタイプ検出
python tools/multimodal_cli.py analyze <image_path>    # 画像解析
python tools/multimodal_cli.py chart "title" '<json>'  # チャート生成
python tools/multimodal_cli.py suggest "description"   # ダイアグラム提案
```

## External (外部環境)
```bash
python tools/external_cli.py github         # GitHub状態
python tools/external_cli.py env            # 環境状態
python tools/external_cli.py events [--react]  # イベント収集
python tools/external_cli.py status         # 全体ステータス
```

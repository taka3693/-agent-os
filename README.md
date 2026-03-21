# agent-os

Agent-OS Decision System を開発するためのリポジトリです。

## Overview

現在の開発対象は Agent-OS Decision System です。
意思決定の生成、CLI、FastAPI `/decision`、approval workflow、execution controls、governance tooling を段階的に整備します。

## Setup

```bash
git clone https://github.com/taka3693/-agent-os.git
cd -agent-os
```

必要な依存関係や実行手順は、実装に合わせて今後追加します。

## Usage

現時点では、リポジトリの基盤整備とドキュメント整備を進めています。
実装が入ったら、CLI と API の利用例をここに追加します。

## Development Workflow

- `main` から新しい feature branch を切る
- 作業後は `git add` → `git commit` → `git push -u origin <branch>`
- GitHub で Pull Request を作成して merge する
- merge 後は `git checkout main && git pull` を実行する

## Status

現在は README などの基盤整備フェーズです。
今後、`generate_decision.py` パイプライン、CLI、FastAPI `/decision` などを順次追加します。

## Current Project Structure

現時点の最小構成は以下です。

```text
.
├── README.md
└── .git/
```

今後、Decision System の実装に合わせてファイルやディレクトリを追加します。

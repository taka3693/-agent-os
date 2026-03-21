# Guard必須実行アーキテクチャ

## 目的

Guardは、コード変更を伴う成功報告の**最終安全ゲート**である。
このドキュメントは、Guardが必須であることをアーキテクチャ要件として定義する。

---

## 現在の必須実行パス

```
リクエスト
    ↓
タスク実行
    ↓
結果生成 (result)
    ↓
enforce_guard()  ← 必須通過点
    ↓
成功 または guard_blocked
    ↓
最終返信
```

**実装箇所:** `tools/run_agent_os_request.py`

**Guard呼び出し位置:** 908行目

```python
result = enforce_guard(
    result,
    output=reply_text,
    changed_files=changed_py_files,
    diff_output=diff_output,
    is_small_change=is_small_change,
    pytest_info=pytest_info,
)
```

**重要:** すべての`return`文は`enforce_guard()`呼び出しの後にある。

---

## Guardの責任

Guardは以下のチェックを実行する：

| チェック | 内容 |
|---------|------|
| 危険な変更検出 | 関数/クラス/import削除、大量削除のブロック |
| pytest失敗ブロック | テスト失敗時の成功報告を防止 |
| 構文検証 | Pythonファイルの構文チェック |
| 重要ファイルポリシー | `execution/guard.py`, `tools/run_agent_os_request.py`への条件付きブロック |
| 差分サイズ保護 | 小規模変更モードでの厳格な行数制限 |

---

## 非Guard実行パス

以下のパスは**意図的にGuardを使用しない**（コードを変更しないため）：

| パス | 内容 | 理由 |
|-----|------|------|
| ルータークエリ | `aos router <query>` | 読み取り専用 |
| サービス管理 | `service.restart_openclaw_gateway` | Pythonコードを変更しない |
| ステータス確認 | `service.status_*`, `git.status_repo` | 読み取り専用 |
| セッションアーカイブ | `session.archive` | Pythonコードを変更しない |
| 設定読み取り | `config.read_openclaw_json` | 読み取り専用 |

**実装箇所:** `execution/executor.py` (ACTION_REGISTRY)

---

## アーキテクチャルール

> **コードを変更できる、またはコード変更の成功を報告できる実行パスは、必ず `enforce_guard()` を通過しなければならない。**

---

## コントリビュータールール

新しい実行パスを追加する場合：

1. **Guard通過を確認**
   - 成功報告前に`enforce_guard()`を呼び出す
   - または、コードを変更しない読み取り専用パスであることを確認

2. **テストで検証**
   ```bash
   make safety
   ```

3. **コミット前に確認**
   - `git diff`で変更内容を確認
   - Guard経路が維持されていることを確認

---

## クイック検証チェックリスト

開発者は以下を確認すること：

- [ ] `make safety` が通過する
- [ ] `enforce_guard()` がメインパスに残っている
- [ ] `git diff` で意図しない変更がない
- [ ] 新しいパスがコードを変更する場合、Guardを通過する

---

## 関連ドキュメント

- [safety_workflow.md](safety_workflow.md) - オペレーター向けワークフロー
- [guard_failure_codes.md](guard_failure_codes.md) - 失敗コード一覧

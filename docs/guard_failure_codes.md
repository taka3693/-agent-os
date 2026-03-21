# Guard失敗コード一覧

## 目的

Guardは、安全でない変更や未検証の変更が成功として報告されるのを防ぐために存在する。
このドキュメントは、Guard失敗コードの一覧と、各コードが発生した際のオペレーター対応を説明する。

---

## データ構造

| フィールド | 説明 |
|-----------|------|
| `guard_failed` | Guardが失敗した場合 `true` |
| `guard_failures` | 人間可読の失敗理由リスト（文字列） |
| `guard_failure_details` | 構造化された失敗詳細（code/messageのdictリスト） |
| `pytest_info["summary"]` | pytest失敗時の短い要約（利用可能な場合） |

---

## 失敗コード一覧

### コード参照表

| コード | 意味 | 典型的なトリガー | 推奨対応 |
|-------|------|-----------------|---------|
| `EDIT_FAILED` | 編集操作の失敗 | ファイル編集コマンドが失敗 | 編集内容とファイルパスを確認 |
| `SYNTAX_ERROR` | 構文エラー | 編集後にPython構文エラーが検出 | 編集結果の構文を確認・修正 |
| `VERIFICATION_MISSING` | 検証欠落 | 成果物が期待通りに作成されなかった | 実行結果と成果物を確認 |
| `PYTEST_FAILED` | pytest失敗 | テストが実行され失敗 | pytest出力と `pytest_info["summary"]` を確認 |
| `PYTEST_REQUIRED_BUT_NOT_EXECUTED` | pytest未実行 | pytestが必要だが実行されなかった | pytest環境と実行条件を確認 |
| `DANGEROUS_CHANGE` | 危険な変更 | 関数/クラス削除、import削除など | diffを確認、意図的な削除か検討 |
| `DIFF_TOO_LARGE` | 差分過大 | 変更行数が上限を超過 | 変更を小さく分割 |
| `CRITICAL_FILE_DANGEROUS_CHANGE` | 重要ファイルへの危険な変更 | `execution/guard.py`や`tools/run_agent_os_request.py`への危険な変更 | 慎重にレビュー、意図的か確認 |
| `CRITICAL_FILE_PYTEST_REQUIRED` | 重要ファイルにpytest必須 | 重要ファイル変更時にpytest未実行 | pytestを実行してから再試行 |

---

## 詳細説明

### EDIT_FAILED
ファイル編集操作が失敗した場合に発生。
- 編集対象ファイルが存在しない
- 編集内容が不正
- ファイル権限の問題

**対応:** 編集コマンドと対象ファイルを確認。

### SYNTAX_ERROR
編集後にPython構文チェックでエラーが検出された場合。
- 不完全なコードブロック
- 括弧やインデントの不整合

**対応:** 編集結果を確認し、構文を修正。

### VERIFICATION_MISSING
実行後に期待される成果物が見つからない場合。
- ファイルが作成されなかった
- 期待される出力が得られなかった

**対応:** 実行ログと期待される成果物を確認。

### PYTEST_FAILED
pytestが実行され、テストが失敗した場合。
- `pytest_info["summary"]` に短い失敗要約が含まれる
- テスト出力の詳細はpytestログを参照

**対応:** 失敗したテストを確認・修正。

### PYTEST_REQUIRED_BUT_NOT_EXECUTED
pytestの実行が必要だが、何らかの理由で実行されなかった場合。
- pytest環境の問題
- 実行条件の不備

**対応:** pytestが実行可能な状態か確認。

### DANGEROUS_CHANGE
コード削除や構造変更など、危険な変更が検出された場合。
- 関数の削除 (`def ...`)
- クラスの削除 (`class ...`)
- import文の削除
- 大量の連続削除（10行超）

**対応:** diffを確認し、削除が意図的か検討。

### DIFF_TOO_LARGE
変更の差分が大きすぎる場合。
- デフォルト上限: 500行
- 小規模変更として処理される場合: 50行

**対応:** 変更を複数の小さなコミットに分割。

### CRITICAL_FILE_DANGEROUS_CHANGE
重要ファイルへの危険な変更が検出された場合。

**重要ファイル:**
- `execution/guard.py` - Guardロジック本体
- `tools/run_agent_os_request.py` - 実行ランナー

**対応:** 慎重にレビュー。意図的な変更か確認。

### CRITICAL_FILE_PYTEST_REQUIRED
重要ファイルが変更されたが、pytestが実行されていない場合。
- 重要ファイルへの変更はpytest検証が必須

**対応:** pytestを実行してから再試行。

---

## オペレーター対応ガイド

### 最初に確認すること

1. **`guard_failure_details`** - 構造化された失敗理由
2. **`pytest_info["summary"]`** - pytest関連の場合、短い要約

### 再試行すべき場合

- `SYNTAX_ERROR` - 構文を修正して再試行
- `EDIT_FAILED` - 編集内容を修正して再試行
- `VERIFICATION_MISSING` - 実行内容を確認して再試行

### git diffを確認すべき場合

- `DANGEROUS_CHANGE` - 何が削除されたか確認
- `CRITICAL_FILE_DANGEROUS_CHANGE` - 重要ファイルへの変更内容を確認

### pytest出力を確認すべき場合

- `PYTEST_FAILED` - 失敗したテストの詳細を確認
- `CRITICAL_FILE_PYTEST_REQUIRED` - pytestを実行

### 手動レビューが必要な場合

- `CRITICAL_FILE_DANGEROUS_CHANGE` - 重要ファイルへの危険な変更
- `DANGEROUS_CHANGE` で大量削除が検出された場合
- 原因が不明な場合

---

## 参考リンク

- [operations_runbook.md](operations_runbook.md) - 運用手順書
- [policy_evolution_system.md](policy_evolution_system.md) - ポリシー進化システム

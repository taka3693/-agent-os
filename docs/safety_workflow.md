# 安全系チェック ワークフロー

## 目的

このドキュメントは、Agent-OS開発において**いつ**安全系チェックを実行すべきか、オペレーター向けに簡潔にまとめたものである。

---

## 基本方針

**成功を報告する前に、必ずGuardを通す。**

---

## 標準開発フロー

### 1. 作業開始前

```bash
git status
```
- 現在の状態を確認
- 未コミットの変更があれば整理

### 2. コード変更後

```bash
git diff
```
- 変更内容を確認
- 意図しない削除・追加がないか確認

### 3. 成功報告前（必須）

```bash
make safety
```
- Guard安全系テストを実行
- **29テストが通過することを確認**

### 4. Guard失敗時

1. **guard_failure_details** を確認
2. **pytest_info["summary"]** を確認（pytest関連の場合）
3. **docs/guard_failure_codes.md** を参照
4. 失敗理由を修正して再実行

### 5. コミット前

```bash
git diff --stat
make safety
git add <files>
git commit -m "..."
```

---

## Guard失敗時の対応

### 最初に確認すること

1. **実行結果の末尾** - Guard失敗サマリーが表示される
2. **`guard_failure_details`** - 構造化された失敗理由

### 表示例

```
⚠️ **Guard blocked this change**
- `PYTEST_FAILED`: FAILED test_x.py::test_y - AssertionError

**次に確認:**
- pytest出力を確認して失敗テストを修正
```

### 対応フロー

| 失敗コード | 最初にやること |
|-----------|--------------|
| `PYTEST_FAILED` | pytest出力を確認 |
| `DANGEROUS_CHANGE` | git diffで削除差分を確認 |
| `DIFF_TOO_LARGE` | 変更を小さく分割 |
| `SYNTAX_ERROR` | 編集結果の構文を確認 |
| `CRITICAL_FILE_*` | 手動レビュー |

### 手動レビューが必要な場合

- `CRITICAL_FILE_DANGEROUS_CHANGE` - 重要ファイルへの危険な変更
- 原因が不明な場合
- 大量削除が検出された場合

---

## コミット指針

**1タスク = 1差分 = 1検証 = 1コミット**

- 複数のタスクを混ぜない
- 不要な変更を含めない
- Guardが通ってからコミット

---

## クイックリファレンス

| コマンド | 用途 |
|---------|------|
| `make safety` | 安全系テスト実行 |
| `pytest -m safety` | 同上（直接実行） |
| `git diff` | 変更内容確認 |
| `git status` | 現在の状態確認 |

---

## 関連ドキュメント

- [guard_failure_codes.md](guard_failure_codes.md) - 失敗コード一覧
- [operations_runbook.md](operations_runbook.md) - 運用手順書

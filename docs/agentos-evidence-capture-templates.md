# AgentOS 証拠取得テンプレ集

## 目的
自動圧縮が入っても、診断・レビュー・監査に必要な証拠を欠かさず取るための実務テンプレ。

---

## 1. 基本原則

1. 全文を一気に出さない
2. 先に要約用コマンド、次に詳細
3. 証拠は必ず `コマンド → 生出力`
4. 圧縮が出たら証拠不足扱い
5. 長い内容は `PART1 / PART2 / PART3` で分割

---

## 2. ログ確認テンプレ

### 全体把握
```bash
wc -l app.log
tail -50 app.log
```

### 先頭 / 末尾
```bash
head -40 app.log
tail -40 app.log
```

### エラー抽出
```bash
grep -n "ERROR\|WARN\|Traceback\|Exception" app.log | tail -50
```

### 範囲指定
```bash
sed -n '1,120p' app.log
sed -n '121,240p' app.log
```

---

## 3. コード確認テンプレ

### ファイル存在
```bash
ls -l path/to/file.py
wc -l path/to/file.py
```

### 全文確認
```bash
sed -n '1,200p' path/to/file.py
sed -n '201,400p' path/to/file.py
```

### 関数・分岐抽出
```bash
grep -n "def \|class \|if __name__" path/to/file.py
grep -n "target_function_name" path/to/file.py
```

---

## 4. Git確認テンプレ

### 状態
```bash
git status
git branch --show-current
```

### 変更概要
```bash
git diff --stat
git log --oneline -n 10
```

### 対象ファイル差分
```bash
git diff -- path/to/file.py
git show HEAD -- path/to/file.py
```

### 追跡確認
```bash
git ls-files | grep '^path/to/file.py$' || true
```

---

## 5. 実行確認テンプレ

### 単体実行
```bash
python3 tool.py
python3 tool.py --help
```

### エラー系
```bash
python3 tool.py invalid_arg
python3 tool.py missing_arg
```

### 出力絞り込み
```bash
python3 tool.py ... | tail -50
python3 tool.py ... | grep -E '"ok"|"error"|"status"'
```

---

## 6. JSON確認テンプレ

### 整形して確認
```bash
cat result.json | python3 -m json.tool
```

### キー抽出
```bash
cat result.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('ok')); print(d.get('error'))"
```

### JSONL確認
```bash
tail -5 state/data.jsonl
wc -l state/data.jsonl
```

---

## 7. state ファイル確認テンプレ

### 一覧
```bash
ls -lt state/
find state -type f | sort
```

### 最新1件
```bash
f=$(ls -t state/*.json | head -n 1)
echo "$f"
sed -n '1,220p' "$f"
```

### 全件確認
```bash
for f in state/*.json; do
  echo "===== $f ====="
  sed -n '1,220p' "$f"
done
```

---

## 8. 圧縮が出た時の再取得テンプレ

### 症状
```text
[compacted: tool output removed to free context]
```

### 対応
```bash
# 1. まず件数
wc -l file

# 2. 先頭
head -40 file

# 3. 末尾
tail -40 file

# 4. エラー抽出
grep -n "ERROR\|WARN\|Traceback\|Exception" file

# 5. 必要範囲だけ
sed -n '100,180p' file
```

---

## 9. レビュー依頼テンプレ

```text
以下をこの順で出してください。
1. ファイル存在確認
2. 対象ファイル全文（200行ずつ分割）
3. 関連差分
4. 実行コマンド
5. 生出力
6. state/ログ確認
要約・感想・補足は禁止。
```

---

## 10. AgentOS向けおすすめ順序

### 仕様確認
```bash
ls -l target.py
wc -l target.py
sed -n '1,200p' target.py
```

### 実装確認
```bash
grep -n "def \|class " target.py
git diff -- target.py
```

### 実行確認
```bash
python3 target.py --help
python3 target.py ...
```

### 結果確認
```bash
ls -lt state/
tail -20 logs/app.log
```

---

## 11. 禁止パターン

### 悪い例
```bash
cat huge.log
cat huge.py
git diff
python3 tool.py
```

### 良い例
```bash
tail -50 huge.log
sed -n '1,200p' huge.py
git diff --stat
python3 tool.py | tail -50
```

---

## 12. 最小実務セット

迷ったらまずこれだけ:

```bash
git status
git diff --stat
ls -l target.py
wc -l target.py
sed -n '1,200p' target.py
python3 target.py ... | tail -50
```

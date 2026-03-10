#!/usr/bin/env bash
set -euo pipefail

cd /home/milky/agent-os

CLI="python3 /home/milky/agent-os/tools/run_agent_os_request.py"

echo '=== AgentOS smoke test ==='

mkdir -p workspace/smoke/subdir
printf 'alpha\nbeta\ngamma\n' > workspace/smoke/read_test.txt
printf 'x\n' > workspace/smoke/subdir/nested.txt

echo
echo '--- ls root ---'
$CLI "aos ls"

echo
echo '--- ls smoke ---'
$CLI "aos ls smoke"

echo
echo '--- tree smoke ---'
$CLI "aos tree smoke"

echo
echo '--- pwd ---'
$CLI "aos pwd"

echo
echo '--- root ---'
$CLI "aos root"

echo
echo '--- mkdir ---'
$CLI "aos mkdir smoke/new_dir"

echo
echo '--- read ---'
$CLI "aos read smoke/read_test.txt"

echo
echo '--- cat ---'
$CLI "aos cat smoke/read_test.txt"

echo
echo '--- delete policy ---'
$CLI "aos rm smoke/read_test.txt" || true

echo
echo '--- move policy ---'
$CLI "aos mv smoke/read_test.txt smoke/read_test2.txt" || true

echo
echo '--- pass ---'
$CLI "hello world" || true

echo
echo '=== expected checks ==='
echo '[OK] aos ls smoke -> basename 表示のみ'
echo '[OK] aos tree smoke -> 階層表示'
echo '[OK] aos pwd -> workspace 相対の現在位置'
echo '[OK] aos root -> workspace ルート'
echo '[OK] aos mkdir -> 成功応答'
echo '[OK] aos read / aos cat -> 読み取り成功'
echo '[OK] aos rm -> 未対応ポリシー応答 / rc=0'
echo '[OK] aos mv -> 未対応ポリシー応答 / rc=0'
echo '[OK] pass -> "AgentOS対象外の入力です" / rc=1'

echo
echo '=== Telegram smoke messages ==='
echo 'aos ls smoke'
echo 'aos tree smoke'
echo 'aos pwd'
echo 'aos root'
echo 'aos mkdir smoke/tg_dir'
echo 'aos read smoke/read_test.txt'
echo 'aos rm smoke/read_test.txt'
echo 'aos mv smoke/read_test.txt smoke/read_test2.txt'
echo 'hello world'

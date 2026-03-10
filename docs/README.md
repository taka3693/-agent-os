# Agent OS README

## 目的

この構成は、途中停止しても再開できる最小運用を作るためのものです。

目標は次の2つです。

- 何をしていたかを task JSON で追跡できる
- plan -> task -> update -> completed を小さく回せる

## ディレクトリ構成

agent-os/

state/
tasks/

plans/

skills/
critique/
manifest.yaml
decision/
manifest.yaml
execution/
manifest.yaml
research/
manifest.yaml

docs/
README.md

router/
router.py

## 各ディレクトリの役割

state/tasks/
1タスク = 1JSON  
実行中・中断中・完了済みの状態を保存する

plans/
1依頼 = 1JSON  
実行前の分解計画を保存する

skills/
1 skill = 1 manifest.yaml  
skillの役割と入出力を定義する

docs/
人間向けの運用ルール

router/
最小Router実装

## 命名規則

task_id
task-YYYYMMDD-XXX

plan_id
plan-YYYYMMDD-XXX

## 最小運用フロー

1 plan JSON を作る
2 task JSON を作る
3 作業ごとに task JSON を更新
4 status = completed

## status

todo
in_progress
paused
blocked
completed
cancelled

## task更新ルール

更新する項目

next_action
touched_files
updated_at

### next_action

次にやる1手だけ書く

### touched_files

編集して保存したファイルを書く

### updated_at

task JSON を保存した直後の時刻

ISO8601

## Routerルール

固定カテゴリ

critique
decision
experiment
execution
research
retrospective

フォールバック順

decision
critique
research
execution

skill連鎖

最大3

allowed_skills

事前フィルタ


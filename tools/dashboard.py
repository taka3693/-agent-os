#!/usr/bin/env python3
"""KPI Dashboard for AgentOS decision/execution tracking."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
DECISION_LOG = ROOT / "state" / "decision_runs" / "decision_runs.jsonl"
EXECUTION_LOG = ROOT / "state" / "execution_runs" / "execution_runs.jsonl"
STRATEGY_DIR = ROOT / "state" / "strategy"

def load_jsonl(path):
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            try:
                records.append(json.loads(line))
            except:
                pass
    return records

def get_recent(records, days=7):
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for r in records:
        ts = r.get("timestamp") or r.get("logged_at")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.replace(tzinfo=None) > cutoff:
                    recent.append(r)
            except:
                pass
    return recent

def load_weekly_goals():
    path = STRATEGY_DIR / "weekly_goals.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}

def print_dashboard():
    print("=" * 60)
    print("  AgentOS KPI Dashboard")
    print("=" * 60)
    
    goals = load_weekly_goals()
    if goals:
        print(f"\n[TARGET] {goals.get('primary_goal', 'N/A')}")
        print(f"  Period: {goals.get('week_start', '?')} - {goals.get('week_end', '?')}")
        secondary = goals.get('secondary_goals', [])
        if secondary:
            print(f"  Secondary: {', '.join(secondary)}")
    
    decisions = get_recent(load_jsonl(DECISION_LOG), 7)
    print(f"\n[DECISIONS] Past 7 days: {len(decisions)}")
    
    if decisions:
        winners = Counter(d.get("winner") or d.get("decision_winner") for d in decisions)
        winners = {k: v for k, v in winners.items() if k}
        if winners:
            print("  Top Winners:")
            for w, c in Counter(winners).most_common(3):
                print(f"    - {w}: {c}")
    
    executions = get_recent(load_jsonl(EXECUTION_LOG), 7)
    print(f"\n[EXECUTIONS] Past 7 days: {len(executions)}")
    
    if executions:
        statuses = Counter(e.get("result_flag") or e.get("status") for e in executions)
        for s, c in statuses.most_common():
            mark = "OK" if s == "success" else "NG" if s in ("fail", "failed") else "??"
            print(f"  [{mark}] {s}: {c}")
    
    print(f"\n[RECENT DECISIONS]")
    for d in decisions[-5:]:
        ts = (d.get("timestamp") or d.get("logged_at") or "")[:16]
        winner = d.get("winner") or d.get("decision_winner") or "?"
        query = (d.get("input_query") or d.get("query") or "")[:35]
        print(f"  {ts} | {winner} <- {query}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    print_dashboard()

#!/usr/bin/env python3
"""セッション監視 - コンテキストオーバーフロー対策"""

import os
import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

SESSIONS_DIR = Path.home() / ".openclaw/agents/main/sessions"
MAX_SESSION_SIZE_KB = 100  # 100KB以上で警告
MAX_SESSION_AGE_HOURS = 4  # 4時間以上で警告
CHAT_ID = "6474742983"

def get_active_session():
    """アクティブなセッションを取得"""
    sessions_file = SESSIONS_DIR / "sessions.json"
    if not sessions_file.exists():
        return None
    
    with open(sessions_file) as f:
        sessions = json.load(f)
    
    # dict形式: キーがセッションキー
    telegram_key = "agent:main:telegram:direct:6474742983"
    if telegram_key in sessions:
        return sessions[telegram_key]
    return None

def check_session_health():
    """セッションの健全性をチェック"""
    issues = []
    
    # セッションファイルのサイズをチェック
    for jsonl_file in SESSIONS_DIR.glob("*.jsonl"):
        size_kb = jsonl_file.stat().st_size / 1024
        if size_kb > MAX_SESSION_SIZE_KB:
            issues.append({
                "type": "large_session",
                "file": jsonl_file.name,
                "size_kb": round(size_kb, 1),
                "recommendation": f"/reset 推奨（{size_kb:.0f}KB > {MAX_SESSION_SIZE_KB}KB）"
            })
    
    # アクティブセッションの経過時間をチェック
    session = get_active_session()
    if session:
        updated_at = session.get("updatedAt")
        if updated_at:
            try:
                # ミリ秒タイムスタンプ
                last_dt = datetime.fromtimestamp(updated_at / 1000, tz=timezone.utc)
                now = datetime.now(timezone.utc)
                
                # セッションファイルの作成時刻を確認
                session_file = session.get("sessionFile")
                if session_file and os.path.exists(session_file):
                    created = os.path.getctime(session_file)
                    created_dt = datetime.fromtimestamp(created, tz=timezone.utc)
                    session_duration = (now - created_dt).total_seconds() / 3600
                    
                    if session_duration > MAX_SESSION_AGE_HOURS:
                        issues.append({
                            "type": "long_session",
                            "duration_hours": round(session_duration, 1),
                            "recommendation": f"セッション{session_duration:.1f}h経過 - /reset 推奨"
                        })
            except Exception as e:
                print(f"Error checking session age: {e}")
    
    return issues

def send_alert(message: str):
    """Telegramにアラートを送信"""
    try:
        import sys
        sys.path.insert(0, str(Path.home() / "agent-os"))
        from miso.bridge import send_telegram_message
        send_telegram_message(CHAT_ID, f"⚠️ セッション監視\n\n{message}")
        return True
    except Exception as e:
        print(f"Alert (local): {message}")
        return False

def main():
    """メイン処理"""
    issues = check_session_health()
    
    if issues:
        print(f"Found {len(issues)} issue(s):")
        messages = []
        for issue in issues:
            msg = f"[{issue['type']}] {issue['recommendation']}"
            print(f"  - {msg}")
            messages.append(msg)
        
        # Telegramに通知
        send_alert("\n".join(messages))
    else:
        print("Session health: OK")
    
    return {"ok": True, "issues": issues}

if __name__ == "__main__":
    result = main()
    print(json.dumps(result, indent=2, ensure_ascii=False))

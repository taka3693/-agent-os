from __future__ import annotations
from typing import Any, Dict, List

EXECUTION_HINTS = [
    "対象を1つに限定する",
    "出力物を先に決める",
    "完了条件を明示する",
    "実行順序を固定する",
    "完了後は必ず裏取りする",
]

def _normalize_query(query: Any) -> str:
    if query is None:
        return ""
    return str(query).strip()

def _extract_verification(query: str) -> Dict[str, Any]:
    """Generate verification steps based on query content."""
    q = query.lower()
    
    verification = {
        "method": "manual_check",
        "commands": [],
        "checklist": [],
    }
    
    # ファイル操作系
    if any(k in q for k in ["ファイル", "作成", "更新", "修正", "file", "create", "update"]):
        verification["commands"].append("cat <対象ファイル> | head -20  # 内容確認")
        verification["commands"].append("ls -la <対象ファイル>  # 存在確認")
        verification["checklist"].append("ファイルが存在するか")
        verification["checklist"].append("内容が期待通りか")
    
    # 設定変更系
    if any(k in q for k in ["設定", "config", "変更", "置換", "replace"]):
        verification["commands"].append("grep '<変更したキーワード>' <対象ファイル>")
        verification["checklist"].append("変更が反映されているか")
        verification["checklist"].append("他の箇所に残骸がないか")
    
    # コード系
    if any(k in q for k in ["コード", "実装", "関数", "code", "implement", "function"]):
        verification["commands"].append("python3 <スクリプト> --help  # 実行確認")
        verification["commands"].append("python3 -c 'import <モジュール>'  # import確認")
        verification["checklist"].append("構文エラーがないか")
        verification["checklist"].append("期待した出力が出るか")
    
    # デプロイ・起動系
    if any(k in q for k in ["起動", "再起動", "デプロイ", "restart", "deploy"]):
        verification["commands"].append("systemctl --user status <サービス名>")
        verification["checklist"].append("サービスがactiveか")
        verification["checklist"].append("エラーログがないか")
    
    # デフォルト
    if not verification["checklist"]:
        verification["checklist"] = [
            "期待した結果が得られたか",
            "副作用がないか",
            "元に戻せる状態か",
        ]
    
    return verification

def _make_steps(query: str) -> List[str]:
    if not query:
        return [
            "対象・目的・完了条件を書く。",
            "最小の作業単位に分解する。",
            "上から順に1つずつ実行する。",
            "完了後、検証コマンドで裏取りする。",
        ]
    
    steps: List[str] = []
    
    if not any(k in query for k in ["完了", "done", "終了", "finish"]):
        steps.append("完了条件を1文で定義する。")
    
    if not any(k in query for k in ["出力", "成果物", "ファイル", "result"]):
        steps.append("出力物を明確化する。何を作れば終わりか決める。")
    
    steps.append("対象を1つに絞る。複数作業の同時進行は禁止。")
    steps.append("作業を3〜5手順に分解する。")
    steps.append("各手順の実行後に結果を短く記録する。")
    steps.append("【検証】完了条件を満たしたか、コマンドで裏取りする。")
    
    uniq: List[str] = []
    for x in steps:
        if x not in uniq:
            uniq.append(x)
    return uniq[:6]

def _make_output(query: str) -> str:
    if not query:
        return "最小の実行計画"
    return f"{query} の実行計画"

def run(query: str, **kwargs: Any) -> Dict[str, Any]:
    q = _normalize_query(query)
    verification = _extract_verification(q)
    
    return {
        "ok": True,
        "skill": "execution",
        "query": q,
        "summary": "入力内容を実行可能な最小手順へ分解した。",
        "output": _make_output(q),
        "steps": _make_steps(q),
        "verification": verification,
        "notes": EXECUTION_HINTS,
    }

def execute(query: str, **kwargs: Any) -> Dict[str, Any]:
    return run(query, **kwargs)

def execution(query: str, **kwargs: Any) -> Dict[str, Any]:
    return run(query, **kwargs)

def run_execution(query: str, **kwargs):
    return run(query, **kwargs)

def run_execution_plan(query: str, **kwargs):
    return run(query, **kwargs)

def execute_plan(query: str, **kwargs):
    return run(query, **kwargs)

if __name__ == "__main__":
    import json
    import sys
    q = " ".join(sys.argv[1:]).strip()
    print(json.dumps(run(q), ensure_ascii=False, indent=2))

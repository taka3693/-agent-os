from __future__ import annotations

import json
from typing import Any, Dict, Tuple


def build_json_batch_error(message: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "mode": "execution",
        "status": "failed",
        "is_json_batch": True,
        "operation_count": 0,
        "reply_text": message,
    }


def parse_json_batch_request(text: str) -> Tuple[bool, Dict[str, Any] | None, Dict[str, Any] | None]:
    s = "" if text is None else str(text)
    prefix = "aos json "

    if not s.lower().startswith(prefix):
        if s.strip().lower() == "aos json":
            return True, None, build_json_batch_error(
                'json 実行失敗\n理由: JSON が空です\n使い方: aos json {"steps":["aos ls", "aos read notes/file.txt"]}'
            )
        return False, None, None

    raw = s[len(prefix):].strip()
    if not raw:
        return True, None, build_json_batch_error(
            'json 実行失敗\n理由: JSON が空です\n使い方: aos json {"steps":["aos ls", "aos read notes/file.txt"]}'
        )

    try:
        obj = json.loads(raw)
    except Exception as e:
        return True, None, build_json_batch_error(
            f"json 実行失敗\n理由: JSON 解析エラー\n詳細: {e}"
        )

    if not isinstance(obj, dict):
        return True, None, build_json_batch_error(
            "json 実行失敗\n理由: ルートは object である必要があります"
        )

    steps = obj.get("steps")
    validate_only = bool(obj.get("validate_only", False) or obj.get("dry_run", False))

    if not isinstance(steps, list) or not steps:
        return True, None, build_json_batch_error(
            'json 実行失敗\n理由: steps が空です\n使い方: aos json {"steps":["aos ls", "aos read notes/file.txt"]}'
        )

    return True, {
        "steps": steps,
        "validate_only": validate_only,
        "raw_obj": obj,
    }, None

"""Multimodal Input Handler - 複数形式の入力を処理

画像、PDF、ファイル等を検出し、適切な処理パイプラインに渡す。
"""
from __future__ import annotations
import base64
import mimetypes
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# サポートするファイル形式
SUPPORTED_FORMATS = {
    "image": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"],
    "document": [".pdf", ".docx", ".doc", ".txt", ".md"],
    "data": [".csv", ".xlsx", ".xls", ".json", ".yaml", ".yml"],
    "code": [".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".h"],
}


def detect_input_type(input_data: Any) -> Dict[str, Any]:
    """入力のタイプを検出
    
    Args:
        input_data: ファイルパス、base64文字列、またはdict
    
    Returns:
        {
            "type": "text" | "image" | "document" | "data" | "code" | "unknown",
            "format": str,
            "path": Optional[str],
            "is_base64": bool,
        }
    """
    # 文字列の場合
    if isinstance(input_data, str):
        # base64画像チェック
        if input_data.startswith("data:image"):
            return {
                "type": "image",
                "format": input_data.split(";")[0].split("/")[1],
                "path": None,
                "is_base64": True,
            }
        
        # ファイルパスチェック
        path = Path(input_data)
        if path.exists() and path.is_file():
            ext = path.suffix.lower()
            
            for file_type, extensions in SUPPORTED_FORMATS.items():
                if ext in extensions:
                    return {
                        "type": file_type,
                        "format": ext,
                        "path": str(path),
                        "is_base64": False,
                    }
            
            return {
                "type": "unknown",
                "format": ext,
                "path": str(path),
                "is_base64": False,
            }
        
        # 通常のテキスト
        return {
            "type": "text",
            "format": "plain",
            "path": None,
            "is_base64": False,
        }
    
    # dictの場合（構造化データ）
    if isinstance(input_data, dict):
        if "image" in input_data or "image_url" in input_data:
            return {
                "type": "image",
                "format": "url",
                "path": input_data.get("image") or input_data.get("image_url"),
                "is_base64": False,
            }
        
        if "file" in input_data or "path" in input_data:
            file_path = input_data.get("file") or input_data.get("path")
            return detect_input_type(file_path)
        
        return {
            "type": "data",
            "format": "dict",
            "path": None,
            "is_base64": False,
        }
    
    return {
        "type": "unknown",
        "format": str(type(input_data)),
        "path": None,
        "is_base64": False,
    }


def load_file_content(path: str) -> Dict[str, Any]:
    """ファイルの内容を読み込む"""
    file_path = Path(path)
    
    if not file_path.exists():
        return {"ok": False, "error": f"File not found: {path}"}
    
    input_type = detect_input_type(path)
    
    try:
        if input_type["type"] == "image":
            # 画像をbase64エンコード
            with open(file_path, "rb") as f:
                content = base64.b64encode(f.read()).decode("utf-8")
            
            mime_type = mimetypes.guess_type(path)[0] or "image/png"
            return {
                "ok": True,
                "type": "image",
                "content": f"data:{mime_type};base64,{content}",
                "size_bytes": file_path.stat().st_size,
            }
        
        elif input_type["type"] == "document":
            if input_type["format"] == ".pdf":
                # PDFは特別処理（テキスト抽出またはbase64）
                with open(file_path, "rb") as f:
                    content = base64.b64encode(f.read()).decode("utf-8")
                return {
                    "ok": True,
                    "type": "document",
                    "format": "pdf",
                    "content_base64": content,
                    "size_bytes": file_path.stat().st_size,
                }
            else:
                # テキスト系ドキュメント
                content = file_path.read_text(encoding="utf-8", errors="replace")
                return {
                    "ok": True,
                    "type": "document",
                    "format": input_type["format"],
                    "content": content,
                    "size_bytes": file_path.stat().st_size,
                }
        
        elif input_type["type"] in ("data", "code"):
            content = file_path.read_text(encoding="utf-8", errors="replace")
            return {
                "ok": True,
                "type": input_type["type"],
                "format": input_type["format"],
                "content": content,
                "size_bytes": file_path.stat().st_size,
            }
        
        else:
            return {"ok": False, "error": f"Unsupported type: {input_type['type']}"}
    
    except Exception as e:
        return {"ok": False, "error": str(e)}


def prepare_multimodal_message(
    text: str,
    attachments: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """マルチモーダルメッセージを準備
    
    Args:
        text: テキストメッセージ
        attachments: ファイルパスのリスト
    
    Returns:
        OpenClaw/LLM用のメッセージ構造
    """
    message_parts = []
    
    # テキスト部分
    if text:
        message_parts.append({
            "type": "text",
            "text": text,
        })
    
    # 添付ファイル
    if attachments:
        for path in attachments:
            file_content = load_file_content(path)
            
            if not file_content.get("ok"):
                message_parts.append({
                    "type": "text",
                    "text": f"[Error loading {path}: {file_content.get('error')}]",
                })
                continue
            
            if file_content["type"] == "image":
                message_parts.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": file_content["content"].split(",")[1] if "," in file_content["content"] else file_content["content"],
                    },
                })
            
            elif file_content["type"] == "document" and file_content.get("format") == "pdf":
                message_parts.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": file_content["content_base64"],
                    },
                })
            
            else:
                # テキスト系はそのまま追加
                message_parts.append({
                    "type": "text",
                    "text": f"[File: {path}]\n```\n{file_content['content'][:5000]}\n```",
                })
    
    return {
        "parts": message_parts,
        "has_vision": any(p["type"] == "image" for p in message_parts),
        "has_document": any(p["type"] == "document" for p in message_parts),
    }

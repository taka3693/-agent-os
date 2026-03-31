"""Vision Processor - 画像認識処理

OpenClaw/LLMのビジョン機能を使って画像を解析する。
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ops.multimodal_input import load_file_content, prepare_multimodal_message

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def analyze_image(
    image_path: str,
    prompt: str = "この画像を詳しく説明してください。",
    agent: str = "dev",
) -> Dict[str, Any]:
    """画像を解析
    
    Args:
        image_path: 画像ファイルのパス
        prompt: 解析の指示
        agent: 使用するエージェント
    
    Returns:
        解析結果
    """
    # 画像を読み込み
    file_content = load_file_content(image_path)
    
    if not file_content.get("ok"):
        return {
            "ok": False,
            "error": file_content.get("error", "Failed to load image"),
        }
    
    # OpenClawでビジョン解析を実行
    try:
        # OpenClawのvisionコマンドを使用
        result = subprocess.run(
            [
                "openclaw", "run",
                "--agent", agent,
                "--vision", image_path,
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(PROJECT_ROOT),
        )
        
        if result.returncode == 0:
            return {
                "ok": True,
                "analysis": result.stdout.strip(),
                "image_path": image_path,
            }
        else:
            return {
                "ok": False,
                "error": result.stderr or "Vision analysis failed",
            }
    
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": "Vision analysis timed out",
        }
    except FileNotFoundError:
        # OpenClawがない場合は代替処理
        return analyze_image_fallback(image_path, prompt)


def analyze_image_fallback(
    image_path: str,
    prompt: str,
) -> Dict[str, Any]:
    """OpenClawがない場合のフォールバック（基本情報のみ）"""
    from PIL import Image
    
    try:
        with Image.open(image_path) as img:
            return {
                "ok": True,
                "analysis": f"画像情報: サイズ {img.size[0]}x{img.size[1]}, モード {img.mode}, フォーマット {img.format}",
                "image_path": image_path,
                "metadata": {
                    "width": img.size[0],
                    "height": img.size[1],
                    "mode": img.mode,
                    "format": img.format,
                },
                "note": "Full vision analysis requires OpenClaw with vision support",
            }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
        }


def analyze_screenshot(
    image_path: str,
    focus: str = "error",
) -> Dict[str, Any]:
    """スクリーンショットを解析（エラー検出に最適化）
    
    Args:
        image_path: スクリーンショットのパス
        focus: "error" | "ui" | "text" | "general"
    """
    prompts = {
        "error": "このスクリーンショットにエラーメッセージがあれば、その内容と原因、解決策を教えてください。",
        "ui": "このUIの構成要素と改善点を分析してください。",
        "text": "この画像に含まれるテキストをすべて抽出してください。",
        "general": "この画像の内容を詳しく説明してください。",
    }
    
    prompt = prompts.get(focus, prompts["general"])
    return analyze_image(image_path, prompt)


def extract_text_from_image(image_path: str) -> Dict[str, Any]:
    """画像からテキストを抽出（OCR）"""
    return analyze_image(
        image_path,
        prompt="この画像に含まれるすべてのテキストを抽出してください。書式を維持して出力してください。",
    )


def compare_images(
    image1_path: str,
    image2_path: str,
) -> Dict[str, Any]:
    """2つの画像を比較"""
    # 両方の画像を読み込んで比較リクエスト
    # 現在のOpenClawは単一画像のみサポートの可能性があるため、順次処理
    
    result1 = analyze_image(image1_path, "この画像の主要な特徴を簡潔に説明してください。")
    result2 = analyze_image(image2_path, "この画像の主要な特徴を簡潔に説明してください。")
    
    if not result1.get("ok") or not result2.get("ok"):
        return {
            "ok": False,
            "error": "Failed to analyze one or both images",
        }
    
    return {
        "ok": True,
        "image1_analysis": result1["analysis"],
        "image2_analysis": result2["analysis"],
        "comparison_note": "Full comparison requires multi-image vision support",
    }

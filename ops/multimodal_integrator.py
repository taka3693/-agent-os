"""
Multimodal Integrator for Agent OS

Integrates multiple modalities (text, image, audio, video) for unified reasoning.
Automatically detects input types, processes each with appropriate processors,
and combines results for LLM queries.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Configure logging
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"multimodal_integrator_{logging.getLevelName(logging.INFO).lower()}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MultimodalIntegratorError(Exception):
    """Base exception for multimodal integrator errors"""
    pass


class UnsupportedInputTypeError(MultimodalIntegratorError):
    """Unsupported input type"""
    pass


# ===== Dependencies =====

VISION_AVAILABLE = False
try:
    vision_processor = __import__("ops.vision_processor", fromlist=["analyze_image"])
    VISION_AVAILABLE = True
    logger.info("vision_processor is available")
except (ImportError, AttributeError):
    logger.warning("vision_processor not available")


AUDIO_AVAILABLE = False
try:
    audio_processor = __import__("ops.audio_processor", fromlist=["transcribe_audio", "get_audio_info"])
    AUDIO_AVAILABLE = True
    logger.info("audio_processor is available")
except (ImportError, AttributeError):
    logger.warning("audio_processor not available")


VIDEO_AVAILABLE = False
try:
    video_processor = __import__("ops.video_processor", fromlist=["analyze_video", "get_video_info"])
    VIDEO_AVAILABLE = True
    logger.info("video_processor is available")
except (ImportError, AttributeError):
    logger.warning("video_processor not available")


# MISO integration
MISO_AVAILABLE = False
try:
    from miso.bridge import start_mission, update_agent_status, complete_mission, fail_mission
    MISO_AVAILABLE = True
    logger.info("MISO bridge is available")
except ImportError:
    logger.warning("MISO bridge not available")


# ===== Input Detection =====

def detect_input_type(input_data: Union[str, Dict[str, Any]]) -> str:
    """
    Detect the type of input based on content or file extension.

    Args:
        input_data: Either a file path or a dict with 'type' and 'content'/'path'

    Returns:
        Detected type: "text", "image", "audio", "video", or "unknown"
    """
    # If it's already a dict with type, return that
    if isinstance(input_data, dict):
        input_type = input_data.get("type")
        if input_type:
            return input_type

        # Try to detect from path
        path = input_data.get("path") or input_data.get("content")
        if path:
            return detect_input_type(path)

    # If it's a string, detect from file extension or content
    if isinstance(input_data, str):
        path = Path(input_data)

        # If it's a file, check extension
        if path.exists():
            ext = path.suffix.lower()

            # Image formats
            if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}:
                return "image"

            # Audio formats
            if ext in {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".wma"}:
                return "audio"

            # Video formats
            if ext in {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}:
                return "video"

        # If it doesn't exist or has no extension, treat as text
        return "text"

    return "unknown"


def normalize_input(input_data: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalize input data to a standard format.

    Args:
        input_data: Either a file path or a dict

    Returns:
        Normalized dict with 'type', 'content'/'path', and 'metadata'
    """
    if isinstance(input_data, dict):
        # Already a dict, just ensure it has required fields
        result = {
            "type": input_data.get("type", "unknown"),
            "path": input_data.get("path"),
            "content": input_data.get("content"),
            "metadata": input_data.get("metadata", {}),
        }

        # Detect type if not provided
        if result["type"] == "unknown":
            result["type"] = detect_input_type(input_data)

        return result

    # If it's a string, convert to dict
    input_type = detect_input_type(input_data)

    if input_type == "text":
        return {
            "type": "text",
            "content": input_data,
            "path": None,
            "metadata": {},
        }
    else:
        return {
            "type": input_type,
            "path": input_data,
            "content": None,
            "metadata": {},
        }


# ===== Input Processing =====

def process_text(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process text input.

    Args:
        input_data: Normalized input dict

    Returns:
        Processing result
    """
    text = input_data.get("content", "")

    # Basic text statistics
    result = {
        "type": "text",
        "text": text,
        "length": len(text),
        "word_count": len(text.split()),
        "char_count": len(text.replace(" ", "")),
        "metadata": input_data.get("metadata", {}),
    }

    return result


def process_image(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process image input using vision processor.

    Args:
        input_data: Normalized input dict

    Returns:
        Processing result
    """
    path = input_data.get("path")

    if not VISION_AVAILABLE:
        return {
            "type": "image",
            "path": path,
            "error": "vision_processor not available",
            "metadata": input_data.get("metadata", {}),
        }

    try:
        # Analyze image with a general description prompt
        analysis_result = vision_processor.analyze_image(
            path,
            prompt="この画像の内容を詳細に説明してください。含まれている物体、シーン、テキスト、雰囲気などについて説明してください。"
        )

        result = {
            "type": "image",
            "path": path,
            "description": analysis_result.get("description"),
            "objects": analysis_result.get("objects"),
            "text": analysis_result.get("text"),
            "metadata": input_data.get("metadata", {}),
        }

    except Exception as e:
        result = {
            "type": "image",
            "path": path,
            "error": str(e),
            "metadata": input_data.get("metadata", {}),
        }

    return result


def process_audio(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process audio input using audio processor.

    Args:
        input_data: Normalized input dict

    Returns:
        Processing result
    """
    path = input_data.get("path")

    if not AUDIO_AVAILABLE:
        return {
            "type": "audio",
            "path": path,
            "error": "audio_processor not available",
            "metadata": input_data.get("metadata", {}),
        }

    try:
        # Get audio info
        info_result = audio_processor.get_audio_info(path)

        # Transcribe audio
        transcript_result = audio_processor.transcribe_audio(path, language="ja")

        result = {
            "type": "audio",
            "path": path,
            "transcript": transcript_result.get("text"),
            "language": transcript_result.get("language"),
            "duration": info_result.get("duration"),
            "format": info_result.get("format"),
            "metadata": input_data.get("metadata", {}),
        }

    except Exception as e:
        result = {
            "type": "audio",
            "path": path,
            "error": str(e),
            "metadata": input_data.get("metadata", {}),
        }

    return result


def process_video(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process video input using video processor.

    Args:
        input_data: Normalized input dict

    Returns:
        Processing result
    """
    path = input_data.get("path")

    if not VIDEO_AVAILABLE:
        return {
            "type": "video",
            "path": path,
            "error": "video_processor not available",
            "metadata": input_data.get("metadata", {}),
        }

    try:
        # Analyze video
        analysis_result = video_processor.analyze_video(
            path,
            prompt="この動画の内容を詳細に説明してください。シーンの変化、主要な要素、音声内容などを含めてください。",
            frame_interval=3.0,
            max_frames=5,
            transcribe_audio=True
        )

        result = {
            "type": "video",
            "path": path,
            "analysis": analysis_result.get("analysis"),
            "frames_analyzed": analysis_result.get("frames_analyzed"),
            "transcript": analysis_result.get("transcript"),
            "video_info": analysis_result.get("video_info"),
            "metadata": input_data.get("metadata", {}),
        }

    except Exception as e:
        result = {
            "type": "video",
            "path": path,
            "error": str(e),
            "metadata": input_data.get("metadata", {}),
        }

    return result


def process_input(input_data: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Process a single input based on its type.

    Args:
        input_data: Input to process

    Returns:
        Processing result
    """
    normalized = normalize_input(input_data)
    input_type = normalized["type"]

    logger.info(f"Processing {input_type} input: {normalized.get('path') or normalized.get('content')[:50]}")

    if input_type == "text":
        return process_text(normalized)
    elif input_type == "image":
        return process_image(normalized)
    elif input_type == "audio":
        return process_audio(normalized)
    elif input_type == "video":
        return process_video(normalized)
    else:
        raise UnsupportedInputTypeError(f"Unsupported input type: {input_type}")


# ===== Integration =====

def integrate_inputs(
    inputs: List[Union[str, Dict[str, Any]]],
    chat_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Integrate multiple inputs into a unified context.

    Args:
        inputs: List of inputs (file paths or dicts)
        chat_id: Telegram chat ID for MISO

    Returns:
        Dict with keys:
        - ok: True if integration succeeded
        - context: Unified context with all processed inputs
        - sources: List of source information
        - error: Error message (if failed)
    """
    logger.info(f"Integrating {len(inputs)} inputs...")

    # Start MISO mission if available
    mission_id = None
    if MISO_AVAILABLE and chat_id:
        try:
            mission_id = f"mm-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            start_mission(
                mission_id=mission_id,
                mission_name="Multimodal Integration",
                goal=f"Process {len(inputs)} multimodal inputs",
                chat_id=chat_id,
                agents=[f"processor_{i}" for i in range(len(inputs))]
            )
        except Exception as e:
            logger.warning(f"Failed to start MISO mission: {e}")

    result = {
        "ok": False,
        "context": {
            "inputs": [],
            "summary": "",
            "timestamp": datetime.now().isoformat(),
        },
        "sources": [],
        "error": None,
        "mission_id": mission_id,
    }

    try:
        # Process each input
        processed_inputs = []
        sources = []

        for i, input_data in enumerate(inputs):
            # Update MISO status
            if MISO_AVAILABLE and mission_id:
                agent_name = f"processor_{i}"
                update_agent_status(mission_id, agent_name, "RUNNING")

            # Process input
            processed = process_input(input_data)
            processed_inputs.append(processed)
            sources.append({
                "index": i,
                "type": processed.get("type"),
                "path": processed.get("path"),
                "content_preview": processed.get("text", processed.get("transcript", processed.get("description", "")))[:100],
            })

            # Update MISO status
            if MISO_AVAILABLE and mission_id:
                update_agent_status(mission_id, agent_name, "DONE")

        result["context"]["inputs"] = processed_inputs
        result["sources"] = sources

        # Generate summary
        summary_parts = []
        for i, processed in enumerate(processed_inputs):
            input_type = processed.get("type", "unknown")
            summary_parts.append(f"{i+1}. {input_type.upper()}:")

            if input_type == "text":
                text = processed.get("text", "")
                summary_parts.append(f"   テキスト: {text[:100]}{'...' if len(text) > 100 else ''}")
            elif input_type == "image":
                desc = processed.get("description", "")
                summary_parts.append(f"   画像: {desc[:100]}{'...' if len(desc) > 100 else ''}")
            elif input_type == "audio":
                transcript = processed.get("transcript", "")
                summary_parts.append(f"   音声: {transcript[:100]}{'...' if len(transcript) > 100 else ''}")
            elif input_type == "video":
                analysis = processed.get("analysis", "")
                summary_parts.append(f"   動画: {analysis[:100]}{'...' if len(analysis) > 100 else ''}")
            elif "error" in processed:
                summary_parts.append(f"   エラー: {processed['error']}")

            summary_parts.append("")

        result["context"]["summary"] = "\n".join(summary_parts)
        result["ok"] = True

        # Complete MISO mission
        if MISO_AVAILABLE and mission_id:
            complete_mission(mission_id, f"Processed {len(inputs)} inputs successfully")

        logger.info(f"Integration complete: {len(processed_inputs)} inputs processed")

    except Exception as e:
        error_msg = f"Integration failed: {e}"
        logger.error(error_msg)
        result["error"] = error_msg

        if MISO_AVAILABLE and mission_id:
            fail_mission(mission_id, error_msg)

    return result


# ===== Querying =====

def multimodal_query(
    inputs: List[Union[str, Dict[str, Any]]],
    prompt: str,
    chat_id: Optional[str] = None,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process multiple modal inputs and query LLM with integrated context.

    Args:
        inputs: List of inputs to process
        prompt: Query for the LLM
        chat_id: Telegram chat ID for MISO
        model: Model name to use

    Returns:
        Dict with keys:
        - ok: True if query succeeded
        - response: LLM response
        - sources: List of source information
        - context: Full integrated context
        - error: Error message (if failed)
    """
    logger.info(f"Multimodal query with {len(inputs)} inputs: {prompt[:50]}...")

    # Integrate inputs
    integration_result = integrate_inputs(inputs, chat_id=chat_id)

    if not integration_result["ok"]:
        return {
            "ok": False,
            "response": None,
            "sources": [],
            "context": None,
            "error": integration_result["error"],
        }

    # Build full prompt with context
    context_summary = integration_result["context"]["summary"]
    full_prompt = f"""以下のマルチモーダル入力を考慮して、質問に答えてください。

== 入力内容 ==
{context_summary}

== 質問 ==
{prompt}

上記の入力に基づいて、質問に答えてください。複数のモーダルからの情報を統合して回答してください。
"""

    result = {
        "ok": False,
        "response": None,
        "sources": integration_result["sources"],
        "context": integration_result["context"],
        "error": None,
    }

    try:
        # Query LLM (placeholder - integrate with actual LLM call)
        # For now, return a response indicating integration was successful
        result["response"] = f"[マルチモーダルクエリの応答]\n\n処理された入力: {len(inputs)}件\n\n{full_prompt}"
        result["ok"] = True

        logger.info("Multimodal query completed")

    except Exception as e:
        error_msg = f"Query failed: {e}"
        logger.error(error_msg)
        result["error"] = error_msg

    return result


# ===== Auto Processing =====

def auto_process(file_path: str) -> Dict[str, Any]:
    """
    Automatically detect file type and process with appropriate processor.

    Args:
        file_path: Path to file to process

    Returns:
        Dict with keys:
        - ok: True if processing succeeded
        - type: Detected file type
        - result: Processing result from appropriate processor
        - error: Error message (if failed)
    """
    logger.info(f"Auto-processing file: {file_path}")

    path = Path(file_path)

    if not path.exists():
        return {
            "ok": False,
            "type": None,
            "result": None,
            "error": f"File not found: {file_path}"
        }

    # Detect type
    file_type = detect_input_type(str(path))

    result = {
        "ok": False,
        "type": file_type,
        "result": None,
        "error": None,
    }

    try:
        # Process with appropriate processor
        processed = process_input(str(path))

        result["result"] = processed
        result["ok"] = True

        logger.info(f"Auto-processed {file_type}: {file_path}")

    except Exception as e:
        error_msg = f"Auto-processing failed: {e}"
        logger.error(error_msg)
        result["error"] = error_msg

    return result


# ===== Summarization =====

def summarize_multimodal(
    inputs: List[Union[str, Dict[str, Any]]],
    chat_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a unified summary from multiple modal inputs.

    Args:
        inputs: List of inputs to summarize
        chat_id: Telegram chat ID for MISO

    Returns:
        Dict with keys:
        - ok: True if summarization succeeded
        - summary: Unified summary
        - sources: List of source information
        - error: Error message (if failed)
    """
    logger.info(f"Summarizing {len(inputs)} multimodal inputs...")

    # Integrate inputs
    integration_result = integrate_inputs(inputs, chat_id=chat_id)

    if not integration_result["ok"]:
        return {
            "ok": False,
            "summary": None,
            "sources": [],
            "error": integration_result["error"],
        }

    # Build summary from context
    context = integration_result["context"]
    summary_parts = ["# マルチモーダル入力の要約\n"]

    for i, processed in enumerate(context["inputs"], 1):
        input_type = processed.get("type", "unknown")
        summary_parts.append(f"\n## {i}. {input_type.upper()}\n")

        if input_type == "text":
            summary_parts.append(f"**内容:** {processed.get('text', '')}")
            summary_parts.append(f"**単語数:** {processed.get('word_count', 0)}")

        elif input_type == "image":
            summary_parts.append(f"**説明:** {processed.get('description', 'N/A')}")
            if processed.get("objects"):
                summary_parts.append(f"**検出された物体:** {', '.join(processed['objects'][:5])}")
            if processed.get("text"):
                summary_parts.append(f"**検出されたテキスト:** {processed['text']}")

        elif input_type == "audio":
            summary_parts.append(f"**転写:** {processed.get('transcript', 'N/A')}")
            summary_parts.append(f"**言語:** {processed.get('language', 'N/A')}")
            if processed.get("duration"):
                summary_parts.append(f"**長さ:** {processed['duration']:.1f}秒")

        elif input_type == "video":
            summary_parts.append(f"**分析:** {processed.get('analysis', 'N/A')}")
            if processed.get("transcript"):
                summary_parts.append(f"**音声:** {processed['transcript']}")
            if processed.get("video_info"):
                info = processed["video_info"]
                summary_parts.append(f"**動画情報:** {info.get('duration', 0):.1f}秒, {info.get('resolution', 'N/A')}")

        elif "error" in processed:
            summary_parts.append(f"**エラー:** {processed['error']}")

    result = {
        "ok": True,
        "summary": "\n".join(summary_parts),
        "sources": integration_result["sources"],
        "error": None,
    }

    logger.info("Multimodal summarization completed")

    return result


# ===== CLI Entry Point =====

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Multimodal Integrator CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # integrate
    integrate_parser = subparsers.add_parser("integrate", help="Integrate multiple inputs")
    integrate_parser.add_argument("inputs", nargs="+", help="Input files/paths")
    integrate_parser.add_argument("--chat-id", help="Telegram chat ID for MISO")

    # query
    query_parser = subparsers.add_parser("query", help="Query with multimodal inputs")
    query_parser.add_argument("inputs", nargs="+", help="Input files/paths")
    query_parser.add_argument("prompt", help="Query for LLM")
    query_parser.add_argument("--chat-id", help="Telegram chat ID for MISO")
    query_parser.add_argument("--model", help="Model name")

    # auto-process
    auto_parser = subparsers.add_parser("auto", help="Auto-process a file")
    auto_parser.add_argument("file", help="File to process")

    # summarize
    summary_parser = subparsers.add_parser("summarize", help="Summarize multimodal inputs")
    summary_parser.add_argument("inputs", nargs="+", help="Input files/paths")
    summary_parser.add_argument("--chat-id", help="Telegram chat ID for MISO")

    args = parser.parse_args()

    result = {}

    if args.command == "integrate":
        result = integrate_inputs(args.inputs, args.chat_id)
        if result["ok"]:
            print("=== Integration Complete ===")
            print(f"Processed {len(result['sources'])} inputs")
            print("\n--- Sources ---")
            for source in result["sources"]:
                print(f"  {source['index'] + 1}. {source['type'].upper()}: {source['content_preview']}")
            print("\n--- Summary ---")
            print(result["context"]["summary"])
        else:
            print(f"Error: {result['error']}")

    elif args.command == "query":
        result = multimodal_query(args.inputs, args.prompt, args.chat_id, args.model)
        if result["ok"]:
            print("=== Query Result ===")
            print(result["response"])
        else:
            print(f"Error: {result['error']}")

    elif args.command == "auto":
        result = auto_process(args.file)
        if result["ok"]:
            print(f"=== Auto-Process Result ({result['type']}) ===")
            print(json.dumps(result["result"], indent=2, ensure_ascii=False))
        else:
            print(f"Error: {result['error']}")

    elif args.command == "summarize":
        result = summarize_multimodal(args.inputs, args.chat_id)
        if result["ok"]:
            print("=== Multimodal Summary ===")
            print(result["summary"])
        else:
            print(f"Error: {result['error']}")

    import sys
    sys.exit(0 if result.get("ok", True) else 1)


if __name__ == "__main__":
    main()

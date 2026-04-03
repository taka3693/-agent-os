#!/usr/bin/env python3
"""Multimodal CLI"""
from __future__ import annotations
import argparse
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Dynamic imports to avoid circular dependencies
try:
    multimodal_input = importlib.import_module("ops.multimodal_input")
    detect_input_type = multimodal_input.detect_input_type
    load_file_content = multimodal_input.load_file_content
except ImportError:
    detect_input_type = None
    load_file_content = None

try:
    vision_processor = importlib.import_module("ops.vision_processor")
    analyze_image = vision_processor.analyze_image
    analyze_image_fallback = vision_processor.analyze_image_fallback
except ImportError:
    analyze_image = None
    analyze_image_fallback = None

try:
    output_generator = importlib.import_module("ops.output_generator")
    generate_mermaid_flowchart = output_generator.generate_mermaid_flowchart
    generate_ascii_chart = output_generator.generate_ascii_chart
    generate_diagram_from_description = output_generator.generate_diagram_from_description
except ImportError:
    generate_mermaid_flowchart = None
    generate_ascii_chart = None
    generate_diagram_from_description = None


def cmd_detect(args):
    result = detect_input_type(args.path)
    print(f"Path: {args.path}")
    print(f"Type: {result['type']}")
    print(f"Format: {result['format']}")
    return 0


def cmd_analyze(args):
    print(f"Analyzing: {args.image_path}")
    result = analyze_image_fallback(args.image_path, args.prompt or "詳しく説明")
    if result["ok"]:
        print(f"\n{result['analysis']}")
    else:
        print(f"Error: {result['error']}")
    return 0


def cmd_chart(args):
    data = json.loads(args.data)
    result = generate_ascii_chart(args.title, data, args.type)
    if result["ok"]:
        print(result["chart"])
    return 0


def cmd_suggest(args):
    result = generate_diagram_from_description(args.description)
    print(f"Suggested type: {result['suggestion']}")
    if result.get("template"):
        print(f"\n```mermaid\n{result['template']['code']}\n```")
    return 0


# ===== New commands =====

def cmd_transcribe(args):
    try:
        audio_processor = importlib.import_module("ops.audio_processor")
        transcribe_audio = audio_processor.transcribe_audio
    except ImportError:
        print("Error: audio_processor not available")
        return 1

    print(f"Transcribing audio: {args.audio_path}")
    result = transcribe_audio(args.audio_path, language=args.language)

    if result["ok"]:
        print(f"\n=== Transcription ({result['language']}) ===")
        print(result["text"])
        print(f"\nDuration: {result.get('duration', 0):.1f}s")
    else:
        print(f"Error: {result['error']}")
    return 0


def cmd_speak(args):
    try:
        audio_processor = importlib.import_module("ops.audio_processor")
        synthesize_speech = audio_processor.synthesize_speech
    except ImportError:
        print("Error: audio_processor not available")
        return 1

    print(f"Synthesizing speech: {len(args.text)} chars -> {args.output_path}")
    result = synthesize_speech(args.text, args.output_path, voice=args.voice)

    if result["ok"]:
        print(f"✓ Speech synthesized: {result['path']} ({result.get('duration', 0):.1f}s)")
    else:
        print(f"Error: {result['error']}")
    return 0


def cmd_video_info(args):
    try:
        video_processor = importlib.import_module("ops.video_processor")
        get_video_info = video_processor.get_video_info
    except ImportError:
        print("Error: video_processor not available")
        return 1

    print(f"Getting video info: {args.video_path}")
    result = get_video_info(args.video_path)

    if result["ok"]:
        print(f"\n=== Video Information ===")
        print(f"Format: {result['format']}")
        print(f"Duration: {result['duration']:.2f}s")
        print(f"Resolution: {result['resolution']}")
        print(f"FPS: {result['fps']:.2f}")
        print(f"Codec: {result['codec']}")
        print(f"Has audio: {'Yes' if result['has_audio'] else 'No'}")
    else:
        print(f"Error: {result['error']}")
    return 0


def cmd_video_analyze(args):
    try:
        video_processor = importlib.import_module("ops.video_processor")
        analyze_video = video_processor.analyze_video
    except ImportError:
        print("Error: video_processor not available")
        return 1

    print(f"Analyzing video: {args.video_path}")
    result = analyze_video(
        args.video_path,
        prompt=args.prompt or "この動画を説明して",
        frame_interval=args.interval,
        max_frames=args.max_frames,
        transcribe_audio=not args.no_audio
    )

    if result["ok"]:
        print(f"\n=== Video Analysis ===")
        print(result["analysis"])
        print(f"\n--- Details ---")
        print(f"Frames analyzed: {result['frames_analyzed']}")
        print(f"Audio transcribed: {'Yes' if result.get('transcript') else 'No'}")
        if result.get("video_info"):
            info = result["video_info"]
            print(f"Video: {info.get('duration', 0):.1f}s, {info.get('resolution')}")
    else:
        print(f"Error: {result['error']}")
    return 0


def cmd_integrate(args):
    try:
        multimodal_integrator = importlib.import_module("ops.multimodal_integrator")
        multimodal_query = multimodal_integrator.multimodal_query
    except ImportError:
        print("Error: multimodal_integrator not available")
        return 1

    print(f"Integrating {len(args.inputs)} inputs...")
    prompt = args.prompt or "これらの入力を説明してください"

    result = multimodal_query(
        args.inputs,
        prompt=prompt,
        chat_id=args.chat_id,
        model=args.model
    )

    if result["ok"]:
        print(f"\n=== Multimodal Query Result ===")
        print(result["response"])
        print(f"\n--- Sources ({len(result['sources'])}) ---")
        for source in result["sources"]:
            print(f"  {source['index'] + 1}. {source['type'].upper()}: {source['content_preview']}")
    else:
        print(f"Error: {result['error']}")
    return 0


def cmd_auto(args):
    try:
        multimodal_integrator = importlib.import_module("ops.multimodal_integrator")
        auto_process = multimodal_integrator.auto_process
    except ImportError:
        print("Error: multimodal_integrator not available")
        return 1

    print(f"Auto-processing: {args.file_path}")
    result = auto_process(args.file_path)

    if result["ok"]:
        print(f"\n=== Auto-Process Result ({result['type'].upper()}) ===")
        print(json.dumps(result["result"], indent=2, ensure_ascii=False))
    else:
        print(f"Error: {result['error']}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Multimodal Processing")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Existing commands
    p = subparsers.add_parser("detect")
    p.add_argument("path")
    p.set_defaults(func=cmd_detect)

    p = subparsers.add_parser("analyze")
    p.add_argument("image_path")
    p.add_argument("--prompt", default=None)
    p.set_defaults(func=cmd_analyze)

    p = subparsers.add_parser("chart")
    p.add_argument("title")
    p.add_argument("data")
    p.add_argument("--type", default="horizontal_bar")
    p.set_defaults(func=cmd_chart)

    p = subparsers.add_parser("suggest")
    p.add_argument("description")
    p.set_defaults(func=cmd_suggest)

    # New commands - Audio
    p = subparsers.add_parser("transcribe", help="Transcribe audio to text")
    p.add_argument("audio_path", help="Path to audio file")
    p.add_argument("--language", default="ja", help="Language code")
    p.set_defaults(func=cmd_transcribe)

    p = subparsers.add_parser("speak", help="Synthesize text to speech")
    p.add_argument("text", help="Text to synthesize")
    p.add_argument("output_path", help="Output audio file path")
    p.add_argument("--voice", default="default", help="Voice name")
    p.set_defaults(func=cmd_speak)

    # New commands - Video
    p = subparsers.add_parser("video-info", help="Get video information")
    p.add_argument("video_path", help="Path to video file")
    p.set_defaults(func=cmd_video_info)

    p = subparsers.add_parser("video-analyze", help="Analyze video content")
    p.add_argument("video_path", help="Path to video file")
    p.add_argument("--prompt", default="この動画を説明して", help="Analysis prompt")
    p.add_argument("--interval", type=float, default=3.0, help="Frame interval in seconds")
    p.add_argument("--max-frames", type=int, default=5, help="Max frames to analyze")
    p.add_argument("--no-audio", action="store_true", help="Skip audio transcription")
    p.set_defaults(func=cmd_video_analyze)

    # New commands - Multimodal
    p = subparsers.add_parser("integrate", help="Integrate multiple multimodal inputs and query")
    p.add_argument("inputs", nargs="+", help="Input files/paths (text, image, audio, video)")
    p.add_argument("--prompt", help="Query for LLM")
    p.add_argument("--chat-id", help="Telegram chat ID for MISO")
    p.add_argument("--model", help="Model name")
    p.set_defaults(func=cmd_integrate)

    p = subparsers.add_parser("auto", help="Auto-process a file (detect type and process)")
    p.add_argument("file_path", help="File to process")
    p.set_defaults(func=cmd_auto)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Multimodal CLI"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ops.multimodal_input import detect_input_type, load_file_content
from ops.vision_processor import analyze_image, analyze_image_fallback
from ops.output_generator import (
    generate_mermaid_flowchart,
    generate_ascii_chart,
    generate_diagram_from_description,
)


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


def main():
    parser = argparse.ArgumentParser(description="Multimodal Processing")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
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
    
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

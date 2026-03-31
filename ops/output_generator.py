"""Output Generator - 図/グラフの生成

Mermaid図、チャート、ダイアグラム等を生成する。
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"


def ensure_output_dir():
    OUTPUT_DIR.mkdir(exist_ok=True)


def generate_mermaid_flowchart(
    title: str,
    nodes: List[Dict[str, str]],
    edges: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Mermaidフローチャートを生成
    
    Args:
        title: 図のタイトル
        nodes: [{"id": "A", "label": "Start"}]
        edges: [{"from": "A", "to": "B", "label": "next"}]
    """
    lines = ["flowchart TD"]
    
    # ノード定義
    for node in nodes:
        node_id = node["id"]
        label = node.get("label", node_id)
        shape = node.get("shape", "rect")  # rect, round, diamond, circle
        
        if shape == "round":
            lines.append(f"    {node_id}({label})")
        elif shape == "diamond":
            lines.append(f"    {node_id}{{{label}}}")
        elif shape == "circle":
            lines.append(f"    {node_id}(({label}))")
        else:
            lines.append(f"    {node_id}[{label}]")
    
    # エッジ定義
    for edge in edges:
        from_id = edge["from"]
        to_id = edge["to"]
        label = edge.get("label", "")
        
        if label:
            lines.append(f"    {from_id} -->|{label}| {to_id}")
        else:
            lines.append(f"    {from_id} --> {to_id}")
    
    mermaid_code = "\n".join(lines)
    
    return {
        "ok": True,
        "type": "mermaid",
        "subtype": "flowchart",
        "title": title,
        "code": mermaid_code,
    }


def generate_mermaid_sequence(
    title: str,
    participants: List[str],
    messages: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Mermaidシーケンス図を生成
    
    Args:
        participants: ["User", "System", "Database"]
        messages: [{"from": "User", "to": "System", "message": "Request"}]
    """
    lines = ["sequenceDiagram"]
    
    # 参加者定義
    for p in participants:
        lines.append(f"    participant {p}")
    
    # メッセージ
    for msg in messages:
        from_p = msg["from"]
        to_p = msg["to"]
        message = msg["message"]
        arrow = msg.get("arrow", "->>")  # ->>, -->, -x, --x
        
        lines.append(f"    {from_p}{arrow}{to_p}: {message}")
    
    mermaid_code = "\n".join(lines)
    
    return {
        "ok": True,
        "type": "mermaid",
        "subtype": "sequence",
        "title": title,
        "code": mermaid_code,
    }


def generate_mermaid_gantt(
    title: str,
    tasks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Mermaidガントチャートを生成
    
    Args:
        tasks: [{"name": "Task1", "start": "2024-01-01", "duration": "7d", "section": "Phase1"}]
    """
    lines = [
        "gantt",
        f"    title {title}",
        "    dateFormat YYYY-MM-DD",
    ]
    
    current_section = None
    for task in tasks:
        section = task.get("section")
        if section and section != current_section:
            lines.append(f"    section {section}")
            current_section = section
        
        name = task["name"]
        start = task.get("start", "")
        duration = task.get("duration", "7d")
        
        if start:
            lines.append(f"    {name}: {start}, {duration}")
        else:
            lines.append(f"    {name}: {duration}")
    
    mermaid_code = "\n".join(lines)
    
    return {
        "ok": True,
        "type": "mermaid",
        "subtype": "gantt",
        "title": title,
        "code": mermaid_code,
    }


def generate_ascii_chart(
    title: str,
    data: List[Dict[str, Any]],
    chart_type: str = "bar",
) -> Dict[str, Any]:
    """ASCIIチャートを生成（外部依存なし）
    
    Args:
        data: [{"label": "A", "value": 50}]
        chart_type: "bar" | "horizontal_bar"
    """
    if not data:
        return {"ok": False, "error": "No data provided"}
    
    max_value = max(d["value"] for d in data)
    max_label_len = max(len(str(d["label"])) for d in data)
    
    lines = [f"=== {title} ===", ""]
    
    if chart_type == "horizontal_bar":
        bar_width = 40
        for d in data:
            label = str(d["label"]).ljust(max_label_len)
            value = d["value"]
            bar_len = int((value / max_value) * bar_width) if max_value > 0 else 0
            bar = "█" * bar_len
            lines.append(f"{label} | {bar} {value}")
    
    else:  # vertical bar
        height = 10
        for row in range(height, 0, -1):
            threshold = (row / height) * max_value
            row_chars = []
            for d in data:
                if d["value"] >= threshold:
                    row_chars.append(" █ ")
                else:
                    row_chars.append("   ")
            lines.append("".join(row_chars))
        
        # ラベル行
        lines.append("-" * (len(data) * 3))
        labels = [str(d["label"])[:3].center(3) for d in data]
        lines.append("".join(labels))
    
    chart = "\n".join(lines)
    
    return {
        "ok": True,
        "type": "ascii_chart",
        "subtype": chart_type,
        "title": title,
        "chart": chart,
    }


def save_output(
    content: str,
    filename: str,
    format: str = "md",
) -> Dict[str, Any]:
    """出力をファイルに保存"""
    ensure_output_dir()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_filename = f"{timestamp}_{filename}.{format}"
    output_path = OUTPUT_DIR / full_filename
    
    output_path.write_text(content, encoding="utf-8")
    
    return {
        "ok": True,
        "path": str(output_path),
        "filename": full_filename,
    }


def generate_diagram_from_description(description: str) -> Dict[str, Any]:
    """説明文からダイアグラムを自動生成（ルールベース）"""
    description_lower = description.lower()
    
    # フロー/プロセス系
    if any(w in description_lower for w in ["flow", "フロー", "process", "プロセス", "手順"]):
        return {
            "suggestion": "flowchart",
            "template": generate_mermaid_flowchart(
                "Process Flow",
                [
                    {"id": "start", "label": "開始", "shape": "round"},
                    {"id": "step1", "label": "ステップ1"},
                    {"id": "step2", "label": "ステップ2"},
                    {"id": "end", "label": "終了", "shape": "round"},
                ],
                [
                    {"from": "start", "to": "step1"},
                    {"from": "step1", "to": "step2"},
                    {"from": "step2", "to": "end"},
                ],
            ),
        }
    
    # シーケンス/対話系
    if any(w in description_lower for w in ["sequence", "シーケンス", "対話", "通信", "api"]):
        return {
            "suggestion": "sequence",
            "template": generate_mermaid_sequence(
                "Sequence Diagram",
                ["Client", "Server", "Database"],
                [
                    {"from": "Client", "to": "Server", "message": "Request"},
                    {"from": "Server", "to": "Database", "message": "Query"},
                    {"from": "Database", "to": "Server", "message": "Result"},
                    {"from": "Server", "to": "Client", "message": "Response"},
                ],
            ),
        }
    
    # スケジュール系
    if any(w in description_lower for w in ["schedule", "スケジュール", "gantt", "ガント", "計画"]):
        return {
            "suggestion": "gantt",
            "template": generate_mermaid_gantt(
                "Project Schedule",
                [
                    {"name": "Phase 1", "duration": "7d", "section": "Planning"},
                    {"name": "Phase 2", "duration": "14d", "section": "Development"},
                    {"name": "Phase 3", "duration": "7d", "section": "Testing"},
                ],
            ),
        }
    
    return {
        "suggestion": "unknown",
        "message": "Could not determine diagram type from description",
    }

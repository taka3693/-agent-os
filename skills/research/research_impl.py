#!/usr/bin/env python3
"""Research skill implementation with OpenClaw AI integration."""
import json
import subprocess
from pathlib import Path
from typing import Dict, Any


def _call_openclaw(query: str, system_hint: str = "") -> Dict[str, Any]:
    """Call OpenClaw agent and return response."""
    prompt = f"{system_hint}\n\n{query}" if system_hint else query
    
    try:
        result = subprocess.run(
            ["openclaw", "agent", "--agent", "main", "--message", prompt, "--json"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        if result.returncode != 0:
            return {"error": result.stderr or "OpenClaw call failed", "ok": False}
        
        output = result.stdout.strip()
        lines = output.split("\n")
        
        # Find JSON start
        json_start = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("{"):
                json_start = i
                break
        
        json_str = "\n".join(lines[json_start:])
        data = json.loads(json_str)
        
        # Handle both formats: direct payloads or nested under result
        if "result" in data:
            payloads = data.get("result", {}).get("payloads", [])
            model = data.get("result", {}).get("meta", {}).get("agentMeta", {}).get("model", "unknown")
        else:
            payloads = data.get("payloads", [])
            model = data.get("meta", {}).get("agentMeta", {}).get("model", "unknown")
        
        text = payloads[0].get("text", "") if payloads else ""
        
        return {
            "ok": True,
            "text": text,
            "model": model,
        }
    except subprocess.TimeoutExpired:
        return {"error": "OpenClaw timeout", "ok": False}
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "ok": False}
    except Exception as e:
        return {"error": str(e), "ok": False}


def run_research(query: str) -> dict:
    """Run research task using OpenClaw AI."""
    q = query.strip() if isinstance(query, str) else ""
    if not q:
        raise ValueError("query is required")
    
    system_hint = "リサーチアシスタントとして、簡潔に調査結果をまとめてください。"
    result = _call_openclaw(q, system_hint)
    
    if not result.get("ok"):
        return {
            "summary": f"調査失敗: {result.get('error', 'unknown error')}",
            "findings": [],
            "error": result.get("error"),
        }
    
    return {
        "summary": result.get("text", ""),
        "findings": [f"モデル: {result.get('model', 'unknown')}"],
        "ai_response": True,
    }

# Aliases for consistent interface
run = run_research
execute = run_research


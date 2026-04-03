#!/usr/bin/env python3
"""大きなファイルを分割して処理 - コンテキストオーバーフロー対策"""

import os
import sys
from pathlib import Path
from typing import List, Generator

MAX_CHUNK_SIZE = 50000  # 50KB (約12500トークン相当)
MAX_LINES_PER_CHUNK = 500

def estimate_tokens(text: str) -> int:
    """トークン数を概算（1トークン≒4文字）"""
    return len(text) // 4

def split_by_size(file_path: str, max_bytes: int = MAX_CHUNK_SIZE) -> Generator[str, None, None]:
    """ファイルをサイズで分割"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        chunk = []
        chunk_size = 0
        
        for line in f:
            line_size = len(line.encode('utf-8'))
            
            if chunk_size + line_size > max_bytes and chunk:
                yield ''.join(chunk)
                chunk = []
                chunk_size = 0
            
            chunk.append(line)
            chunk_size += line_size
        
        if chunk:
            yield ''.join(chunk)

def split_by_lines(file_path: str, max_lines: int = MAX_LINES_PER_CHUNK) -> Generator[str, None, None]:
    """ファイルを行数で分割"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        chunk = []
        
        for line in f:
            chunk.append(line)
            
            if len(chunk) >= max_lines:
                yield ''.join(chunk)
                chunk = []
        
        if chunk:
            yield ''.join(chunk)

def analyze_file(file_path: str) -> dict:
    """ファイルを分析"""
    path = Path(file_path)
    
    if not path.exists():
        return {"ok": False, "error": "File not found"}
    
    size_bytes = path.stat().st_size
    size_kb = size_bytes / 1024
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    lines = content.count('\n') + 1
    tokens = estimate_tokens(content)
    
    needs_split = size_kb > (MAX_CHUNK_SIZE / 1024) or lines > MAX_LINES_PER_CHUNK
    
    return {
        "ok": True,
        "file": str(path),
        "size_kb": round(size_kb, 1),
        "lines": lines,
        "estimated_tokens": tokens,
        "needs_split": needs_split,
        "recommended_chunks": max(1, int(size_bytes / MAX_CHUNK_SIZE) + 1) if needs_split else 1
    }

def split_file(file_path: str, output_dir: str = None) -> List[str]:
    """ファイルを分割して保存"""
    path = Path(file_path)
    
    if output_dir is None:
        output_dir = path.parent / f"{path.stem}_chunks"
    
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    chunks = list(split_by_size(file_path))
    saved_files = []
    
    for i, chunk in enumerate(chunks, 1):
        chunk_file = output_path / f"{path.stem}_part{i:03d}{path.suffix}"
        with open(chunk_file, 'w', encoding='utf-8') as f:
            f.write(chunk)
        saved_files.append(str(chunk_file))
    
    return saved_files

def main():
    if len(sys.argv) < 2:
        print("Usage: file_splitter.py <file_path> [analyze|split]")
        print("\nExamples:")
        print("  file_splitter.py large_file.py analyze")
        print("  file_splitter.py large_file.py split")
        return
    
    file_path = sys.argv[1]
    action = sys.argv[2] if len(sys.argv) > 2 else "analyze"
    
    if action == "analyze":
        result = analyze_file(file_path)
        print(f"\n📁 File Analysis: {file_path}")
        print(f"   Size: {result.get('size_kb', 0)} KB")
        print(f"   Lines: {result.get('lines', 0)}")
        print(f"   Est. Tokens: {result.get('estimated_tokens', 0)}")
        print(f"   Needs Split: {'Yes' if result.get('needs_split') else 'No'}")
        if result.get('needs_split'):
            print(f"   Recommended Chunks: {result.get('recommended_chunks')}")
    
    elif action == "split":
        analysis = analyze_file(file_path)
        if not analysis.get('needs_split'):
            print(f"File is small enough ({analysis.get('size_kb')} KB), no split needed.")
            return
        
        files = split_file(file_path)
        print(f"\n✅ Split into {len(files)} chunks:")
        for f in files:
            print(f"   - {f}")

if __name__ == "__main__":
    main()

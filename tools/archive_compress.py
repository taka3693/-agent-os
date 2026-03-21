from __future__ import annotations

import gzip
import shutil
import time
from pathlib import Path

ARCHIVE = Path.home() / ".openclaw/agents/main/sessions_archive"
AGE_SECONDS = 7 * 24 * 3600

def compress_file(p: Path) -> None:
    gz = p.with_suffix(p.suffix + ".gz")
    with p.open("rb") as f_in:
        with gzip.open(gz, "wb", compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)
    p.unlink()

def run() -> None:
    now = time.time()

    for p in ARCHIVE.rglob("*.jsonl"):
        try:
            if not p.is_file():
                continue

            age = now - p.stat().st_mtime
            if age < AGE_SECONDS:
                continue

            compress_file(p)

        except Exception as e:
            print("skip", p, e)

if __name__ == "__main__":
    run()

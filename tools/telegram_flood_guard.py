from __future__ import annotations

def normalize_outbound_text(
    text: object,
    *,
    max_chars: int = 3000,
    max_lines: int = 40,
) -> str:
    if text is None:
        s = "internal: empty response prevented"
    else:
        s = str(text).replace("\r\n", "\n").replace("\r", "\n").strip()
        if not s:
            s = "internal: empty response prevented"

    lines = [line.rstrip() for line in s.split("\n")]

    compact = []
    blank_run = 0
    for line in lines:
        if line.strip():
            blank_run = 0
            compact.append(line)
        else:
            blank_run += 1
            if blank_run <= 1:
                compact.append("")

    if len(compact) > max_lines:
        compact = compact[:max_lines]
        compact.append("")
        compact.append("[truncated: too many lines]")

    out = "\n".join(compact).strip()
    if len(out) > max_chars:
        out = out[: max_chars - 28].rstrip() + "\n\n[truncated: too long]"

    return out if out.strip() else "internal: empty response prevented"

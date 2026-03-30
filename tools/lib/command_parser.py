from __future__ import annotations

from tools.lib.request_models import CommandEnvelope


def parse_command(raw_text: str) -> CommandEnvelope:
    raw = "" if raw_text is None else str(raw_text).strip()
    lower = raw.lower()

    if lower.startswith("aos router "):
        return CommandEnvelope(
            kind="router",
            raw_command=raw,
            query=raw[11:].strip(),
        )

    if lower.startswith("aos route "):
        return CommandEnvelope(
            kind="router",
            raw_command=raw,
            query=raw[10:].strip(),
        )

    if lower.startswith("aos json "):
        validate_only = '"validate_only":true' in lower or '"validate_only": true' in lower
        return CommandEnvelope(
            kind="json_batch",
            raw_command=raw,
            query=raw[9:].strip(),
            validate_only=validate_only,
        )

    return CommandEnvelope(
        kind="raw",
        raw_command=raw,
        query=raw,
    )

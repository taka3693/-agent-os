from __future__ import annotations

from datetime import datetime, timezone


def _parse_iso_utc(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def should_emit_by_cooldown(
    *,
    now_iso: str,
    last_emitted_at: str | None,
    cooldown_seconds: int,
) -> bool:
    if cooldown_seconds <= 0:
        return True

    if not last_emitted_at:
        return True

    now_dt = _parse_iso_utc(now_iso)
    last_dt = _parse_iso_utc(last_emitted_at)

    if now_dt is None or last_dt is None:
        return True

    elapsed = (now_dt - last_dt).total_seconds()
    return elapsed >= cooldown_seconds

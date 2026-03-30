from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

JsonDict = Dict[str, Any]


@dataclass
class SnapshotCandidate:
    path: Path
    kind: str   # latest | versioned | fallback
    score: int


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _rollback_dir(base_dir: Path) -> Path:
    d = Path(base_dir) / "state" / "rollback"
    d.mkdir(parents=True, exist_ok=True)
    return d


def latest_path(base_dir: Path) -> Path:
    return _rollback_dir(base_dir) / "rollback.latest.json"


def fallback_path(base_dir: Path) -> Path:
    return _rollback_dir(base_dir) / "rollback.fallback.json"


def versioned_path(base_dir: Path, *, ts: Optional[str] = None) -> Path:
    stamp = ts or _utc_ts()
    return _rollback_dir(base_dir) / f"rollback.{stamp}.json"


def _safe_read_json(path: Path) -> Optional[JsonDict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _safe_write_json(path: Path, payload: JsonDict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def build_snapshot_payload(
    payload: JsonDict,
    *,
    source_action: str = "deploy",
    note: Optional[str] = None,
) -> JsonDict:
    out = dict(payload)
    meta = dict(out.get("_rollback_meta") or {})
    meta.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    meta["source_action"] = source_action
    if note:
        meta["note"] = note
    out["_rollback_meta"] = meta
    return out


def write_snapshot(
    base_dir: Path,
    payload: JsonDict,
    *,
    source_action: str = "deploy",
    note: Optional[str] = None,
    keep_last: int = 20,
) -> JsonDict:
    rb_dir = _rollback_dir(base_dir)
    latest = latest_path(base_dir)
    fallback = fallback_path(base_dir)
    versioned = versioned_path(base_dir)

    snap = build_snapshot_payload(payload, source_action=source_action, note=note)

    _safe_write_json(versioned, snap)

    prev_latest = _safe_read_json(latest)
    if prev_latest is not None:
        _safe_write_json(fallback, prev_latest)
    elif not fallback.exists():
        _safe_write_json(fallback, snap)

    _safe_write_json(latest, snap)

    versioned_files = sorted(
        rb_dir.glob("rollback.20*.json"),
        key=lambda p: p.name,
        reverse=True,
    )
    for old in versioned_files[keep_last:]:
        try:
            old.unlink()
        except Exception:
            pass

    return {
        "ok": True,
        "latest": str(latest),
        "versioned": str(versioned),
        "fallback": str(fallback),
        "kept_versioned": min(len(versioned_files), keep_last),
    }


def default_snapshot_validator(payload: JsonDict) -> bool:
    if not isinstance(payload, dict):
        return False

    if (
        "executed_action" not in payload
        and "next_action" not in payload
        and "deploy_artifact" not in payload
    ):
        return False

    meta = payload.get("_rollback_meta")
    if meta is not None and not isinstance(meta, dict):
        return False

    return True


def list_snapshot_candidates(base_dir: Path) -> List[SnapshotCandidate]:
    rb_dir = _rollback_dir(base_dir)
    out: List[SnapshotCandidate] = []

    latest = latest_path(base_dir)
    fallback = fallback_path(base_dir)

    if latest.exists():
        out.append(SnapshotCandidate(latest, "latest", 300))

    versioned_files = sorted(
        rb_dir.glob("rollback.20*.json"),
        key=lambda p: p.name,
        reverse=True,
    )
    score = 250
    for p in versioned_files:
        out.append(SnapshotCandidate(p, "versioned", score))
        score -= 1

    if fallback.exists():
        out.append(SnapshotCandidate(fallback, "fallback", 100))

    return out


def inspect_latest_snapshot(
    base_dir: Path,
    *,
    validator: Optional[Callable[[JsonDict], bool]] = None,
) -> Dict[str, Any]:
    check = validator or default_snapshot_validator
    latest = latest_path(base_dir)
    if not latest.exists():
        return {
            "ok": False,
            "path": str(latest),
            "reason": "latest_missing",
            "payload": None,
        }

    payload = _safe_read_json(latest)
    if payload is None:
        return {
            "ok": False,
            "path": str(latest),
            "reason": "latest_unreadable",
            "payload": None,
        }

    try:
        valid = check(payload)
    except Exception:
        valid = False

    if not valid:
        return {
            "ok": False,
            "path": str(latest),
            "reason": "latest_invalid",
            "payload": payload,
        }

    return {
        "ok": True,
        "path": str(latest),
        "reason": "latest_valid",
        "payload": payload,
    }

def repair_latest_from_best_snapshot(
    base_dir: Path,
    *,
    validator: Optional[Callable[[JsonDict], bool]] = None,
) -> Dict[str, Any]:
    latest_info = inspect_latest_snapshot(base_dir, validator=validator)
    if latest_info.get("ok"):
        return {
            "ok": True,
            "repaired": False,
            "reason": "latest_already_valid",
            "latest_path": latest_info.get("path"),
        }

    snap = load_best_snapshot(base_dir, validator=validator)
    if not snap.get("ok"):
        return {
            "ok": False,
            "repaired": False,
            "reason": "no_valid_snapshot_for_repair",
            "latest_reason": latest_info.get("reason"),
            "tried": snap.get("tried", []),
        }

    selected_kind = snap.get("selected_kind")
    if selected_kind == "latest":
        return {
            "ok": False,
            "repaired": False,
            "reason": "latest_selected_but_invalid",
            "latest_reason": latest_info.get("reason"),
            "selected_path": snap.get("selected_path"),
            "selected_kind": selected_kind,
        }

    latest = latest_path(base_dir)
    payload = snap.get("payload") or {}
    _safe_write_json(latest, payload)

    return {
        "ok": True,
        "repaired": True,
        "reason": "latest_repaired_from_snapshot",
        "latest_reason": latest_info.get("reason"),
        "latest_path": str(latest),
        "selected_path": snap.get("selected_path"),
        "selected_kind": selected_kind,
    }

def load_best_snapshot(
    base_dir: Path,
    *,
    validator: Optional[Callable[[JsonDict], bool]] = None,
) -> Dict[str, Any]:
    check = validator or default_snapshot_validator
    candidates = list_snapshot_candidates(base_dir)

    ordered = sorted(
        candidates,
        key=lambda c: (
            0 if c.kind == "latest" else 1 if c.kind == "versioned" else 2,
            -c.score,
            c.path.name,
        ),
    )

    tried = []
    for c in ordered:
        tried.append(str(c.path))
        payload = _safe_read_json(c.path)
        if payload is None:
            continue
        try:
            if check(payload):
                return {
                    "ok": True,
                    "payload": payload,
                    "selected_path": str(c.path),
                    "selected_kind": c.kind,
                    "tried": tried,
                }
        except Exception:
            continue

    return {
        "ok": False,
        "payload": None,
        "selected_path": None,
        "selected_kind": None,
        "tried": tried,
    }


def save_last_known_good(name: str, payload: JsonDict, *, base_dir: Optional[Path] = None) -> JsonDict:
    """
    DEPRECATED: backward-compatible wrapper for older code paths.

    New code must call write_snapshot(...) directly and normalize
    rollback_info via the caller-side helper.
    Existing callers expect rollback_info-like metadata.
    """
    root = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parents[2]

    note = f"save_last_known_good:{name}"
    meta = write_snapshot(
        root,
        payload,
        source_action=name,
        note=note,
    )

    return {
        "ok": True,
        "name": name,
        "latest": meta.get("latest"),
        "versioned": meta.get("versioned"),
        "fallback": meta.get("fallback"),
        "restored_from": meta.get("latest"),
        "snapshot_kind": "latest",
    }

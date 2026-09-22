"""Persist last job params/stats under dataset .caption_state/ for resume."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from caption_batch import __version__
from .discover import state_dir_for

SNAPSHOT_NAME = "job_snapshot.json"
SNAPSHOT_SCHEMA = 1

_write_lock = threading.Lock()

# Params that must never be written to disk
_SECRET_KEYS = {
    "gemini_api_key",
    "openrouter_api_key",
    "api_key",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "GOOGLE_API_KEY",
}


def snapshot_path_for(input_dir: Path, state_dir: Path | None = None) -> Path:
    return state_dir_for(input_dir, state_dir) / SNAPSHOT_NAME


def sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
    if not params:
        return {}
    out: dict[str, Any] = {}
    for k, v in params.items():
        if k in _SECRET_KEYS:
            continue
        if isinstance(k, str) and ("api_key" in k.lower() or k.endswith("_KEY")):
            continue
        out[k] = v
    return out


def write_job_snapshot(
    input_dir: Path,
    *,
    status: str,
    params: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
    started_at: float | None = None,
    finished_at: float | None = None,
    error: str | None = None,
    state_dir: Path | None = None,
    kind: str | None = None,
) -> Path:
    """Atomically write job_snapshot.json. status: running|finished|stopped|error."""
    path = snapshot_path_for(input_dir, state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema": SNAPSHOT_SCHEMA,
        "version": __version__,
        "status": status,
        "params": sanitize_params(params),
        "stats": dict(stats or {}),
        "started_at": started_at,
        "finished_at": finished_at,
        "error": error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if kind is not None:
        payload["kind"] = kind
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    with _write_lock:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return path


def read_job_snapshot(
    input_dir: Path,
    *,
    state_dir: Path | None = None,
) -> dict[str, Any] | None:
    path = snapshot_path_for(input_dir, state_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data

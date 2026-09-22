"""Helpers for settings routes."""
from __future__ import annotations

import re
from pathlib import Path

from caption_batch.run_server import find_project_root

_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

def _upsert_env_file(path: Path, updates: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    order: list[str] = []
    other_lines: list[str] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                other_lines.append(line)
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k in updates:
                existing[k] = updates[k]
                order.append(k)
            else:
                existing[k] = v
                order.append(k)
    for k, v in updates.items():
        if k not in existing:
            order.append(k)
            existing[k] = v
    out: list[str] = []
    seen_keys: set[str] = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                out.append(line)
                continue
            k = line.partition("=")[0].strip()
            if k in updates:
                out.append(f"{k}={updates[k]}")
                seen_keys.add(k)
            else:
                out.append(line)
                seen_keys.add(k)
    for k, v in updates.items():
        if k not in seen_keys:
            out.append(f"{k}={v}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _ui_settings_path() -> Path:
    return find_project_root() / "ui-settings.json"

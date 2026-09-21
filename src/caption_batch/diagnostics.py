"""Thin diagnostics zip (logs + port + env key names; no secret values)."""

from __future__ import annotations

import json
import os
import platform
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from caption_batch import __version__
from caption_batch.logging_utils import flush_logging, get_logger, setup_file_logging
from caption_batch.run_server import find_project_root

log = get_logger(__name__)


def collect_diagnostics(root: Path | None = None) -> dict[str, Any]:
    root = Path(root) if root is not None else find_project_root()
    try:
        setup_file_logging(root / "logs", fresh_latest=False)
    except Exception:
        pass
    flush_logging()

    diag_dir = root / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = diag_dir / f"diagnostics-{stamp}.zip"

    env_names = sorted(
        k
        for k in os.environ
        if any(x in k.upper() for x in ("GEMINI", "GOOGLE", "OPENROUTER", "CAPTION"))
    )
    meta = {
        "tool": "caption_batch",
        "version": __version__,
        "python": sys.version,
        "platform": platform.platform(),
        "cwd": str(Path.cwd()),
        "root": str(root),
        "env_keys_present": env_names,
    }

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("environment.json", json.dumps(meta, indent=2))
        port = root / "port.json"
        if port.is_file():
            zf.write(port, "port.json")
        logs = root / "logs"
        if logs.is_dir():
            for name in ("latest.log", "selfcheck-last.txt"):
                p = logs / name
                if p.is_file():
                    zf.write(p, f"logs/{name}")
            sessions = sorted(
                logs.glob("session-*.log"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if sessions:
                zf.write(sessions[0], f"logs/{sessions[0].name}")

    log.info("diagnostics collected zip=%s", zip_path)
    return {"ok": True, "zip_path": str(zip_path)}


def main() -> None:
    print(json.dumps(collect_diagnostics(), indent=2))


if __name__ == "__main__":
    main()

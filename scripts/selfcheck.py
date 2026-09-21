#!/usr/bin/env python3
"""Thin offline selfcheck: import package + dry-run runner + API health."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> int:
    lines: list[str] = []

    def note(text: str) -> None:
        lines.append(text)
        print(text)

    failed = 0
    note("caption-batch selfcheck")

    try:
        from caption_batch import __version__
        from caption_batch.core.discover import is_done
        from caption_batch.core.prompts import DEFAULT_PROMPT
        from caption_batch.core.runner import run_batch

        assert __version__
        assert len(DEFAULT_PROMPT) > 20
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            root.joinpath("a.png").write_bytes(
                bytes.fromhex(
                    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
                    "0000000c49444154789c63f80f00000101000518d84e0000000049454e44ae426082"
                )
            )
            stats = run_batch(
                provider_name="gemini",
                model="dry",
                input_dir=root,
                dry_run=True,
                workers=1,
            )
            assert stats.total >= 1
            assert not is_done(root / "a.png")
        note("[OK] core dry-run")
    except Exception as exc:
        failed += 1
        note(f"[FAIL] core dry-run: {exc}")

    try:
        from fastapi.testclient import TestClient
        from caption_batch.api.app import app

        client = TestClient(app)
        assert client.get("/api/health").json().get("status") in ("ok", "OK")
        d = client.get("/api/defaults").json()
        assert "prompt" in d
        for path in ("/", "/app.js", "/styles.css"):
            assert client.get(path).status_code == 200
        note("[OK] API/static")
    except Exception as exc:
        failed += 1
        note(f"[FAIL] API/static: {exc}")

    note("RESULT: OK" if not failed else f"RESULT: FAIL ({failed})")
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "selfcheck-last.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

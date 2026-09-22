"""Loader for routes_settings (concat gzip b64 parts)."""
from __future__ import annotations

import base64
import gzip
import pathlib

_dir = pathlib.Path(__file__).parent
_parts = sorted(_dir.glob("routes_settings.py.gz.b64.part*"))
if not _parts:
    raise FileNotFoundError("routes_settings.py.gz.b64.part* missing")
_b64 = "".join(p.read_text(encoding="ascii").strip() for p in _parts)
_code = gzip.decompress(base64.b64decode(_b64))
exec(compile(_code, str(_dir / "routes_settings_impl.py"), "exec"), globals())

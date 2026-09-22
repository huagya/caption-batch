"""Assemble routes_settings from plain text parts (no compression)."""
from __future__ import annotations

import pathlib

_dir = pathlib.Path(__file__).parent
_code = (_dir / "routes_settings.part_a.py.txt").read_text(encoding="utf-8")
_code += (_dir / "routes_settings.part_b.py.txt").read_text(encoding="utf-8")
exec(compile(_code, str(_dir / "routes_settings_impl.py"), "exec"), globals())

"""Loader for routes_settings.py (gzip+base64 sibling). Do not edit; edit routes_settings_src if needed."""
from __future__ import annotations

import base64
import gzip
import pathlib

_b64 = pathlib.Path(__file__).with_name("routes_settings.py.gz.b64").read_text(encoding="ascii").strip()
_code = gzip.decompress(base64.b64decode(_b64))
exec(compile(_code, str(pathlib.Path(__file__).with_name("routes_settings_impl.py")), "exec"), globals())

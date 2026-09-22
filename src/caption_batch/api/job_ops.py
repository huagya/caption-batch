"""Loader for job_ops.py (gzip+base64 sibling). Do not edit; edit job_ops_src if needed."""
from __future__ import annotations

import base64
import gzip
import pathlib

_b64 = pathlib.Path(__file__).with_name("job_ops.py.gz.b64").read_text(encoding="ascii").strip()
_code = gzip.decompress(base64.b64decode(_b64))
exec(compile(_code, str(pathlib.Path(__file__).with_name("job_ops_impl.py")), "exec"), globals())

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo "[ERROR] .venv not found. Run: python -m venv .venv && .venv/bin/pip install -e '.[dev]'"
  exit 1
fi
.venv/bin/python -m caption_batch.diagnostics

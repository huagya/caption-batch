from __future__ import annotations

"""Batch runner public API (re-exports)."""

from .run_batch_impl import (
    ImageResult,
    RunState,
    RunStats,
    _atomic_write_text,
    run_batch,
)
from .runner_progress import ProgressTracker, atomic_write_text, stats_dict

# Prefer progress-module names; keep CLI aliases
_ProgressTracker = ProgressTracker
_stats_dict = stats_dict

__all__ = [
    "ImageResult",
    "ProgressTracker",
    "RunState",
    "RunStats",
    "_ProgressTracker",
    "_atomic_write_text",
    "_stats_dict",
    "atomic_write_text",
    "run_batch",
    "stats_dict",
]

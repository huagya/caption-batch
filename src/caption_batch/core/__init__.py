"""Captioning core: discover, runner, providers, prompts."""

from .prompts import DEFAULT_PROMPT
from .runner import RunStats, run_batch

__all__ = ["DEFAULT_PROMPT", "RunStats", "run_batch"]

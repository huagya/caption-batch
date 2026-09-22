"""Unified thinking_level + Gemini media_resolution helpers.

UI / API values for thinking_level: empty/null, none, minimal, low, medium, high.
Gemini maps none→minimal (Gemini 3.x cannot fully disable thinking).
OpenRouter maps 1:1 to reasoning.effort.
Never set include_thoughts=True for batch caption runs.
"""

from __future__ import annotations

from typing import Any

THINKING_LEVELS = ("none", "minimal", "low", "medium", "high")

# Short / full names accepted for media_resolution
_MEDIA_SHORT = {
    "low": "MEDIA_RESOLUTION_LOW",
    "medium": "MEDIA_RESOLUTION_MEDIUM",
    "high": "MEDIA_RESOLUTION_HIGH",
}
_MEDIA_FULL = {
    "MEDIA_RESOLUTION_LOW": "MEDIA_RESOLUTION_LOW",
    "MEDIA_RESOLUTION_MEDIUM": "MEDIA_RESOLUTION_MEDIUM",
    "MEDIA_RESOLUTION_HIGH": "MEDIA_RESOLUTION_HIGH",
}


def normalize_thinking_level(value: str | None) -> str | None:
    """Return canonical lowercase level or None if empty. Raise ValueError if invalid."""
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v:
        return None
    if v not in THINKING_LEVELS:
        raise ValueError(
            f"thinking_level must be one of {list(THINKING_LEVELS)} or empty, got {value!r}"
        )
    return v


def normalize_media_resolution(value: str | None) -> str | None:
    """Return MEDIA_RESOLUTION_* or None. Accepts short low/medium/high."""
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    key = v.lower()
    if key in _MEDIA_SHORT:
        return _MEDIA_SHORT[key]
    upper = v.upper()
    if upper in _MEDIA_FULL:
        return _MEDIA_FULL[upper]
    raise ValueError(
        "media_resolution must be low|medium|high "
        "(or MEDIA_RESOLUTION_LOW|MEDIUM|HIGH), or empty"
    )


def gemini_thinking_level_for_api(level: str) -> str:
    """Map unified level to Gemini ThinkingLevel name (uppercase).

    ``none`` is mapped to ``MINIMAL`` — Gemini 3.x cannot fully disable thinking;
    on 2.5 Flash a budget of 0 would work, but we keep one path for simplicity.
    """
    if level == "none":
        return "MINIMAL"
    return level.upper()


def build_gemini_thinking_config(thinking_level: str | None) -> Any | None:
    """Build google.genai.types.ThinkingConfig or None.

    Never sets include_thoughts. Never sends both thinking_budget and thinking_level.
    """
    level = normalize_thinking_level(thinking_level)
    if level is None:
        return None
    from google.genai import types

    api_level = gemini_thinking_level_for_api(level)
    # Prefer ThinkingLevel enum when available
    tl_enum = getattr(types, "ThinkingLevel", None)
    if tl_enum is not None:
        enum_val = getattr(tl_enum, api_level, None)
        if enum_val is not None:
            return types.ThinkingConfig(thinking_level=enum_val)
    return types.ThinkingConfig(thinking_level=api_level)


def build_gemini_media_resolution(media_resolution: str | None) -> Any | None:
    """Build types.MediaResolution enum or None."""
    name = normalize_media_resolution(media_resolution)
    if name is None:
        return None
    from google.genai import types

    return getattr(types.MediaResolution, name)


def openrouter_reasoning_effort(thinking_level: str | None) -> str | None:
    """Map unified thinking_level to OpenRouter reasoning.effort string."""
    level = normalize_thinking_level(thinking_level)
    if level is None:
        return None
    # 1:1 mapping including none
    return level


def build_openrouter_reasoning(thinking_level: str | None) -> dict | None:
    """Return {\"effort\": ...} kwargs fragment or None."""
    effort = openrouter_reasoning_effort(thinking_level)
    if effort is None:
        return None
    return {"effort": effort}

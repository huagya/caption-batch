"""Pydantic request bodies and UI settings schema for the API."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from caption_batch.core.image_prep import (
    DEFAULT_IMAGE_FORMAT,
    DEFAULT_IMAGE_PREP_ENABLED,
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_MAX_IMAGE_SIDE,
)

UI_SETTINGS_SCHEMA = 3
UI_SETTINGS_KEYS = (
    "provider",
    "model",
    "folder",
    "workers",
    "limit",
    "overwrite",
    "dry_run",
    "recursive",
    "from_index",
    "temperature",
    "top_p",
    "max_output_tokens",
    "seed",
    "max_image_side",
    "image_prep_enabled",
    "image_format",
    "image_quality",
    "thinking_level",
    "media_resolution",
    "prompt",
    "rate_limit_rpm",
    "few_shot",
    "preview_count",
)
UI_SETTINGS_FORBIDDEN = {
    "gemini_api_key",
    "openrouter_api_key",
    "api_key",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
}


class FewShotItem(BaseModel):
    image: str = Field(..., min_length=1)
    caption: str = Field(..., min_length=1)


class SaveKeysBody(BaseModel):
    gemini_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None


class StartJobBody(BaseModel):
    provider: Literal["gemini", "openrouter"]
    model: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)
    workers: int = 4
    limit: Optional[int] = None
    overwrite: bool = False
    dry_run: bool = False
    recursive: bool = True
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_output_tokens: Optional[int] = 1024
    seed: Optional[int] = None
    max_image_side: int = DEFAULT_MAX_IMAGE_SIDE
    image_prep_enabled: bool = DEFAULT_IMAGE_PREP_ENABLED
    image_format: Literal["jpeg", "webp", "png"] = DEFAULT_IMAGE_FORMAT
    image_quality: int = DEFAULT_IMAGE_QUALITY
    thinking_level: Optional[str] = None
    media_resolution: Optional[str] = None
    prompt: Optional[str] = None
    from_index: bool = False
    rate_limit_rpm: Optional[int] = 0
    few_shot: Optional[list[FewShotItem]] = None


class PreviewJobBody(StartJobBody):
    preview_count: int = 3
    preview_write: bool = True


class UiSettingsBody(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


class ListModelsBody(BaseModel):
    provider: Literal["gemini", "openrouter"]
    vision_only: bool = True
    as_json: bool = False
    contains: Optional[str] = None

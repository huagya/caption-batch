from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..image_prep import (
    DEFAULT_IMAGE_FORMAT,
    DEFAULT_IMAGE_PREP_ENABLED,
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_MAX_IMAGE_SIDE,
)
from ..few_shot import FewShotExample


@dataclass
class CaptionRequest:
    image_path: Path
    prompt: str
    model: str
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = 1024
    seed: int | None = None
    max_image_side: int = DEFAULT_MAX_IMAGE_SIDE
    image_prep_enabled: bool = DEFAULT_IMAGE_PREP_ENABLED
    image_format: Literal["jpeg", "webp", "png"] = DEFAULT_IMAGE_FORMAT
    image_quality: int = DEFAULT_IMAGE_QUALITY
    thinking_level: str | None = None
    media_resolution: str | None = None
    few_shot: list[FewShotExample] = field(default_factory=list)


class Provider(ABC):
    name: str

    @abstractmethod
    def caption(self, req: CaptionRequest) -> str:
        """Return caption text or raise on failure."""

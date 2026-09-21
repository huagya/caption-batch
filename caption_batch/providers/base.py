from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from ..image_prep import DEFAULT_MAX_IMAGE_SIDE


@dataclass
class CaptionRequest:
    image_path: Path
    prompt: str
    model: str
    temperature: float | None = 0.2
    max_output_tokens: int | None = 1024
    max_image_side: int = DEFAULT_MAX_IMAGE_SIDE


class Provider(ABC):
    name: str

    @abstractmethod
    def caption(self, req: CaptionRequest) -> str:
        """Return caption text or raise on failure."""

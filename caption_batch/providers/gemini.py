from __future__ import annotations

import os
import time

from google import genai
from google.genai import types

from ..image_prep import prepare_image_jpeg
from .base import CaptionRequest, Provider


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, max_retries: int = 6):
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise SystemExit("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set.")
        self.client = genai.Client(api_key=key)
        self.max_retries = max_retries

    def caption(self, req: CaptionRequest) -> str:
        data, mime = prepare_image_jpeg(req.image_path, max_image_side=req.max_image_side)
        config_kwargs: dict = {}
        if req.temperature is not None:
            config_kwargs["temperature"] = float(req.temperature)
        if req.max_output_tokens is not None:
            config_kwargs["max_output_tokens"] = int(req.max_output_tokens)
        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        delay = 1.0
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs: dict = {
                    "model": req.model,
                    "contents": [
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_text(text=req.prompt),
                                types.Part.from_bytes(data=data, mime_type=mime),
                            ],
                        )
                    ],
                }
                if config is not None:
                    kwargs["config"] = config
                response = self.client.models.generate_content(**kwargs)
                text = (response.text or "").strip()
                if not text:
                    raise RuntimeError("Empty response from Gemini")
                return " ".join(text.split())
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                retryable = any(x in msg for x in ("429", "rate", "503", "unavailable", "timeout", "500"))
                if not retryable or attempt == self.max_retries:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 60)
        raise RuntimeError(f"Gemini failed after retries: {last_err}")

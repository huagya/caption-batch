from __future__ import annotations

import base64
import os
import time

from openai import OpenAI

from ..image_prep import prepare_image_jpeg
from .base import CaptionRequest, Provider


def _data_url(path, max_image_side: int) -> str:
    data, mime = prepare_image_jpeg(path, max_image_side=max_image_side)
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


class OpenRouterProvider(Provider):
    name = "openrouter"

    def __init__(self, api_key: str | None = None, max_retries: int = 6):
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise SystemExit("OPENROUTER_API_KEY is not set.")
        headers = {}
        ref = os.environ.get("OPENROUTER_HTTP_REFERER", "https://github.com/huagya/caption-batch")
        title = os.environ.get("OPENROUTER_APP_TITLE", "caption-batch")
        if ref:
            headers["HTTP-Referer"] = ref
        if title:
            headers["X-Title"] = title
        self.client = OpenAI(
            api_key=key,
            base_url="https://openrouter.ai/api/v1",
            default_headers=headers or None,
        )
        self.max_retries = max_retries

    def caption(self, req: CaptionRequest) -> str:
        url = _data_url(req.image_path, req.max_image_side)
        delay = 1.0
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs: dict = {
                    "model": req.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": req.prompt},
                                {"type": "image_url", "image_url": {"url": url}},
                            ],
                        }
                    ],
                }
                if req.temperature is not None:
                    kwargs["temperature"] = float(req.temperature)
                if req.max_output_tokens is not None:
                    kwargs["max_tokens"] = int(req.max_output_tokens)
                response = self.client.chat.completions.create(**kwargs)
                text = (response.choices[0].message.content or "").strip()
                if not text:
                    raise RuntimeError("Empty response from OpenRouter")
                return " ".join(text.split())
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                retryable = any(x in msg for x in ("429", "rate", "503", "unavailable", "timeout", "500"))
                if not retryable or attempt == self.max_retries:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 60)
        raise RuntimeError(f"OpenRouter failed after retries: {last_err}")

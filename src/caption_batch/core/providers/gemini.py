from __future__ import annotations

import logging
import os
import time

from google import genai
from google.genai import types

from ..image_prep import prepare_image
from ..prompts import resolve_user_prompt
from ..thinking import build_gemini_media_resolution, build_gemini_thinking_config
from .base import CaptionRequest, Provider

log = logging.getLogger(__name__)


def _caption_text_from_response(response: object) -> str:
    """Prefer non-thought parts; fall back to response.text (OK when thoughts not included)."""
    try:
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            content = getattr(candidates[0], "content", None)
            parts = getattr(content, "parts", None) or []
            texts: list[str] = []
            for part in parts:
                if getattr(part, "thought", None):
                    continue
                t = getattr(part, "text", None)
                if t:
                    texts.append(t)
            if texts:
                return " ".join(" ".join(texts).split())
    except Exception:
        pass
    text = (getattr(response, "text", None) or "").strip()
    return " ".join(text.split()) if text else ""


def _prep(req: CaptionRequest, image_path):
    return prepare_image(
        image_path,
        image_prep_enabled=req.image_prep_enabled,
        max_image_side=req.max_image_side,
        image_format=req.image_format,
        image_quality=req.image_quality,
    )


def build_gemini_contents(req: CaptionRequest) -> list:
    """
    Build Gemini user Content list (few-shot + target).

    System rules live in GenerateContentConfig.system_instruction — not here.
    Ordering (Google single-image guidance): image bytes, then text.
    """
    user_text = resolve_user_prompt(req.user_prompt)
    parts: list = []
    examples = list(req.few_shot or [])
    for i, ex in enumerate(examples, start=1):
        label = "Example caption:" if len(examples) == 1 else f"Example {i} caption:"
        ex_data, ex_mime = _prep(req, ex.image)
        parts.append(types.Part.from_bytes(data=ex_data, mime_type=ex_mime))
        parts.append(types.Part.from_text(text=f"{label}\n{ex.caption}"))
    data, mime = _prep(req, req.image_path)
    parts.append(types.Part.from_bytes(data=data, mime_type=mime))
    parts.append(types.Part.from_text(text=user_text))
    return [types.Content(role="user", parts=parts)]


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, max_retries: int = 6):
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise SystemExit("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set.")
        self.client = genai.Client(api_key=key)
        self.max_retries = max_retries

    def caption(self, req: CaptionRequest) -> str:
        config_kwargs: dict = {
            "system_instruction": req.prompt,
        }
        if req.temperature is not None:
            config_kwargs["temperature"] = float(req.temperature)
        if req.top_p is not None:
            config_kwargs["top_p"] = float(req.top_p)
        if req.max_output_tokens is not None:
            config_kwargs["max_output_tokens"] = int(req.max_output_tokens)
        if req.seed is not None:
            config_kwargs["seed"] = int(req.seed)

        thinking_cfg = build_gemini_thinking_config(req.thinking_level)
        if thinking_cfg is not None:
            config_kwargs["thinking_config"] = thinking_cfg

        media_res = build_gemini_media_resolution(req.media_resolution)
        if media_res is not None:
            config_kwargs["media_resolution"] = media_res

        config = types.GenerateContentConfig(**config_kwargs)
        contents = build_gemini_contents(req)

        delay = 1.0
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs: dict = {
                    "model": req.model,
                    "contents": contents,
                    "config": config,
                }
                response = self.client.models.generate_content(**kwargs)
                text = _caption_text_from_response(response)
                if not text:
                    raise RuntimeError("Empty response from Gemini")
                return text
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                rate_limited = ("429" in msg) or ("rate" in msg and "limit" in msg) or ("resource_exhausted" in msg)
                retryable = rate_limited or any(
                    x in msg for x in ("503", "unavailable", "timeout", "500")
                )
                if not retryable or attempt == self.max_retries:
                    raise
                if rate_limited:
                    log.warning(
                        "rate_limited retry attempt=%s sleep=%s provider=gemini err=%s",
                        attempt,
                        delay,
                        e,
                    )
                else:
                    log.warning(
                        "retryable error attempt=%s sleep=%s provider=gemini err=%s",
                        attempt,
                        delay,
                        e,
                    )
                time.sleep(delay)
                delay = min(delay * 2, 60)
        raise RuntimeError(f"Gemini failed after retries: {last_err}")

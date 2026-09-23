from __future__ import annotations

import base64
import logging
import os
import time

from openai import OpenAI

from ..few_shot import build_openrouter_messages_spec
from ..image_prep import prepare_image
from ..prompts import resolve_user_prompt
from ..thinking import build_openrouter_reasoning
from .base import CaptionRequest, Provider

log = logging.getLogger(__name__)


def _data_url_for(req: CaptionRequest, image_path) -> str:
    data, mime = prepare_image(
        image_path,
        image_prep_enabled=req.image_prep_enabled,
        max_image_side=req.max_image_side,
        image_format=req.image_format,
        image_quality=req.image_quality,
    )
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def build_openrouter_messages(req: CaptionRequest) -> list[dict]:
    """
    Build OpenRouter chat messages.

    - system role = long rules (req.prompt)
    - user turns: text (user_prompt) FIRST, then image_url (OR recommendation)
    - few-shot as multi-turn user/assistant pairs when present
    """
    user_text = resolve_user_prompt(req.user_prompt)
    target_url = _data_url_for(req, req.image_path)
    examples = list(req.few_shot or [])
    example_items = [(_data_url_for(req, ex.image), ex.caption) for ex in examples]
    return build_openrouter_messages_spec(
        system_prompt=req.prompt,
        user_prompt=user_text,
        target_data_url=target_url,
        example_items=example_items,
    )


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
        messages = build_openrouter_messages(req)
        delay = 1.0
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs: dict = {
                    "model": req.model,
                    "messages": messages,
                }
                if req.temperature is not None:
                    kwargs["temperature"] = float(req.temperature)
                if req.top_p is not None:
                    kwargs["top_p"] = float(req.top_p)
                if req.max_output_tokens is not None:
                    kwargs["max_tokens"] = int(req.max_output_tokens)
                if req.seed is not None:
                    kwargs["seed"] = int(req.seed)
                reasoning = build_openrouter_reasoning(req.thinking_level)
                if reasoning is not None:
                    kwargs["reasoning"] = reasoning
                # media_resolution is Gemini-only — never send on OpenRouter
                response = self.client.chat.completions.create(**kwargs)
                # Caption text only — ignore .reasoning even if present
                message = response.choices[0].message
                text = (getattr(message, "content", None) or "").strip()
                if not text:
                    raise RuntimeError("Empty response from OpenRouter")
                return " ".join(text.split())
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
                        "rate_limited retry attempt=%s sleep=%s provider=openrouter err=%s",
                        attempt,
                        delay,
                        e,
                    )
                else:
                    log.warning(
                        "retryable error attempt=%s sleep=%s provider=openrouter err=%s",
                        attempt,
                        delay,
                        e,
                    )
                time.sleep(delay)
                delay = min(delay * 2, 60)
        raise RuntimeError(f"OpenRouter failed after retries: {last_err}")

"""Unit tests for thinking_level / media_resolution mapping and provider config."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from PIL import Image

from caption_batch.core.thinking import (
    build_gemini_media_resolution,
    build_gemini_thinking_config,
    build_openrouter_reasoning,
    gemini_thinking_level_for_api,
    normalize_media_resolution,
    normalize_thinking_level,
    openrouter_reasoning_effort,
)


def _tiny_png(path: Path) -> Path:
    Image.new("RGB", (8, 8), color=(200, 40, 40)).save(path, format="PNG")
    return path


def test_normalize_thinking_level_empty() -> None:
    assert normalize_thinking_level(None) is None
    assert normalize_thinking_level("") is None
    assert normalize_thinking_level("  ") is None


def test_normalize_thinking_level_valid() -> None:
    for v in ("none", "minimal", "low", "medium", "high", "LOW", " Medium "):
        out = normalize_thinking_level(v)
        assert out == v.strip().lower()


def test_normalize_thinking_level_invalid() -> None:
    with pytest.raises(ValueError):
        normalize_thinking_level("ultra")


def test_gemini_none_maps_to_minimal() -> None:
    assert gemini_thinking_level_for_api("none") == "MINIMAL"
    assert gemini_thinking_level_for_api("minimal") == "MINIMAL"
    assert gemini_thinking_level_for_api("high") == "HIGH"


def test_build_gemini_thinking_config_none_is_minimal() -> None:
    cfg = build_gemini_thinking_config("none")
    assert cfg is not None
    # include_thoughts must not be True
    assert getattr(cfg, "include_thoughts", None) in (None, False)
    # thinking_budget must not be set alongside thinking_level
    assert getattr(cfg, "thinking_budget", None) is None
    level = cfg.thinking_level
    name = getattr(level, "name", None) or getattr(level, "value", None) or str(level)
    assert "MINIMAL" in str(name).upper()


def test_build_gemini_thinking_config_empty() -> None:
    assert build_gemini_thinking_config(None) is None
    assert build_gemini_thinking_config("") is None


def test_build_gemini_thinking_config_never_both_budget_and_level() -> None:
    for level in ("minimal", "low", "medium", "high"):
        cfg = build_gemini_thinking_config(level)
        assert cfg.thinking_level is not None
        assert cfg.thinking_budget is None
        assert cfg.include_thoughts is not True


def test_media_resolution_short_and_full() -> None:
    assert normalize_media_resolution("low") == "MEDIA_RESOLUTION_LOW"
    assert normalize_media_resolution("MEDIUM") == "MEDIA_RESOLUTION_MEDIUM"
    assert normalize_media_resolution("MEDIA_RESOLUTION_HIGH") == "MEDIA_RESOLUTION_HIGH"
    assert normalize_media_resolution(None) is None
    assert normalize_media_resolution("") is None
    with pytest.raises(ValueError):
        normalize_media_resolution("ultra")


def test_build_gemini_media_resolution() -> None:
    from google.genai import types

    assert build_gemini_media_resolution(None) is None
    assert build_gemini_media_resolution("low") == types.MediaResolution.MEDIA_RESOLUTION_LOW
    assert build_gemini_media_resolution("high") == types.MediaResolution.MEDIA_RESOLUTION_HIGH


def test_openrouter_reasoning_map() -> None:
    assert build_openrouter_reasoning(None) is None
    assert build_openrouter_reasoning("none") == {"effort": "none"}
    assert build_openrouter_reasoning("minimal") == {"effort": "minimal"}
    assert openrouter_reasoning_effort("high") == "high"


def test_gemini_provider_builds_config_kwargs(tmp_path: Path) -> None:
    """GeminiProvider attaches thinking_config + media_resolution without calling network."""
    from caption_batch.core.providers.base import CaptionRequest
    from caption_batch.core.providers.gemini import GeminiProvider

    img = _tiny_png(tmp_path / "x.png")

    captured: dict = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            resp = MagicMock()
            resp.text = "a caption"
            resp.candidates = []
            return resp

    class FakeClient:
        def __init__(self):
            self.models = FakeModels()

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False):
        with patch("caption_batch.core.providers.gemini.genai.Client", return_value=FakeClient()):
            prov = GeminiProvider(api_key="test-key")
            text = prov.caption(
                CaptionRequest(
                    image_path=img,
                    prompt="describe",
                    model="gemini-2.5-flash",
                    thinking_level="low",
                    media_resolution="medium",
                    max_output_tokens=512,
                )
            )
    assert text == "a caption"
    cfg = captured.get("config")
    assert cfg is not None
    assert cfg.thinking_config is not None
    assert cfg.thinking_config.thinking_budget is None
    assert cfg.thinking_config.include_thoughts is not True
    assert cfg.media_resolution is not None
    assert "MEDIUM" in str(cfg.media_resolution)


def test_openrouter_provider_reasoning_kwarg(tmp_path: Path) -> None:
    from caption_batch.core.providers.base import CaptionRequest
    from caption_batch.core.providers.openrouter import OpenRouterProvider

    img = _tiny_png(tmp_path / "x.png")

    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            msg = MagicMock()
            msg.content = "or caption"
            msg.reasoning = "should be ignored"
            choice = MagicMock()
            choice.message = msg
            resp = MagicMock()
            resp.choices = [choice]
            return resp

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    with patch("caption_batch.core.providers.openrouter.OpenAI", return_value=FakeClient()):
        prov = OpenRouterProvider(api_key="or-key")
        text = prov.caption(
            CaptionRequest(
                image_path=img,
                prompt="describe",
                model="some/vision",
                thinking_level="medium",
                media_resolution="high",  # must be ignored
            )
        )
    assert text == "or caption"
    assert captured.get("reasoning") == {"effort": "medium"}
    assert "media_resolution" not in captured


def test_gemini_prefers_non_thought_parts(tmp_path: Path) -> None:
    from caption_batch.core.providers.base import CaptionRequest
    from caption_batch.core.providers.gemini import GeminiProvider

    img = _tiny_png(tmp_path / "x.png")

    thought = MagicMock()
    thought.thought = True
    thought.text = "internal reasoning"
    answer = MagicMock()
    answer.thought = False
    answer.text = "visible caption"
    content = MagicMock()
    content.parts = [thought, answer]
    cand = MagicMock()
    cand.content = content
    resp = MagicMock()
    resp.candidates = [cand]
    resp.text = "fallback should not win"

    class FakeModels:
        def generate_content(self, **kwargs):
            return resp

    class FakeClient:
        models = FakeModels()

    with patch("caption_batch.core.providers.gemini.genai.Client", return_value=FakeClient()):
        prov = GeminiProvider(api_key="k")
        text = prov.caption(
            CaptionRequest(image_path=img, prompt="p", model="m", thinking_level=None)
        )
    assert text == "visible caption"

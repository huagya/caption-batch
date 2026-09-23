"""Unit tests for Gemini / OpenRouter message builders (system split + ordering)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from caption_batch.core.few_shot import FewShotExample
from caption_batch.core.prompts import DEFAULT_PROMPT, DEFAULT_USER_PROMPT
from caption_batch.core.providers.base import CaptionRequest
from caption_batch.core.providers.gemini import build_gemini_contents
from caption_batch.core.providers.openrouter import build_openrouter_messages


def _fake_prep(_req, image_path):
    name = Path(image_path).name.encode("utf-8")
    return name, "image/png"


def _req(**kwargs) -> CaptionRequest:
    base = dict(
        image_path=Path("/tmp/target.png"),
        prompt=DEFAULT_PROMPT,
        model="test-model",
        image_prep_enabled=False,
    )
    base.update(kwargs)
    return CaptionRequest(**base)


@patch("caption_batch.core.providers.gemini._prep", side_effect=_fake_prep)
def test_gemini_contents_no_system_in_user_image_before_text(_mock):
    contents = build_gemini_contents(_req())
    assert len(contents) == 1
    parts = contents[0].parts
    assert len(parts) == 2
    # Part 0: image bytes, Part 1: user cue text
    assert getattr(parts[0], "inline_data", None) is not None or parts[0].inline_data
    assert parts[1].text == DEFAULT_USER_PROMPT
    # long system rules must not appear in user parts
    for part in parts:
        t = getattr(part, "text", None) or ""
        assert "Strict Rules" not in t
        assert "You are an expert" not in t


@patch("caption_batch.core.providers.gemini._prep", side_effect=_fake_prep)
def test_gemini_few_shot_image_then_caption_then_target_then_cue(_mock):
    req = _req(
        few_shot=[FewShotExample(Path("/tmp/ex.png"), "an example caption")],
        user_prompt="Describe the outfit.",
    )
    contents = build_gemini_contents(req)
    parts = contents[0].parts
    # ex image, ex text, target image, user cue
    assert len(parts) == 4
    assert parts[1].text.startswith("Example caption:")
    assert "an example caption" in parts[1].text
    assert parts[3].text == "Describe the outfit."
    for part in parts:
        t = getattr(part, "text", None) or ""
        assert "You are an expert" not in t


@patch("caption_batch.core.providers.openrouter._data_url_for", side_effect=lambda req, p: f"data:image/png;base64,{Path(p).name}")
def test_openrouter_messages_system_and_text_before_image(_mock):
    msgs = build_openrouter_messages(_req())
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == DEFAULT_PROMPT
    assert msgs[1]["role"] == "user"
    content = msgs[1]["content"]
    assert content[0]["type"] == "text"
    assert content[0]["text"] == DEFAULT_USER_PROMPT
    assert content[1]["type"] == "image_url"
    # system not duplicated into user text parts
    assert all(
        DEFAULT_PROMPT not in (c.get("text") or "")
        for c in content
        if c.get("type") == "text"
    )


@patch("caption_batch.core.providers.openrouter._data_url_for", side_effect=lambda req, p: f"data:image/png;base64,{Path(p).name}")
def test_openrouter_few_shot_multiturn(_mock):
    req = _req(
        few_shot=[FewShotExample(Path("/tmp/ex.png"), "ex cap")],
        user_prompt="Caption please.",
    )
    msgs = build_openrouter_messages(req)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[2]["content"] == "ex cap"
    last = msgs[-1]["content"]
    assert last[0]["text"] == "Caption please."
    assert last[1]["type"] == "image_url"

"""Few-shot helpers and provider request building."""
from __future__ import annotations

from pathlib import Path

from caption_batch.core.few_shot import (
    FewShotExample,
    build_gemini_user_parts_spec,
    build_openrouter_messages_spec,
    build_openrouter_user_content,
    normalize_few_shot,
)
from caption_batch.core.prompts import DEFAULT_USER_PROMPT, resolve_user_prompt


def test_normalize_few_shot_clamp_and_skip():
    raw = [
        {"image": "/a.png", "caption": "cap a"},
        {"image": "", "caption": "bad"},
        {"image": "/b.png", "caption": "cap b"},
        {"image": "/c.png", "caption": "cap c"},
        {"image": "/d.png", "caption": "cap d"},
    ]
    out = normalize_few_shot(raw)
    assert len(out) == 3
    assert out[0].image == Path("/a.png")
    assert out[0].caption == "cap a"
    assert out[2].caption == "cap c"


def test_normalize_empty():
    assert normalize_few_shot(None) == []
    assert normalize_few_shot([]) == []
    assert normalize_few_shot([{"image": "x", "caption": ""}]) == []


def test_resolve_user_prompt():
    assert resolve_user_prompt(None) == DEFAULT_USER_PROMPT
    assert resolve_user_prompt("") == DEFAULT_USER_PROMPT
    assert resolve_user_prompt("   ") == DEFAULT_USER_PROMPT
    assert resolve_user_prompt("Focus on clothing.") == "Focus on clothing."


def test_openrouter_messages_spec_no_few_shot_text_before_image():
    msgs = build_openrouter_messages_spec(
        system_prompt="SYSTEM RULES LONG",
        user_prompt="Caption this image.",
        target_data_url="data:image/png;base64,AAA",
        example_items=[],
    )
    assert msgs[0] == {"role": "system", "content": "SYSTEM RULES LONG"}
    assert len(msgs) == 2
    user = msgs[1]
    assert user["role"] == "user"
    content = user["content"]
    assert content[0]["type"] == "text"
    assert content[0]["text"] == "Caption this image."
    assert content[1]["type"] == "image_url"
    # system rules must not appear in user content
    assert all(
        "SYSTEM RULES" not in (c.get("text") or "")
        for c in content
        if c.get("type") == "text"
    )


def test_openrouter_messages_spec_few_shot_multiturn():
    msgs = build_openrouter_messages_spec(
        system_prompt="SYS",
        user_prompt="Caption this image.",
        target_data_url="data:image/png;base64,TARGET",
        example_items=[
            ("data:image/png;base64,BBB", "example one"),
            ("data:image/png;base64,CCC", "example two"),
        ],
    )
    assert msgs[0]["role"] == "system"
    # user, assistant, user, assistant, user(target)
    assert [m["role"] for m in msgs] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert msgs[2]["content"] == "example one"
    assert msgs[4]["content"] == "example two"
    last = msgs[-1]["content"]
    assert last[0]["type"] == "text"
    assert last[1]["type"] == "image_url"
    assert last[1]["image_url"]["url"] == "data:image/png;base64,TARGET"


def test_openrouter_content_builder_legacy_text_first():
    content = build_openrouter_user_content(
        prompt="Caption this.",
        target_data_url="data:image/png;base64,AAA",
        example_items=[
            ("data:image/png;base64,BBB", "example one"),
            ("data:image/png;base64,CCC", "example two"),
        ],
    )
    texts = [c["text"] for c in content if c.get("type") == "text"]
    assert texts[0] == "Caption this."
    assert "Example 1:" in texts
    assert "example one" in texts
    assert "Now caption this image:" in texts
    images = [c for c in content if c.get("type") == "image_url"]
    assert len(images) == 3  # 2 examples + target


def test_gemini_parts_spec_image_before_text_no_system():
    parts = build_gemini_user_parts_spec(
        user_prompt="Caption this image.",
        target_mime="image/webp",
        example_items=[("image/png", "ex caption")],
    )
    kinds = [p["kind"] for p in parts]
    # image → text (example), image → text (target+cue)
    assert kinds == ["image", "text", "image", "text"]
    assert parts[0]["mime"] == "image/png"
    assert "Example caption:" in parts[1]["text"]
    assert "ex caption" in parts[1]["text"]
    assert parts[2]["mime"] == "image/webp"
    assert parts[3]["text"] == "Caption this image."
    # system-length rules must not be in user parts
    assert all("Strict Rules" not in (p.get("text") or "") for p in parts)


def test_few_shot_example_dataclass():
    ex = FewShotExample(Path("/x.png"), "hello")
    assert ex.caption == "hello"

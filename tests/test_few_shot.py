"""Few-shot helpers and provider request building."""
from __future__ import annotations

from pathlib import Path

from caption_batch.core.few_shot import (
    FewShotExample,
    build_gemini_user_parts_spec,
    build_openrouter_user_content,
    normalize_few_shot,
)


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


def test_openrouter_content_builder():
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


def test_gemini_parts_spec():
    parts = build_gemini_user_parts_spec(
        prompt="Main prompt",
        target_mime="image/webp",
        example_items=[("image/png", "ex caption")],
    )
    kinds = [p["kind"] for p in parts]
    assert kinds[0] == "text"
    assert "image" in kinds
    assert parts[0]["text"] == "Main prompt"
    assert any(p.get("text") == "Example caption:" for p in parts)
    assert any(p.get("text") == "Now caption this image:" for p in parts)
    assert parts[-1]["kind"] == "image"
    assert parts[-1]["mime"] == "image/webp"


def test_few_shot_example_dataclass():
    ex = FewShotExample(Path("/x.png"), "hello")
    assert ex.caption == "hello"

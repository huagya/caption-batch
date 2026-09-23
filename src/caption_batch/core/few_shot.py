"""Few-shot example helpers for caption providers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence


@dataclass(frozen=True)
class FewShotExample:
    image: Path
    caption: str


def normalize_few_shot(
    raw: Sequence[dict[str, Any] | FewShotExample] | None,
    *,
    max_n: int = 3,
) -> list[FewShotExample]:
    """Parse and clamp few-shot examples (max 3). Empty / invalid entries skipped."""
    if not raw:
        return []
    out: list[FewShotExample] = []
    for item in raw:
        if len(out) >= max_n:
            break
        if isinstance(item, FewShotExample):
            if str(item.caption).strip() and str(item.image).strip():
                out.append(FewShotExample(Path(item.image), str(item.caption).strip()))
            continue
        if not isinstance(item, dict):
            continue
        img = item.get("image")
        cap = item.get("caption")
        if img is None or cap is None:
            continue
        img_s = str(img).strip()
        cap_s = str(cap).strip()
        if not img_s or not cap_s:
            continue
        out.append(FewShotExample(Path(img_s), cap_s))
    return out


def few_shot_to_dicts(examples: Sequence[FewShotExample]) -> list[dict[str, str]]:
    return [{"image": str(ex.image), "caption": ex.caption} for ex in examples]


def build_openrouter_messages_spec(
    *,
    system_prompt: str,
    user_prompt: str,
    target_data_url: str,
    example_items: Sequence[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """
    OpenRouter chat messages: system + multi-turn few-shot + target.

    User turns always put text (user_prompt) BEFORE image_url parts.
    example_items: list of (data_url, caption_text)
    """
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for url, caption in example_items or []:
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            }
        )
        messages.append({"role": "assistant", "content": caption})
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": target_data_url}},
            ],
        }
    )
    return messages


def build_openrouter_user_content(
    *,
    prompt: str,
    target_data_url: str,
    example_items: Sequence[tuple[str, str]],
) -> list[dict[str, Any]]:
    """
    Legacy single-user content builder (text-first). Prefer build_openrouter_messages_spec.

    Kept for callers that only need the user content array with text before images.
    `prompt` here is the short user cue (not system rules).
    """
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for i, (url, caption) in enumerate(example_items, start=1):
        label = "Example:" if len(example_items) == 1 else f"Example {i}:"
        content.append({"type": "text", "text": label})
        content.append({"type": "image_url", "image_url": {"url": url}})
        content.append({"type": "text", "text": caption})
    if example_items:
        content.append({"type": "text", "text": "Now caption this image:"})
    content.append({"type": "image_url", "image_url": {"url": target_data_url}})
    return content


def build_gemini_user_parts_spec(
    *,
    user_prompt: str,
    target_mime: str,
    example_items: Sequence[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """
    Pure helper describing Gemini *user* parts (system is separate).

    Gemini single-image quality: image BEFORE text in each turn.
    example_items: list of (mime_type, caption_text) — image bytes omitted.
    Returns part specs: {"kind": "text"|"image", ...}
    """
    parts: list[dict[str, Any]] = []
    examples = list(example_items or [])
    for i, (mime, caption) in enumerate(examples, start=1):
        label = "Example caption:" if len(examples) == 1 else f"Example {i} caption:"
        parts.append({"kind": "image", "mime": mime})
        parts.append({"kind": "text", "text": f"{label}\n{caption}"})
    parts.append({"kind": "image", "mime": target_mime})
    parts.append({"kind": "text", "text": user_prompt})
    return parts


ImageFormat = Literal["jpeg", "webp", "png"]

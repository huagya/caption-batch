from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ModelInfo:
    id: str
    name: str = ""
    provider: str = ""
    vision: bool = False
    context_length: int | None = None
    price_prompt: str | None = None
    price_completion: str | None = None
    raw_notes: str = ""


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "caption-batch"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_openrouter(*, vision_only: bool = True) -> list[ModelInfo]:
    data = _http_get_json("https://openrouter.ai/api/v1/models")
    rows = data.get("data") or []
    out: list[ModelInfo] = []
    for m in rows:
        arch = m.get("architecture") or {}
        inputs = arch.get("input_modalities") or []
        modality = (arch.get("modality") or "").lower()
        vision = ("image" in inputs) or ("image" in modality)
        if vision_only and not vision:
            continue
        pricing = m.get("pricing") or {}
        out.append(
            ModelInfo(
                id=m.get("id") or "",
                name=m.get("name") or "",
                provider="openrouter",
                vision=vision,
                context_length=m.get("context_length"),
                price_prompt=pricing.get("prompt"),
                price_completion=pricing.get("completion"),
            )
        )
    out.sort(key=lambda x: x.id.lower())
    return out


def list_gemini(*, vision_only: bool = True, api_key: str | None = None) -> list[ModelInfo]:
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY (or GOOGLE_API_KEY) is required to list Gemini models.")

    try:
        from google import genai

        client = genai.Client(api_key=key)
        out: list[ModelInfo] = []
        for m in client.models.list():
            mid = getattr(m, "name", None) or getattr(m, "id", None) or ""
            mid = mid.replace("models/", "")
            methods = list(
                getattr(m, "supported_actions", None)
                or getattr(m, "supported_generation_methods", None)
                or []
            )
            display = getattr(m, "display_name", "") or mid
            if vision_only:
                drop = any(x in mid.lower() for x in ("embedding", "embed", "tts", "aqa", "imagen", "veo"))
                if drop:
                    continue
                if "gemini" not in mid.lower():
                    continue
            out.append(
                ModelInfo(
                    id=mid,
                    name=str(display),
                    provider="gemini",
                    vision=True,
                    context_length=getattr(m, "input_token_limit", None),
                    raw_notes=",".join(str(x) for x in methods[:8]),
                )
            )
        out.sort(key=lambda x: x.id.lower())
        return out
    except ImportError:
        pass

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    data = _http_get_json(url)
    out = []
    for m in data.get("models") or []:
        mid = (m.get("name") or "").replace("models/", "")
        methods = m.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue
        if vision_only and any(x in mid.lower() for x in ("embedding", "embed", "tts", "aqa")):
            continue
        out.append(
            ModelInfo(
                id=mid,
                name=m.get("displayName") or mid,
                provider="gemini",
                vision=True,
                context_length=m.get("inputTokenLimit"),
                raw_notes=",".join(methods),
            )
        )
    out.sort(key=lambda x: x.id.lower())
    return out


def format_table(models: list[ModelInfo]) -> str:
    if not models:
        return "(no models)"
    lines = [
        f"{'ID':<48} {'VISION':<6} {'CTX':>8} {'$/prompt_tok':>14} {'$/comp_tok':>14}  NAME",
        "-" * 120,
    ]
    for m in models:
        ctx = "" if m.context_length is None else str(m.context_length)
        lines.append(
            f"{m.id:<48} {str(m.vision):<6} {ctx:>8} {(m.price_prompt or '-'):>14} {(m.price_completion or '-'):>14}  {m.name}"
        )
    lines.append(f"\nTotal: {len(models)}")
    lines.append(
        "Note: OpenRouter prices are per-token strings from their API (often USD). "
        "Gemini list has no public per-model price in this endpoint."
    )
    return "\n".join(lines)


def to_json(models: list[ModelInfo]) -> str:
    return json.dumps([asdict(m) for m in models], ensure_ascii=False, indent=2)

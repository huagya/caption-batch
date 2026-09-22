"""Shared image preparation for API upload."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image

DEFAULT_MAX_IMAGE_SIDE = 768
DEFAULT_IMAGE_FORMAT: Literal["jpeg", "webp", "png"] = "webp"
DEFAULT_IMAGE_QUALITY = 95
DEFAULT_IMAGE_PREP_ENABLED = True

ImageFormat = Literal["jpeg", "webp", "png"]

MIME_BY_SUFFIX: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

FORMAT_MIME: dict[str, str] = {
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "png": "image/png",
}


def mime_from_path(path: Path) -> str:
    """Best-effort MIME from file suffix."""
    return MIME_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")


def _convert_for_format(img: Image.Image, fmt: str) -> Image.Image:
    """Convert pixel mode for target format (RGBA->RGB for jpeg; keep alpha for png/webp)."""
    if fmt == "jpeg":
        if img.mode in ("RGBA", "LA"):
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.split()[-1])
            return background
        if img.mode == "P":
            if "transparency" in img.info:
                rgba = img.convert("RGBA")
                background = Image.new("RGB", rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.split()[-1])
                return background
            return img.convert("RGB")
        if img.mode != "RGB":
            return img.convert("RGB")
        return img

    # png / webp - preserve alpha when present
    if img.mode in ("RGBA", "LA"):
        return img.convert("RGBA")
    if img.mode == "P":
        if "transparency" in img.info:
            return img.convert("RGBA")
        return img.convert("RGB")
    if img.mode in ("RGB", "L"):
        return img
    return img.convert("RGB")


def prepare_image(
    path: Path,
    *,
    image_prep_enabled: bool = DEFAULT_IMAGE_PREP_ENABLED,
    max_image_side: int = DEFAULT_MAX_IMAGE_SIDE,
    image_format: ImageFormat = DEFAULT_IMAGE_FORMAT,
    image_quality: int = DEFAULT_IMAGE_QUALITY,
) -> tuple[bytes, str]:
    """Prepare image bytes for API upload.

    Behavior contract:

    1. If ``image_prep_enabled`` is False: return original file bytes + MIME from
       suffix (jpeg/jpg/png/webp/gif/bmp/...); do **not** re-encode.
    2. If enabled:
       - Never upscale.
       - If longest side > ``max_image_side``: downscale so longest == max.
       - If already <= max: keep pixel size, but still re-encode to the chosen
         format/quality (prep on = explicit encode).
    3. Convert mode appropriately (RGBA->RGB for jpeg; keep alpha for png/webp).

    Resampling uses Lanczos only.

    Format / quality notes:
    - jpeg: standard quality 1-100
    - webp: quality=100 -> lossless=True
    - png: quality unused for lossy; quality>=100 -> compress_level=0
    """
    if not image_prep_enabled:
        return path.read_bytes(), mime_from_path(path)

    fmt = str(image_format).lower().strip()
    if fmt not in FORMAT_MIME:
        raise ValueError(f"Unsupported image_format: {image_format!r} (use jpeg|webp|png)")
    quality = max(1, min(100, int(image_quality)))
    side = max(1, int(max_image_side))

    with Image.open(path) as opened:
        img = _convert_for_format(opened, fmt)
        # Copy out of context manager safely
        img.load()

        w, h = img.size
        longest = max(w, h)
        if longest > side:
            scale = side / float(longest)
            new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        buf = BytesIO()
        if fmt == "jpeg":
            img.save(buf, format="JPEG", quality=quality, optimize=True)
        elif fmt == "webp":
            if quality >= 100:
                img.save(buf, format="WEBP", lossless=True)
            else:
                img.save(buf, format="WEBP", quality=quality, method=6)
        else:  # png
            if quality >= 100:
                compress_level = 0
            else:
                # Map quality 1..99 -> compress_level 9..1 (higher quality = less zlib)
                compress_level = max(1, min(9, int(round((100 - quality) / 100.0 * 9))))
            img.save(buf, format="PNG", compress_level=compress_level)
        return buf.getvalue(), FORMAT_MIME[fmt]


def prepare_image_jpeg(
    path: Path,
    *,
    max_image_side: int = DEFAULT_MAX_IMAGE_SIDE,
    quality: int = DEFAULT_IMAGE_QUALITY,
) -> tuple[bytes, str]:
    """Thin backward-compatible wrapper: always JPEG with prep enabled."""
    return prepare_image(
        path,
        image_prep_enabled=True,
        max_image_side=max_image_side,
        image_format="jpeg",
        image_quality=quality,
    )

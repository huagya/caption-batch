"""Shared image preparation for API upload (resize + JPEG)."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

DEFAULT_MAX_IMAGE_SIDE = 1536
DEFAULT_JPEG_QUALITY = 85


def prepare_image_jpeg(
    path: Path,
    *,
    max_image_side: int = DEFAULT_MAX_IMAGE_SIDE,
    quality: int = DEFAULT_JPEG_QUALITY,
) -> tuple[bytes, str]:
    """Load image, optionally downscale longest side, return JPEG bytes + mime.

    Skips resize when both dimensions are already <= max_image_side.
    Always re-encodes to JPEG for consistent upload size.
    """
    side = max(1, int(max_image_side))
    with Image.open(path) as img:
        img = img.convert("RGB")
        w, h = img.size
        longest = max(w, h)
        if longest > side:
            scale = side / float(longest)
            new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue(), "image/jpeg"

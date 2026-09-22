"""Unit tests for image_prep contract."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from caption_batch.core.image_prep import (
    DEFAULT_MAX_IMAGE_SIDE,
    prepare_image,
)


def _save_png(path: Path, size: tuple[int, int], *, mode: str = "RGB", color=(20, 40, 60)) -> Path:
    img = Image.new(mode, size, color if mode != "RGBA" else (*color, 200))
    img.save(path, format="PNG")
    return path


def test_default_max_side_is_768() -> None:
    assert DEFAULT_MAX_IMAGE_SIDE == 768


def test_prep_off_returns_original_bytes(tmp_path: Path) -> None:
    src = _save_png(tmp_path / "orig.png", (120, 80))
    original = src.read_bytes()
    data, mime = prepare_image(src, image_prep_enabled=False)
    assert data == original
    assert mime == "image/png"


def test_never_upscales(tmp_path: Path) -> None:
    src = _save_png(tmp_path / "small.png", (100, 50))
    data, mime = prepare_image(
        src,
        image_prep_enabled=True,
        max_image_side=768,
        image_format="png",
        image_quality=95,
    )
    assert mime == "image/png"
    with Image.open(BytesIO(data)) as out:
        assert out.size == (100, 50)


def test_downscales_large(tmp_path: Path) -> None:
    src = _save_png(tmp_path / "big.png", (2000, 1000))
    data, mime = prepare_image(
        src,
        image_prep_enabled=True,
        max_image_side=768,
        image_format="jpeg",
        image_quality=90,
    )
    assert mime == "image/jpeg"
    with Image.open(BytesIO(data)) as out:
        assert max(out.size) == 768
        assert out.size == (768, 384)


def test_small_image_same_size_but_reencoded(tmp_path: Path) -> None:
    src = _save_png(tmp_path / "mid.png", (400, 300))
    original = src.read_bytes()
    data, mime = prepare_image(
        src,
        image_prep_enabled=True,
        max_image_side=768,
        image_format="webp",
        image_quality=95,
    )
    assert mime == "image/webp"
    assert data != original
    with Image.open(BytesIO(data)) as out:
        assert out.size == (400, 300)


def test_webp_lossless_at_quality_100(tmp_path: Path) -> None:
    src = tmp_path / "colors.png"
    img = Image.new("RGB", (64, 64))
    for y in range(64):
        for x in range(64):
            img.putpixel((x, y), (x * 4, y * 4, (x + y) % 256))
    img.save(src, format="PNG")
    data, mime = prepare_image(
        src,
        image_prep_enabled=True,
        max_image_side=768,
        image_format="webp",
        image_quality=100,
    )
    assert mime == "image/webp"
    with Image.open(BytesIO(data)) as out:
        out.load()
        assert out.format == "WEBP"
        out_pixels = [out.getpixel((x, y)) for y in range(64) for x in range(64)]
        src_pixels = [img.getpixel((x, y)) for y in range(64) for x in range(64)]
        assert out_pixels == src_pixels


def test_jpeg_drops_alpha(tmp_path: Path) -> None:
    src = _save_png(tmp_path / "alpha.png", (32, 32), mode="RGBA", color=(10, 20, 30))
    data, mime = prepare_image(
        src,
        image_prep_enabled=True,
        image_format="jpeg",
        image_quality=90,
    )
    assert mime == "image/jpeg"
    with Image.open(BytesIO(data)) as out:
        assert out.mode == "RGB"

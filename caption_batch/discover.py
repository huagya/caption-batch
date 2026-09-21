from __future__ import annotations

from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}

# Auto-build index when discovery would materialize this many paths
HUGE_DIR_HINT = 50_000


def state_dir_for(input_dir: Path, state_dir: Path | None = None) -> Path:
    return state_dir or (input_dir / ".caption_state")


def index_path_for(input_dir: Path, state_dir: Path | None = None) -> Path:
    return state_dir_for(input_dir, state_dir) / "image_index.txt"


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTS


def iter_image_paths(root: Path, recursive: bool = True):
    """Yield image Paths without sorting / materializing (streaming)."""
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")
    if recursive:
        it = root.rglob("*")
    else:
        it = root.iterdir()
    for p in it:
        if is_image_file(p):
            yield p


def iter_images(root: Path, recursive: bool = True) -> list[Path]:
    """Collect and sort image paths (OK for small/medium folders)."""
    paths = list(iter_image_paths(root, recursive=recursive))
    paths.sort(key=lambda p: str(p).lower())
    return paths


def build_image_index(
    input_dir: Path,
    *,
    recursive: bool = True,
    state_dir: Path | None = None,
    index_file: Path | None = None,
) -> Path:
    """Write one absolute path per line to DIR/.caption_state/image_index.txt."""
    input_dir = input_dir.resolve()
    out = index_file or index_path_for(input_dir, state_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    count = 0
    with tmp.open("w", encoding="utf-8") as f:
        # Stream discovery; sort via external temp lines only if needed.
        # For 1M scale, unsorted index is fine — resume uses .txt presence.
        for p in iter_image_paths(input_dir, recursive=recursive):
            f.write(str(p.resolve()) + "\n")
            count += 1
    tmp.replace(out)
    print(f"[build-index] wrote {count} paths -> {out}")
    return out


def load_paths_from_index(index_file: Path, *, limit: int | None = None) -> list[Path]:
    """Load paths from index file. For huge indexes prefer streaming helpers."""
    paths: list[Path] = []
    with index_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            paths.append(Path(line))
            if limit is not None and len(paths) >= limit:
                break
    return paths


def iter_paths_from_index(index_file: Path):
    with index_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield Path(line)


def caption_path_for(image: Path) -> Path:
    return image.with_suffix(".txt")


def is_done(image: Path) -> bool:
    cap = caption_path_for(image)
    if not cap.exists():
        return False
    return cap.stat().st_size > 0

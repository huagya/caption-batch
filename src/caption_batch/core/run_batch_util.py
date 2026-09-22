from __future__ import annotations

from pathlib import Path

from .discover import (
    HUGE_DIR_HINT,
    build_image_index,
    index_path_for,
    iter_images,
    load_paths_from_index,
)


def resolve_image_list(
    input_dir: Path,
    *,
    recursive: bool,
    from_index: bool,
    state_dir: Path | None,
    limit: int | None,
) -> list[Path]:
    idx = index_path_for(input_dir, state_dir)

    if from_index:
        if not idx.is_file():
            print(f"[run] --from-index set but missing {idx}; building now...")
            build_image_index(input_dir, recursive=recursive, state_dir=state_dir)
        return load_paths_from_index(idx, limit=limit)

    if idx.is_file():
        print(f"[run] using existing index: {idx}")
        return load_paths_from_index(idx, limit=limit)

    probe = iter_images(input_dir, recursive=recursive)
    if len(probe) >= HUGE_DIR_HINT:
        print(f"[run] {len(probe)} images (>= {HUGE_DIR_HINT}); writing index for reuse...")
        build_image_index(input_dir, recursive=recursive, state_dir=state_dir)
        images = probe
    else:
        images = probe

    if limit is not None:
        images = images[: max(0, limit)]
    return images

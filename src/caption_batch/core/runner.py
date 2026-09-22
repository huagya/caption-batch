from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from tqdm import tqdm

from .discover import (
    HUGE_DIR_HINT,
    build_image_index,
    caption_path_for,
    index_path_for,
    is_done,
    iter_images,
    load_paths_from_index,
)
from .image_prep import (
    DEFAULT_IMAGE_FORMAT,
    DEFAULT_IMAGE_PREP_ENABLED,
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_MAX_IMAGE_SIDE,
)
from .prompts import DEFAULT_PROMPT
from .providers import get_provider
from .providers.base import CaptionRequest


@dataclass
class RunStats:
    total: int = 0
    todo: int = 0
    done_skip: int = 0
    ok: int = 0
    failed: int = 0


class RunState:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.errors_path = self.state_dir / "errors.jsonl"
        self.summary_path = self.state_dir / "last_run_summary.json"
        self._lock = threading.Lock()

    def log_error(self, image: Path, error: str) -> None:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "image": str(image),
            "error": error,
        }
        with self._lock:
            with self.errors_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def write_summary(self, payload: dict) -> None:
        self.summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _resolve_image_list(
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

    # Heuristic: if folder looks huge, prefer building an index once
    # rather than holding a giant sorted list forever in memory during scan.
    # We still may materialize for the worker queue; index avoids re-scan.
    probe = iter_images(input_dir, recursive=recursive)
    if len(probe) >= HUGE_DIR_HINT:
        print(f"[run] {len(probe)} images (>= {HUGE_DIR_HINT}); writing index for reuse...")
        build_image_index(input_dir, recursive=recursive, state_dir=state_dir)
        # reuse probe (already sorted) rather than re-read
        images = probe
    else:
        images = probe

    if limit is not None:
        images = images[: max(0, limit)]
    return images


def run_batch(
    *,
    provider_name: str,
    model: str,
    input_dir: Path,
    workers: int = 4,
    recursive: bool = True,
    prompt: str | None = None,
    prompt_file: Path | None = None,
    state_dir: Path | None = None,
    overwrite: bool = False,
    limit: int | None = None,
    dry_run: bool = False,
    temperature: float | None = None,
    top_p: float | None = None,
    max_output_tokens: int | None = 1024,
    seed: int | None = None,
    max_image_side: int = DEFAULT_MAX_IMAGE_SIDE,
    image_prep_enabled: bool = DEFAULT_IMAGE_PREP_ENABLED,
    image_format: str = DEFAULT_IMAGE_FORMAT,
    image_quality: int = DEFAULT_IMAGE_QUALITY,
    thinking_level: str | None = None,
    media_resolution: str | None = None,
    from_index: bool = False,
    progress_cb: Optional[Callable[[RunStats], None]] = None,
    stop_event: Optional[threading.Event] = None,
) -> RunStats:
    if prompt_file:
        prompt_text = prompt_file.read_text(encoding="utf-8").strip()
    else:
        prompt_text = (prompt or DEFAULT_PROMPT).strip()

    images = _resolve_image_list(
        input_dir,
        recursive=recursive,
        from_index=from_index,
        state_dir=state_dir,
        limit=limit,
    )

    stats = RunStats(total=len(images))
    if overwrite:
        todo = images
        stats.done_skip = 0
    else:
        todo = []
        for img in images:
            if is_done(img):
                stats.done_skip += 1
            else:
                todo.append(img)
    stats.todo = len(todo)
    if progress_cb:
        progress_cb(stats)

    state = RunState(state_dir or (input_dir / ".caption_state"))
    started = time.time()

    if dry_run:
        print(
            f"[dry-run] total={stats.total} skip={stats.done_skip} todo={stats.todo} "
            f"workers={workers} temp={temperature} top_p={top_p} max_tokens={max_output_tokens} "
            f"seed={seed} max_side={max_image_side} prep={image_prep_enabled} "
            f"fmt={image_format} q={image_quality} "
            f"thinking={thinking_level} media_res={media_resolution}"
        )
        for p in todo[:20]:
            print(f"  would process: {p}")
        if len(todo) > 20:
            print(f"  ... and {len(todo) - 20} more")
        if progress_cb:
            progress_cb(stats)
        return stats

    if stats.todo == 0:
        print("Nothing to do (all captions present).")
        return stats

    provider = get_provider(provider_name)
    workers = max(1, workers)

    def work(image: Path) -> tuple[Path, bool, str]:
        out = caption_path_for(image)
        try:
            text = provider.caption(
                CaptionRequest(
                    image_path=image,
                    prompt=prompt_text,
                    model=model,
                    temperature=temperature,
                    top_p=top_p,
                    max_output_tokens=max_output_tokens,
                    seed=seed,
                    max_image_side=max_image_side,
                    image_prep_enabled=image_prep_enabled,
                    image_format=image_format,  # type: ignore[arg-type]
                    image_quality=image_quality,
                    thinking_level=thinking_level,
                    media_resolution=media_resolution,
                )
            )
            _atomic_write_text(out, text)
            return image, True, ""
        except Exception as e:
            state.log_error(image, str(e))
            return image, False, str(e)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(work, img): img for img in todo}
        with tqdm(total=len(futures), desc="captioning", unit="img") as bar:
            for fut in as_completed(list(futures.keys())):
                if stop_event is not None and stop_event.is_set():
                    for pending in futures:
                        pending.cancel()
                    break
                try:
                    _img, ok, _err = fut.result()
                except Exception as e:  # cancelled or unexpected
                    if stop_event is not None and stop_event.is_set():
                        break
                    stats.failed += 1
                    bar.update(1)
                    if progress_cb:
                        progress_cb(stats)
                    continue
                if ok:
                    stats.ok += 1
                else:
                    stats.failed += 1
                bar.update(1)
                bar.set_postfix(ok=stats.ok, fail=stats.failed, skip=stats.done_skip)
                if progress_cb:
                    progress_cb(stats)

    elapsed = time.time() - started
    stopped = bool(stop_event is not None and stop_event.is_set())
    summary = {
        "provider": provider_name,
        "model": model,
        "input_dir": str(input_dir.resolve()),
        "total": stats.total,
        "skipped_existing": stats.done_skip,
        "ok": stats.ok,
        "failed": stats.failed,
        "workers": workers,
        "temperature": temperature,
        "top_p": top_p,
        "max_output_tokens": max_output_tokens,
        "seed": seed,
        "max_image_side": max_image_side,
        "image_prep_enabled": image_prep_enabled,
        "image_format": image_format,
        "image_quality": image_quality,
        "thinking_level": thinking_level,
        "media_resolution": media_resolution,
        "elapsed_sec": round(elapsed, 2),
        "errors_log": str(state.errors_path),
        "stopped": stopped,
    }
    state.write_summary(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return stats

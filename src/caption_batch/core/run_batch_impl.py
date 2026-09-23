from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

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
from .few_shot import FewShotExample, normalize_few_shot
from .image_prep import (
    DEFAULT_IMAGE_FORMAT,
    DEFAULT_IMAGE_PREP_ENABLED,
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_MAX_IMAGE_SIDE,
)
from .job_snapshot import write_job_snapshot
from .prompts import DEFAULT_PROMPT, resolve_user_prompt
from .providers import get_provider
from .providers.base import CaptionRequest
from .rate_limit import RateLimiter, make_rate_limiter
from .run_batch_util import resolve_image_list
from .runner_progress import (
    ImageResult,
    ProgressTracker,
    RunState,
    RunStats,
    atomic_write_text,
    stats_dict,
)

# Back-compat aliases used by CLI / older imports
_atomic_write_text = atomic_write_text
_stats_dict = stats_dict
_ProgressTracker = ProgressTracker


def run_batch(
    *,
    provider_name: str,
    model: str,
    input_dir: Path,
    workers: int = 4,
    recursive: bool = True,
    prompt: str | None = None,
    prompt_file: Path | None = None,
    user_prompt: str | None = None,
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
    on_progress: Optional[Callable[[dict], None]] = None,
    stop_event: Optional[threading.Event] = None,
    rate_limit_rpm: int | None = None,
    rate_limiter: RateLimiter | None = None,
    few_shot: list[dict] | list[FewShotExample] | None = None,
    collect_results: bool = False,
    write_outputs: bool = True,
    snapshot_params: dict[str, Any] | None = None,
    job_kind: str = "batch",
) -> RunStats | tuple[RunStats, list[ImageResult]]:
    """
    Run caption batch.

    progress_cb: legacy RunStats-only callback (still supported).
    on_progress: richer dict callback (preferred for WebUI).
    collect_results: if True, also return list[ImageResult] (for preview).
    write_outputs: if False, still caption but do not write .txt (rare; preview usually writes).
    """
    if prompt_file:
        prompt_text = prompt_file.read_text(encoding="utf-8").strip()
    else:
        prompt_text = (prompt or DEFAULT_PROMPT).strip()
    user_prompt_text = resolve_user_prompt(user_prompt)

    examples = normalize_few_shot(few_shot)

    images = resolve_image_list(
        input_dir,
        recursive=recursive,
        from_index=from_index,
        state_dir=state_dir,
        limit=limit,
    )

    stats = RunStats(total=len(images))
    results: list[ImageResult] = []
    skipped_existing: list[Path] = []

    if overwrite:
        todo = list(images)
        stats.done_skip = 0
    else:
        todo = []
        for img in images:
            if is_done(img):
                stats.done_skip += 1
                skipped_existing.append(img)
            else:
                todo.append(img)
    stats.todo = len(todo)

    # For preview: include skipped existing captions in results when readable
    if collect_results:
        for img in skipped_existing:
            cap_text: str | None = None
            try:
                cap_text = caption_path_for(img).read_text(encoding="utf-8")
            except Exception:
                cap_text = None
            results.append(
                ImageResult(image=str(img), caption=cap_text, error=None, skipped=True)
            )

    state = RunState(state_dir or (input_dir / ".caption_state"))
    started = time.time()
    tracker = _ProgressTracker(stats, started)

    def _emit() -> None:
        snap = tracker.snapshot()
        if on_progress:
            on_progress(snap)
        if progress_cb:
            progress_cb(stats)

    def _write_snap(status: str, finished_at: float | None = None, error: str | None = None) -> None:
        try:
            params = dict(snapshot_params or {})
            if "provider" not in params:
                params.update(
                    {
                        "provider": provider_name,
                        "model": model,
                        "folder": str(input_dir),
                        "workers": workers,
                        "recursive": recursive,
                        "overwrite": overwrite,
                        "limit": limit,
                        "dry_run": dry_run,
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
                        "from_index": from_index,
                        "rate_limit_rpm": rate_limit_rpm,
                        "prompt": prompt_text,
                        "user_prompt": user_prompt_text,
                        "few_shot": [{"image": str(e.image), "caption": e.caption} for e in examples],
                    }
                )
            write_job_snapshot(
                input_dir,
                status=status,
                params=params,
                stats=_stats_dict(stats),
                started_at=started,
                finished_at=finished_at,
                error=error,
                state_dir=state_dir,
                kind=job_kind,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[snapshot] write failed: {exc}")

    _emit()
    _write_snap("running")

    if dry_run:
        print(
            f"[dry-run] total={stats.total} skip={stats.done_skip} todo={stats.todo} "
            f"workers={workers} temp={temperature} top_p={top_p} max_tokens={max_output_tokens} "
            f"seed={seed} max_side={max_image_side} prep={image_prep_enabled} "
            f"fmt={image_format} q={image_quality} "
            f"thinking={thinking_level} media_res={media_resolution} "
            f"rate_limit_rpm={rate_limit_rpm} few_shot={len(examples)}"
        )
        for p in todo[:20]:
            print(f"  would process: {p}")
            if collect_results:
                results.append(ImageResult(image=str(p), caption=None, error=None, skipped=False))
        if len(todo) > 20:
            print(f"  ... and {len(todo) - 20} more")
        _emit()
        _write_snap("finished", finished_at=time.time())
        if collect_results:
            return stats, results
        return stats

    if stats.todo == 0:
        print("Nothing to do (all captions present).")
        _emit()
        _write_snap("finished", finished_at=time.time())
        if collect_results:
            return stats, results
        return stats

    provider = get_provider(provider_name)
    workers = max(1, workers)
    limiter = rate_limiter if rate_limiter is not None else make_rate_limiter(rate_limit_rpm)

    from .run_batch_loop import run_caption_loop

    run_caption_loop(
        todo=todo,
        stats=stats,
        tracker=tracker,
        state=state,
        provider=provider,
        workers=workers,
        limiter=limiter,
        prompt_text=prompt_text,
        user_prompt_text=user_prompt_text,
        model=model,
        temperature=temperature,
        top_p=top_p,
        max_output_tokens=max_output_tokens,
        seed=seed,
        max_image_side=max_image_side,
        image_prep_enabled=image_prep_enabled,
        image_format=image_format,
        image_quality=image_quality,
        thinking_level=thinking_level,
        media_resolution=media_resolution,
        examples=examples,
        write_outputs=write_outputs,
        collect_results=collect_results,
        results=results,
        stop_event=stop_event,
        emit=_emit,
        write_snap=_write_snap,
    )

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
        "rate_limit_rpm": rate_limit_rpm,
        "few_shot_count": len(examples),
        "elapsed_sec": round(elapsed, 2),
        "errors_log": str(state.errors_path),
        "stopped": stopped,
        "kind": job_kind,
    }
    state.write_summary(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    final_status = "stopped" if stopped else "finished"
    _write_snap(final_status, finished_at=time.time())
    _emit()
    if collect_results:
        return stats, results
    return stats

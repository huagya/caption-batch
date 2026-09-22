from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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
from .prompts import DEFAULT_PROMPT
from .providers import get_provider
from .providers.base import CaptionRequest
from .rate_limit import RateLimiter, make_rate_limiter


@dataclass
class RunStats:
    total: int = 0
    todo: int = 0
    done_skip: int = 0
    ok: int = 0
    failed: int = 0


@dataclass
class ImageResult:
    image: str
    caption: str | None = None
    error: str | None = None
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "image": self.image,
            "caption": self.caption,
            "error": self.error,
            "skipped": self.skipped,
        }


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


def _stats_dict(stats: RunStats) -> dict[str, Any]:
    return {
        "total": stats.total,
        "todo": stats.todo,
        "done_skip": stats.done_skip,
        "ok": stats.ok,
        "failed": stats.failed,
        "skip": stats.done_skip,
        "fail": stats.failed,
    }


class _ProgressTracker:
    """Lock-friendly progress state for on_progress callbacks."""

    def __init__(self, stats: RunStats, started_at: float) -> None:
        self.stats = stats
        self.started_at = started_at
        self.current_image: str | None = None
        self.recent_done: list[dict[str, Any]] = []
        self.recent_errors: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._in_flight: set[str] = set()

    def set_current(self, image: Path | None) -> None:
        with self._lock:
            if image is None:
                return
            s = str(image)
            self._in_flight.add(s)
            self.current_image = s

    def clear_current(self, image: Path) -> None:
        with self._lock:
            s = str(image)
            self._in_flight.discard(s)
            if self.current_image == s:
                self.current_image = next(iter(self._in_flight), None)

    def record_done(self, image: Path, ok: bool, error: str = "") -> None:
        with self._lock:
            row = {"image": str(image), "ok": ok, "error": error or None}
            self.recent_done.append(row)
            if len(self.recent_done) > 20:
                self.recent_done = self.recent_done[-20:]
            if not ok:
                err_row = {
                    "image": str(image),
                    "error": error or "unknown",
                    "ts": time.time(),
                }
                self.recent_errors.append(err_row)
                if len(self.recent_errors) > 50:
                    self.recent_errors = self.recent_errors[-50:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            completed = self.stats.ok + self.stats.failed
            elapsed = max(0.0, time.time() - self.started_at)
            rate: float | None = None
            eta: float | None = None
            if completed > 0 and elapsed > 0:
                rate = completed / elapsed
                remaining = max(0, self.stats.todo - completed)
                if rate > 0:
                    eta = remaining / rate
            return {
                "stats": _stats_dict(self.stats),
                "current_image": self.current_image,
                "recent_done": list(self.recent_done),
                "recent_errors": list(self.recent_errors),
                "started_at": self.started_at,
                "rate_per_sec": rate,
                "eta_sec": eta,
                # flat convenience mirrors
                "total": self.stats.total,
                "todo": self.stats.todo,
                "ok": self.stats.ok,
                "fail": self.stats.failed,
                "skip": self.stats.done_skip,
            }


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

    examples = normalize_few_shot(few_shot)

    images = _resolve_image_list(
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

    # Throttle snapshot disk writes
    last_snap_write = [0.0]

    def work(image: Path) -> tuple[Path, bool, str, str | None]:
        tracker.set_current(image)
        out = caption_path_for(image)
        try:
            if limiter is not None:
                limiter.acquire()
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
                    few_shot=examples,
                )
            )
            if write_outputs:
                _atomic_write_text(out, text)
            return image, True, "", text
        except Exception as e:
            state.log_error(image, str(e))
            return image, False, str(e), None
        finally:
            tracker.clear_current(image)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(work, img): img for img in todo}
        with tqdm(total=len(futures), desc="captioning", unit="img") as bar:
            for fut in as_completed(list(futures.keys())):
                if stop_event is not None and stop_event.is_set():
                    for pending in futures:
                        pending.cancel()
                    break
                caption_text: str | None = None
                try:
                    _img, ok, _err, caption_text = fut.result()
                except Exception as e:  # cancelled or unexpected
                    if stop_event is not None and stop_event.is_set():
                        break
                    stats.failed += 1
                    bar.update(1)
                    _emit()
                    continue
                if ok:
                    stats.ok += 1
                else:
                    stats.failed += 1
                tracker.record_done(_img, ok, _err)
                if collect_results:
                    results.append(
                        ImageResult(
                            image=str(_img),
                            caption=caption_text if ok else None,
                            error=_err or None,
                            skipped=False,
                        )
                    )
                bar.update(1)
                bar.set_postfix(ok=stats.ok, fail=stats.failed, skip=stats.done_skip)
                _emit()
                now = time.time()
                if now - last_snap_write[0] >= 2.0:
                    _write_snap("running")
                    last_snap_write[0] = now

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

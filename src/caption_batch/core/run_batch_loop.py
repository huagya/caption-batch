from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from tqdm import tqdm

from .discover import caption_path_for
from .providers.base import CaptionRequest
from .runner_progress import ImageResult, ProgressTracker, RunState, RunStats, atomic_write_text


def run_caption_loop(
    *,
    todo: list[Path],
    stats: RunStats,
    tracker: ProgressTracker,
    state: RunState,
    provider: Any,
    workers: int,
    limiter: Any,
    prompt_text: str,
    user_prompt_text: str,
    model: str,
    temperature: float | None,
    top_p: float | None,
    max_output_tokens: int | None,
    seed: int | None,
    max_image_side: int,
    image_prep_enabled: bool,
    image_format: str,
    image_quality: int,
    thinking_level: str | None,
    media_resolution: str | None,
    examples: list,
    write_outputs: bool,
    collect_results: bool,
    results: list[ImageResult],
    stop_event: Any,
    emit: Callable[[], None],
    write_snap: Callable[..., None],
) -> None:
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
                    user_prompt=user_prompt_text,
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
                atomic_write_text(out, text)
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
                except Exception:
                    if stop_event is not None and stop_event.is_set():
                        break
                    stats.failed += 1
                    bar.update(1)
                    emit()
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
                emit()
                now = time.time()
                if now - last_snap_write[0] >= 2.0:
                    write_snap("running")
                    last_snap_write[0] = now

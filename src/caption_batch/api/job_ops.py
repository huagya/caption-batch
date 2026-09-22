"""Job start/preview execution helpers for the API."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from caption_batch.api.job_state import JOB
from caption_batch.api.schemas import StartJobBody
from caption_batch.core.job_snapshot import write_job_snapshot
from caption_batch.core.runner import ImageResult, RunStats, run_batch
from caption_batch.core.thinking import normalize_media_resolution, normalize_thinking_level
from caption_batch.logging_utils import get_logger

log = get_logger(__name__)


def few_shot_payload(body: StartJobBody) -> list[dict[str, str]]:
    if not body.few_shot:
        return []
    return [{"image": x.image, "caption": x.caption} for x in body.few_shot[:3]]


def params_for_snapshot(body: StartJobBody, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    d = body.model_dump()
    d["few_shot"] = few_shot_payload(body)
    if extra:
        d.update(extra)
    return d


def validate_job_common(body: StartJobBody) -> None:
    folder = body.folder.strip()
    if not folder:
        raise HTTPException(status_code=400, detail="folder must not be empty")
    if not Path(folder).is_dir():
        raise HTTPException(status_code=400, detail=f"not a directory: {folder}")
    if not body.model.strip():
        raise HTTPException(status_code=400, detail="model is required")
    if body.workers < 1:
        raise HTTPException(status_code=400, detail="workers must be >= 1")
    try:
        normalize_thinking_level(body.thinking_level)
        normalize_media_resolution(body.media_resolution)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.few_shot and len(body.few_shot) > 3:
        raise HTTPException(status_code=400, detail="few_shot max 3 examples")
    for item in body.few_shot or []:
        if not Path(item.image).is_file():
            raise HTTPException(status_code=400, detail=f"few_shot image not found: {item.image}")


def begin_job(body: StartJobBody, *, kind: str) -> None:
    with JOB._lock:
        if JOB.running:
            raise HTTPException(status_code=409, detail="a job is already running")
        JOB.running = True
        JOB.stop_event.clear()
        JOB.error = None
        JOB.stopped = False
        JOB.started_at = time.time()
        JOB.finished_at = None
        JOB.stats = RunStats()
        JOB.params = body.model_dump()
        JOB.kind = kind
        JOB.results = []
        JOB.current_image = None
        JOB.recent_done = []
        JOB.recent_errors = []
        JOB.rate_per_sec = None
        JOB.eta_sec = None
        JOB._folder = body.folder.strip()


def run_job(
    body: StartJobBody,
    *,
    kind: str = "batch",
    limit_override: int | None = None,
    write_outputs: bool = True,
) -> None:
    def on_progress(payload: dict) -> None:
        JOB.apply_progress(payload)

    folder = Path(body.folder.strip())
    try:
        thinking = normalize_thinking_level(body.thinking_level)
        media = normalize_media_resolution(body.media_resolution)
        if body.provider != "gemini":
            media = None
        few = few_shot_payload(body)
        rpm = body.rate_limit_rpm
        if rpm is not None and int(rpm) <= 0:
            rpm = None
        workers = body.workers
        limit = limit_override if limit_override is not None else body.limit
        if kind == "preview" and limit is not None:
            workers = min(workers, max(1, limit))

        collect = kind == "preview"
        snap_params = params_for_snapshot(body, extra={"kind": kind})
        result = run_batch(
            provider_name=body.provider,
            model=body.model.strip(),
            input_dir=folder,
            workers=workers,
            recursive=body.recursive,
            prompt=body.prompt,
            overwrite=body.overwrite,
            limit=limit,
            dry_run=body.dry_run,
            temperature=body.temperature,
            top_p=body.top_p,
            max_output_tokens=body.max_output_tokens,
            seed=body.seed,
            max_image_side=body.max_image_side,
            image_prep_enabled=body.image_prep_enabled,
            image_format=body.image_format,
            image_quality=body.image_quality,
            thinking_level=thinking,
            media_resolution=media,
            from_index=body.from_index,
            on_progress=on_progress,
            stop_event=JOB.stop_event,
            rate_limit_rpm=rpm,
            few_shot=few,
            collect_results=collect,
            write_outputs=write_outputs,
            snapshot_params=snap_params,
            job_kind=kind,
        )
        if collect:
            stats, image_results = result  # type: ignore[misc]
            JOB.apply_stats(stats)
            with JOB._lock:
                JOB.results = [
                    r.to_dict() if isinstance(r, ImageResult) else r for r in image_results
                ]
        else:
            JOB.apply_stats(result)  # type: ignore[arg-type]
        JOB.stopped = JOB.stop_event.is_set()
        if JOB.error:
            try:
                write_job_snapshot(
                    folder,
                    status="error",
                    params=snap_params,
                    stats={
                        "total": JOB.stats.total,
                        "todo": JOB.stats.todo,
                        "ok": JOB.stats.ok,
                        "failed": JOB.stats.failed,
                        "done_skip": JOB.stats.done_skip,
                    },
                    started_at=JOB.started_at,
                    finished_at=time.time(),
                    error=JOB.error,
                    kind=kind,
                )
            except Exception:
                pass
    except SystemExit as exc:
        JOB.error = str(exc)
        log.error("job SystemExit: %s", exc)
        try:
            write_job_snapshot(
                folder,
                status="error",
                params=params_for_snapshot(body, extra={"kind": kind}),
                stats={},
                started_at=JOB.started_at,
                finished_at=time.time(),
                error=str(exc),
                kind=kind,
            )
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        JOB.error = str(exc)
        log.exception("job failed: %s", exc)
        try:
            write_job_snapshot(
                folder,
                status="error",
                params=params_for_snapshot(body, extra={"kind": kind}),
                stats={},
                started_at=JOB.started_at,
                finished_at=time.time(),
                error=str(exc),
                kind=kind,
            )
        except Exception:
            pass
    finally:
        JOB.running = False
        JOB.finished_at = time.time()
        log.info(
            "job finished kind=%s ok=%s fail=%s skip=%s stopped=%s error=%s",
            kind,
            JOB.stats.ok,
            JOB.stats.failed,
            JOB.stats.done_skip,
            JOB.stopped,
            JOB.error,
        )

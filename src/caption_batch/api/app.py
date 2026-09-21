"""FastAPI app: /api/* + static WebUI from web/."""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from caption_batch.core.image_prep import DEFAULT_MAX_IMAGE_SIDE
from caption_batch.core.list_models import format_table, list_gemini, list_openrouter, to_json
from caption_batch.core.prompts import DEFAULT_PROMPT
from caption_batch.core.runner import RunStats, run_batch
from caption_batch.logging_utils import configure_logging, get_logger, get_recent_logs, setup_file_logging
from caption_batch.run_server import find_project_root, load_dotenv_files

configure_logging()
log = get_logger(__name__)

WEB_DIR = Path(__file__).resolve().parents[3] / "web"

app = FastAPI(title="caption_batch", version="0.3.0")

_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class JobState:
    """In-process job tracker (single job at a time)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.running = False
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.error: str | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.params: dict[str, Any] = {}
        self.stats = RunStats()
        self.stopped = False

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self.running,
                "stopped": self.stopped,
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "params": dict(self.params),
                "total": self.stats.total,
                "todo": self.stats.todo,
                "ok": self.stats.ok,
                "fail": self.stats.failed,
                "skip": self.stats.done_skip,
            }

    def apply_stats(self, stats: RunStats) -> None:
        with self._lock:
            self.stats = stats


JOB = JobState()


@app.on_event("startup")
def _startup() -> None:
    root = find_project_root()
    try:
        load_dotenv_files(root)
    except Exception as exc:  # noqa: BLE001
        log.warning("load_dotenv failed: %s", exc)
    try:
        setup_file_logging(root / "logs")
    except Exception as exc:  # noqa: BLE001
        log.warning("file logging setup on startup failed: %s", exc)


class SaveKeysBody(BaseModel):
    gemini_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None


class StartJobBody(BaseModel):
    provider: Literal["gemini", "openrouter"]
    model: str = Field(..., min_length=1)
    folder: str = Field(..., min_length=1)
    workers: int = 4
    limit: Optional[int] = None
    overwrite: bool = False
    dry_run: bool = False
    recursive: bool = True
    temperature: Optional[float] = 0.2
    max_output_tokens: Optional[int] = 1024
    max_image_side: int = DEFAULT_MAX_IMAGE_SIDE
    prompt: Optional[str] = None
    from_index: bool = False


class ListModelsBody(BaseModel):
    provider: Literal["gemini", "openrouter"]
    vision_only: bool = True
    as_json: bool = False
    contains: Optional[str] = None


def _upsert_env_file(path: Path, updates: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    order: list[str] = []
    other_lines: list[str] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                other_lines.append(line)
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k in updates:
                existing[k] = updates[k]
                order.append(k)
            else:
                existing[k] = v
                order.append(k)
    for k, v in updates.items():
        if k not in existing:
            order.append(k)
            existing[k] = v
    # Rebuild: keep comments/blank from original at top, then keys
    out: list[str] = []
    seen_keys: set[str] = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                out.append(line)
                continue
            k = line.partition("=")[0].strip()
            if k in updates:
                out.append(f"{k}={updates[k]}")
                seen_keys.add(k)
            else:
                out.append(line)
                seen_keys.add(k)
    for k, v in updates.items():
        if k not in seen_keys:
            out.append(f"{k}={v}")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": "0.3.0"}


@app.get("/api/defaults")
def defaults() -> dict:
    return {
        "prompt": DEFAULT_PROMPT,
        "temperature": 0.2,
        "max_output_tokens": 1024,
        "max_image_side": DEFAULT_MAX_IMAGE_SIDE,
        "workers": 4,
        "providers": ["gemini", "openrouter"],
    }


@app.post("/api/list-models")
def api_list_models(body: ListModelsBody) -> dict:
    try:
        if body.provider == "openrouter":
            models = list_openrouter(vision_only=body.vision_only)
        else:
            models = list_gemini(vision_only=body.vision_only)
    except SystemExit as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if body.contains:
        q = body.contains.lower()
        models = [m for m in models if q in m.id.lower() or q in (m.name or "").lower()]
    text = to_json(models) if body.as_json else format_table(models)
    return {"provider": body.provider, "count": len(models), "text": text}


@app.post("/api/save-keys")
def save_keys(body: SaveKeysBody) -> dict:
    root = find_project_root()
    updates: dict[str, str] = {}
    if body.gemini_api_key is not None and body.gemini_api_key.strip():
        updates["GEMINI_API_KEY"] = body.gemini_api_key.strip()
    if body.openrouter_api_key is not None and body.openrouter_api_key.strip():
        updates["OPENROUTER_API_KEY"] = body.openrouter_api_key.strip()
    if not updates:
        raise HTTPException(status_code=400, detail="No keys provided")
    for k in updates:
        if not _ENV_KEY_RE.match(k):
            raise HTTPException(status_code=400, detail=f"Invalid key name: {k}")
    env_path = root / ".env"
    _upsert_env_file(env_path, updates)
    for k, v in updates.items():
        os.environ[k] = v
    log.info("api.save-keys wrote %s keys to .env", list(updates.keys()))
    return {"ok": True, "updated": list(updates.keys()), "path": str(env_path)}


def _run_job(body: StartJobBody) -> None:
    def on_progress(stats: RunStats) -> None:
        JOB.apply_stats(stats)

    try:
        stats = run_batch(
            provider_name=body.provider,
            model=body.model.strip(),
            input_dir=Path(body.folder.strip()),
            workers=body.workers,
            recursive=body.recursive,
            prompt=body.prompt,
            overwrite=body.overwrite,
            limit=body.limit,
            dry_run=body.dry_run,
            temperature=body.temperature,
            max_output_tokens=body.max_output_tokens,
            max_image_side=body.max_image_side,
            from_index=body.from_index,
            progress_cb=on_progress,
            stop_event=JOB.stop_event,
        )
        JOB.apply_stats(stats)
        JOB.stopped = JOB.stop_event.is_set()
    except SystemExit as exc:
        JOB.error = str(exc)
        log.error("job SystemExit: %s", exc)
    except Exception as exc:  # noqa: BLE001
        JOB.error = str(exc)
        log.exception("job failed: %s", exc)
    finally:
        JOB.running = False
        JOB.finished_at = time.time()
        log.info(
            "job finished ok=%s fail=%s skip=%s stopped=%s error=%s",
            JOB.stats.ok,
            JOB.stats.failed,
            JOB.stats.done_skip,
            JOB.stopped,
            JOB.error,
        )


@app.post("/api/job/start")
def job_start(body: StartJobBody) -> dict:
    folder = body.folder.strip()
    if not folder:
        raise HTTPException(status_code=400, detail="folder must not be empty")
    if not Path(folder).is_dir():
        raise HTTPException(status_code=400, detail=f"not a directory: {folder}")
    if not body.model.strip():
        raise HTTPException(status_code=400, detail="model is required")
    if body.workers < 1:
        raise HTTPException(status_code=400, detail="workers must be >= 1")

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

    log.info(
        "api.job.start provider=%s model=%s folder=%s dry_run=%s",
        body.provider,
        body.model,
        folder,
        body.dry_run,
    )
    t = threading.Thread(target=_run_job, args=(body,), name="caption-batch-job", daemon=True)
    JOB.thread = t
    t.start()
    return {"ok": True, "status": JOB.snapshot()}


@app.post("/api/job/stop")
def job_stop() -> dict:
    if not JOB.running:
        return {"ok": True, "message": "no job running", "status": JOB.snapshot()}
    JOB.stop_event.set()
    log.info("api.job.stop requested")
    return {"ok": True, "message": "stop requested", "status": JOB.snapshot()}


@app.get("/api/job/status")
def job_status() -> dict:
    return JOB.snapshot()


@app.get("/api/debug/logs")
def debug_logs(limit: int = 100) -> dict:
    return {"logs": get_recent_logs(limit=limit)}


@app.post("/api/diagnostics/collect")
def diagnostics_collect() -> dict:
    from caption_batch.diagnostics import collect_diagnostics

    result = collect_diagnostics(find_project_root())
    log.info("api.diagnostics.collect zip=%s", result.get("zip_path"))
    return result


if WEB_DIR.is_dir():
    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
else:
    log.warning("web directory missing: %s", WEB_DIR)


def create_app() -> FastAPI:
    return app

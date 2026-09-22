"""FastAPI app: /api/* + static WebUI from web/."""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from caption_batch import __version__
from caption_batch.api.job_ops import begin_job, run_job, validate_job_common
from caption_batch.api.job_state import JOB
from caption_batch.api.routes_settings import register_settings_routes
from caption_batch.api.schemas import PreviewJobBody, StartJobBody
from caption_batch.core.job_snapshot import read_job_snapshot
from caption_batch.logging_utils import configure_logging, get_logger, get_recent_logs, setup_file_logging
from caption_batch.run_server import find_project_root, load_dotenv_files

configure_logging()
log = get_logger(__name__)

WEB_DIR = Path(__file__).resolve().parents[3] / "web"

app = FastAPI(title="caption_batch", version=__version__)
register_settings_routes(app)


@app.on_event("startup")
def _startup() -> None:
    root = find_project_root()
    try:
        load_dotenv_files(root)
    except Exception as exc:  # noqa: BLE001
        log.warning("load_dotenv failed: %s", exc)
    try:
        setup_file_logging(root / "logs", fresh_latest=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("file logging setup on startup failed: %s", exc)


@app.post("/api/job/start")
def job_start(body: StartJobBody) -> dict:
    validate_job_common(body)
    folder = body.folder.strip()
    begin_job(body, kind="batch")
    log.info(
        "api.job.start provider=%s model=%s folder=%s dry_run=%s",
        body.provider,
        body.model,
        folder,
        body.dry_run,
    )
    t = threading.Thread(
        target=run_job, args=(body,), kwargs={"kind": "batch"}, name="caption-batch-job", daemon=True
    )
    JOB.thread = t
    t.start()
    return {"ok": True, "status": JOB.snapshot()}


@app.post("/api/job/preview")
def job_preview(body: PreviewJobBody) -> dict:
    """Short preview batch (1–5 images). Background job; poll /api/job/status for results."""
    validate_job_common(body)
    count = max(1, min(5, int(body.preview_count or 3)))
    write_outputs = bool(body.preview_write)
    begin_job(body, kind="preview")
    with JOB._lock:
        JOB.params["preview_count"] = count
        JOB.params["preview_write"] = write_outputs
    log.info(
        "api.job.preview provider=%s model=%s folder=%s count=%s write=%s",
        body.provider,
        body.model,
        body.folder.strip(),
        count,
        write_outputs,
    )
    t = threading.Thread(
        target=run_job,
        args=(body,),
        kwargs={"kind": "preview", "limit_override": count, "write_outputs": write_outputs},
        name="caption-batch-preview",
        daemon=True,
    )
    JOB.thread = t
    t.start()
    return {"ok": True, "status": JOB.snapshot(), "preview_count": count}


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


@app.get("/api/job/snapshot")
def job_snapshot(folder: str) -> dict:
    """Read last job_snapshot.json from dataset .caption_state/."""
    folder = (folder or "").strip()
    if not folder:
        raise HTTPException(status_code=400, detail="folder query param required")
    p = Path(folder)
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"not a directory: {folder}")
    data = read_job_snapshot(p)
    if data is None:
        return {"ok": True, "exists": False, "folder": folder, "snapshot": None}
    return {"ok": True, "exists": True, "folder": folder, "snapshot": data}


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

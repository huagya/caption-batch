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

from caption_batch.core.image_prep import (
    DEFAULT_IMAGE_FORMAT,
    DEFAULT_IMAGE_PREP_ENABLED,
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_MAX_IMAGE_SIDE,
)
from caption_batch import __version__
from caption_batch.core.list_models import format_table, list_gemini, list_openrouter, to_json
from caption_batch.core.prompts import DEFAULT_PROMPT
from caption_batch.core.runner import RunStats, run_batch
from caption_batch.core.thinking import normalize_media_resolution, normalize_thinking_level
from caption_batch.logging_utils import configure_logging, get_logger, get_recent_logs, setup_file_logging
from caption_batch.run_server import find_project_root, load_dotenv_files

configure_logging()
log = get_logger(__name__)

WEB_DIR = Path(__file__).resolve().parents[3] / "web"

app = FastAPI(title="caption_batch", version=__version__)

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
    # After uvicorn dictConfig may have closed handlers; setup_file_logging repairs.
    try:
        setup_file_logging(root / "logs", fresh_latest=True)
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
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_output_tokens: Optional[int] = 1024
    seed: Optional[int] = None
    max_image_side: int = DEFAULT_MAX_IMAGE_SIDE
    image_prep_enabled: bool = DEFAULT_IMAGE_PREP_ENABLED
    image_format: Literal["jpeg", "webp", "png"] = DEFAULT_IMAGE_FORMAT
    image_quality: int = DEFAULT_IMAGE_QUALITY
    thinking_level: Optional[str] = None
    media_resolution: Optional[str] = None
    prompt: Optional[str] = None
    from_index: bool = False


class UiSettingsBody(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


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
    return {"status": "ok", "version": __version__}


UI_SETTINGS_SCHEMA = 2
UI_SETTINGS_KEYS = (
    "provider",
    "model",
    "folder",
    "workers",
    "limit",
    "overwrite",
    "dry_run",
    "recursive",
    "from_index",
    "temperature",
    "top_p",
    "max_output_tokens",
    "seed",
    "max_image_side",
    "image_prep_enabled",
    "image_format",
    "image_quality",
    "thinking_level",
    "media_resolution",
    "prompt",
)
# Keys that must never be persisted in ui-settings.json
UI_SETTINGS_FORBIDDEN = {
    "gemini_api_key",
    "openrouter_api_key",
    "api_key",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
}


def _ui_settings_path() -> Path:
    return find_project_root() / "ui-settings.json"


@app.get("/api/defaults")
def defaults() -> dict:
    return {
        "prompt": DEFAULT_PROMPT,
        "temperature": None,
        "top_p": None,
        "max_output_tokens": 1024,
        "seed": None,
        "max_image_side": DEFAULT_MAX_IMAGE_SIDE,
        "image_prep_enabled": DEFAULT_IMAGE_PREP_ENABLED,
        "image_format": DEFAULT_IMAGE_FORMAT,
        "image_quality": DEFAULT_IMAGE_QUALITY,
        "thinking_level": None,
        "media_resolution": None,
        "workers": 4,
        "providers": ["gemini", "openrouter"],
        "thinking_levels": ["none", "minimal", "low", "medium", "high"],
        "media_resolutions": ["low", "medium", "high"],
        "help": {
            "image_prep_enabled": "OFF=元ファイルをそのまま送信（再エンコードなし）。ON=必要なら縮小し、常に指定フォーマットへ再エンコード。拡大はしません。",
            "max_image_side": "最長辺の上限。これを超える場合のみ縮小（拡大なし）。既定 768。",
            "image_format": "再エンコード先フォーマット: jpeg / webp / png（prep ON 時）。既定 webp。",
            "image_quality": "1–100。webp の 100=可逆。png の 100=圧縮ほぼなし。jpeg は通常の品質。",
            "temperature": "空欄=API既定を送信しない。Gemini 3.x では空欄推奨（公式）。",
            "top_p": "空欄=API既定を送信しない。Gemini 3.x では空欄推奨。",
            "max_output_tokens": "キャプション長の上限。空欄で省略可。既定 1024。thinking を使う場合は思考トークンもここから消費するため、medium/high では 2048 以上を推奨。",
            "seed": "再現用シード。空欄=送信しない。Gemini / OpenRouter 対応。",
            "thinking_level": "モデルが回答前に内部で考える量。上がるほど丁寧だが遅く・高い。思考トークンも課金され max_output_tokens を消費する。空欄＝API既定。Gemini 3.x は完全オフ不可（none≈minimal）。大量処理は low/minimal 推奨。難しいカットだけ medium/high。",
            "media_resolution": "画像をAPI側でどの解像度相当で見るか（Geminiのみ）。空欄＝API既定。コスト削減なら低い方。OpenRouter では無視／非表示。",
        },
        "notes": {
            "gemini_3x": "Gemini 3.x では temperature / top_p は空欄推奨（公式）。thinking の none は minimal 相当（完全オフ不可）。",
        },
    }


@app.get("/api/ui-settings")
def get_ui_settings() -> dict:
    """Load durable UI settings from project-root ui-settings.json."""
    path = _ui_settings_path()
    defaults_payload = defaults()
    base_settings = {k: defaults_payload[k] for k in (
        "temperature", "top_p", "max_output_tokens", "seed",
        "max_image_side", "image_prep_enabled", "image_format", "image_quality",
        "thinking_level", "media_resolution",
        "workers", "prompt",
    )}
    base_settings.update({
        "provider": "gemini",
        "model": "",
        "folder": "",
        "limit": None,
        "overwrite": False,
        "dry_run": False,
        "recursive": True,
        "from_index": False,
    })
    if not path.is_file():
        return {"ok": True, "exists": False, "schema": UI_SETTINGS_SCHEMA, "settings": base_settings, "path": str(path)}
    try:
        import json as _json
        from datetime import datetime, timezone

        raw = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"failed to read ui-settings: {exc}") from exc
    stored = raw.get("settings") if isinstance(raw, dict) else None
    if not isinstance(stored, dict):
        stored = {}
    merged = dict(base_settings)
    for k in UI_SETTINGS_KEYS:
        if k in stored and k not in UI_SETTINGS_FORBIDDEN:
            merged[k] = stored[k]
    return {
        "ok": True,
        "exists": True,
        "schema": raw.get("schema", UI_SETTINGS_SCHEMA) if isinstance(raw, dict) else UI_SETTINGS_SCHEMA,
        "updated_at": raw.get("updated_at") if isinstance(raw, dict) else None,
        "settings": merged,
        "path": str(path),
    }


@app.post("/api/ui-settings")
def save_ui_settings(body: UiSettingsBody) -> dict:
    """Persist UI settings (no API keys) to project-root ui-settings.json."""
    import json as _json
    from datetime import datetime, timezone

    incoming = body.settings or {}
    cleaned: dict[str, Any] = {}
    for k, v in incoming.items():
        if k in UI_SETTINGS_FORBIDDEN:
            continue
        if k not in UI_SETTINGS_KEYS:
            continue
        cleaned[k] = v
    payload = {
        "schema": UI_SETTINGS_SCHEMA,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "settings": cleaned,
    }
    path = _ui_settings_path()
    path.write_text(_json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log.info("api.ui-settings saved %s keys to %s", list(cleaned.keys()), path)
    return {"ok": True, "path": str(path), "updated_at": payload["updated_at"], "keys": list(cleaned.keys())}


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
        thinking = normalize_thinking_level(body.thinking_level)
        media = normalize_media_resolution(body.media_resolution)
        if body.provider != "gemini":
            media = None
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
    try:
        normalize_thinking_level(body.thinking_level)
        normalize_media_resolution(body.media_resolution)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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

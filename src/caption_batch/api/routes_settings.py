from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from caption_batch import __version__
from caption_batch.api.schemas import (
    UI_SETTINGS_FORBIDDEN,
    UI_SETTINGS_KEYS,
    UI_SETTINGS_SCHEMA,
    ListModelsBody,
    SaveKeysBody,
    UiSettingsBody,
)
from caption_batch.core.image_prep import (
    DEFAULT_IMAGE_FORMAT,
    DEFAULT_IMAGE_PREP_ENABLED,
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_MAX_IMAGE_SIDE,
)
from caption_batch.core.list_models import format_table, list_gemini, list_openrouter, to_json
from caption_batch.core.prompts import DEFAULT_PROMPT, DEFAULT_USER_PROMPT
from caption_batch.logging_utils import get_logger
from caption_batch.run_server import find_project_root
from caption_batch.api.routes_settings_helpers import _upsert_env_file, _ui_settings_path, _ENV_KEY_RE

log = get_logger(__name__)

def register_settings_routes(app: FastAPI) -> None:
    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/defaults")
    def defaults() -> dict:
        return {
            "prompt": DEFAULT_PROMPT,
            "user_prompt": DEFAULT_USER_PROMPT,
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
            "rate_limit_rpm": 0,
            "preview_count": 3,
            "few_shot": [],
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
                "rate_limit_rpm": "1分あたりのAPI呼び出し上限。0または空＝制限なし。429が多いときは 20〜60 を試してください。",
                "preview": "本番の前に数枚だけ試します。結果はプレビュー欄に表示され、既定では .txt も書きます（ディスクと画面を一致）。",
                "snapshot_resume": "「前回の設定を読込」でフォルダ内の最終ジョブ設定を復元。上書きOFFのまま Start すると、既にある .txt はスキップして続きから進めます。",
                "few_shot": "お手本の画像＋キャプションを最大3組。モデルに「こんな書き方で」と示します。空欄なら従来どおり。",
                "prompt": "システム指示（役割・ルール・出力形式）。長いルールはここに。プロバイダの system 枠へ送られます。",
                "user_prompt": "ユーザー指示（画像ごとの短い指示）。空欄なら既定「Caption this image.」。Gemini は画像の後、OpenRouter は画像の前に置きます。",
            },
            "notes": {
                "gemini_3x": "Gemini 3.x では temperature / top_p は空欄推奨（公式）。thinking の none は minimal 相当（完全オフ不可）。",
                "next_sharding": "複数PCでの分割処理（sharding）は次バージョン以降の予定です。",
            },
        }

    @app.get("/api/ui-settings")
    def get_ui_settings() -> dict:
        path = _ui_settings_path()
        defaults_payload = defaults()
        base_settings = {k: defaults_payload[k] for k in (
            "temperature", "top_p", "max_output_tokens", "seed",
            "max_image_side", "image_prep_enabled", "image_format", "image_quality",
            "thinking_level", "media_resolution",
            "workers", "prompt", "user_prompt", "rate_limit_rpm", "preview_count", "few_shot",
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

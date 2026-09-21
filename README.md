# caption-batch

Windows tool for batch image captioning (Gemini / OpenRouter).

**Gradio UI is retired.** Same layout as other huagya tools:

- **core** — captioning logic (discover / runner / providers / prompts)
- **FastAPI** — local API (job start/stop/status, model list, key save)
- **static WebUI** — `web/`
- **Typer CLI** — `caption-batch` / `python -m caption_batch.cli`
- **install.bat / start.bat / update.bat** — double-click workflow
- **port.json** — default port **8771** (8751=prepend, 8761=pair-filter)

## Windows quick start

1. Clone
   ```bat
   git clone https://github.com/huagya/caption-batch.git
   cd caption-batch
   ```
2. Double-click `install.bat` (creates `.venv` + installs deps)
3. Copy `.env.example` to `.env` and set keys
   ```
   GEMINI_API_KEY=...
   OPENROUTER_API_KEY=...
   ```
4. Double-click `start.bat` → browser opens `http://127.0.0.1:8771/`
5. In the WebUI pick provider/model/folder and press **Start**

If you ever pasted keys in chat, **rotate them**. `.env` is gitignored.

Example models (IDs change over time): `gemini-3.5-flash-lite` / OpenRouter vision models.

## CLI

```bat
.venv\Scripts\activate
caption-batch run --provider gemini --model gemini-3.5-flash-lite --input-dir D:\dataset --workers 4
caption-batch list-models --provider openrouter
caption-batch build-index --input-dir D:\dataset
caption-batch retry-failed --provider gemini --model gemini-3.5-flash-lite --input-dir D:\dataset --errors D:\dataset\.caption_state\errors.jsonl
caption-batch selfcheck
caption-batch serve
```

## Diagnostics

- `selfcheck.bat` — import + dry-run + thin API/static check
- `smoke.bat` — dry-run against `_smoke`
- `collect-diagnostics.bat` — `diagnostics/diagnostics-*.zip` (no secrets)

## Dev

```bat
pip install -e ".[dev]"
pytest
python scripts/selfcheck.py
```

## About the old Gradio version

The previous Gradio-centric layout (`app.py` / `setup.bat` / `run_ui.bat` / `requirements.txt`) was removed. Core captioning logic (providers, runner, resume, workers, temperature, etc.) is kept.

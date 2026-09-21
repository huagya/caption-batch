"""Gradio UI for caption-batch — thin wrapper over caption_batch core."""
from __future__ import annotations

import os
from pathlib import Path

import gradio as gr

from caption_batch.image_prep import DEFAULT_MAX_IMAGE_SIDE
from caption_batch.list_models import format_table, list_gemini, list_openrouter
from caption_batch.runner import run_batch

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"


def _load_dotenv(path: Path = ENV_PATH) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_dotenv()


def _apply_keys(gemini_key: str, openrouter_key: str) -> None:
    if gemini_key and gemini_key.strip():
        os.environ["GEMINI_API_KEY"] = gemini_key.strip()
    if openrouter_key and openrouter_key.strip():
        os.environ["OPENROUTER_API_KEY"] = openrouter_key.strip()


def _save_env(gemini_key: str, openrouter_key: str) -> str:
    """Write/update local .env only (gitignored)."""
    existing: dict[str, str] = {}
    if ENV_PATH.is_file():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            existing[k.strip()] = v.strip()
    if gemini_key.strip():
        existing["GEMINI_API_KEY"] = gemini_key.strip()
    if openrouter_key.strip():
        existing["OPENROUTER_API_KEY"] = openrouter_key.strip()
    existing.setdefault(
        "OPENROUTER_HTTP_REFERER",
        "https://github.com/huagya/caption-batch",
    )
    existing.setdefault("OPENROUTER_APP_TITLE", "caption-batch")
    lines = [
        "# Local only — never commit",
        f"GEMINI_API_KEY={existing.get('GEMINI_API_KEY', '')}",
        f"OPENROUTER_API_KEY={existing.get('OPENROUTER_API_KEY', '')}",
        f"OPENROUTER_HTTP_REFERER={existing.get('OPENROUTER_HTTP_REFERER', '')}",
        f"OPENROUTER_APP_TITLE={existing.get('OPENROUTER_APP_TITLE', '')}",
        "",
    ]
    ENV_PATH.write_text("\n".join(lines), encoding="utf-8")
    _apply_keys(gemini_key, openrouter_key)
    return f".env を保存しました: {ENV_PATH}"


def _default_model(provider: str) -> str:
    if provider == "openrouter":
        return "google/gemini-2.5-flash-lite"
    return "gemini-3.5-flash-lite"


def do_list_models(provider: str, gemini_key: str, openrouter_key: str, contains: str) -> str:
    _apply_keys(gemini_key, openrouter_key)
    try:
        if provider == "openrouter":
            models = list_openrouter(vision_only=True)
        else:
            models = list_gemini(vision_only=True)
        if contains and contains.strip():
            q = contains.strip().lower()
            models = [m for m in models if q in m.id.lower() or q in (m.name or "").lower()]
        return format_table(models)
    except SystemExit as e:
        return f"エラー: {e}"
    except Exception as e:
        return f"エラー: {e}"


def do_run(
    provider: str,
    model: str,
    input_dir: str,
    workers: int,
    limit: float,
    overwrite: bool,
    dry_run: bool,
    temperature: float,
    max_output_tokens: float,
    max_image_side: float,
    prompt: str,
    gemini_key: str,
    openrouter_key: str,
) -> str:
    _apply_keys(gemini_key, openrouter_key)
    if not input_dir or not input_dir.strip():
        return "入力フォルダを指定してください。"
    folder = Path(input_dir.strip())
    if not folder.is_dir():
        return f"フォルダが見つかりません: {folder}"
    model = (model or "").strip() or _default_model(provider)
    lim = None
    if limit is not None and float(limit) > 0:
        lim = int(limit)
    temp = float(temperature) if temperature is not None else 0.2
    tokens = int(max_output_tokens) if max_output_tokens and float(max_output_tokens) > 0 else 1024
    side = int(max_image_side) if max_image_side and float(max_image_side) > 0 else DEFAULT_MAX_IMAGE_SIDE
    try:
        stats = run_batch(
            provider_name=provider,
            model=model,
            input_dir=folder,
            workers=int(workers) if workers else 1,
            recursive=True,
            prompt=prompt.strip() or None,
            overwrite=bool(overwrite),
            limit=lim,
            dry_run=bool(dry_run),
            temperature=temp,
            max_output_tokens=tokens,
            max_image_side=side,
        )
    except SystemExit as e:
        return f"エラー: {e}"
    except Exception as e:
        return f"エラー: {e}"

    summary_path = folder / ".caption_state" / "last_run_summary.json"
    extra = ""
    if summary_path.is_file():
        try:
            extra = "\n\n" + summary_path.read_text(encoding="utf-8")
        except OSError:
            pass
    return (
        f"完了\n"
        f"total={stats.total} skip={stats.done_skip} ok={stats.ok} failed={stats.failed} todo={stats.todo}"
        f"{extra}"
    )


def build() -> gr.Blocks:
    with gr.Blocks(title="caption-batch") as demo:
        gr.Markdown(
            "# caption-batch\n"
            "大量画像キャプション（Gemini / OpenRouter）。コアは CLI と同じです。\n"
            "初回は `setup.bat` → `.env` にキー → `run_ui.bat`。\n"
            "⚠️ チャットにキーを貼った場合は必ずローテートしてください。"
        )
        with gr.Row():
            provider = gr.Dropdown(
                choices=["gemini", "openrouter"],
                value="gemini",
                label="Provider",
            )
            model = gr.Textbox(value="gemini-3.5-flash-lite", label="Model ID")
        input_dir = gr.Textbox(
            label="画像フォルダ（フルパス）",
            placeholder=r"D:\dataset\images",
        )
        with gr.Row():
            workers = gr.Number(value=2, precision=0, label="Workers")
            limit = gr.Number(value=0, precision=0, label="Limit（0=全部）")
            overwrite = gr.Checkbox(value=False, label="既存.txtを上書き")
            dry_run = gr.Checkbox(value=False, label="Dry-run（API呼ばない）")
        with gr.Row():
            temperature = gr.Number(value=0.2, label="Temperature")
            max_output_tokens = gr.Number(value=1024, precision=0, label="Max output tokens")
            max_image_side = gr.Number(
                value=DEFAULT_MAX_IMAGE_SIDE, precision=0, label="Max image side (px)"
            )
        prompt = gr.Textbox(
            lines=3,
            label="プロンプト（空ならデフォルト）",
            placeholder="空欄でデフォルトプロンプト",
        )
        with gr.Accordion("API キー（このPCの .env に保存可）", open=False):
            gemini_key = gr.Textbox(
                type="password",
                label="GEMINI_API_KEY",
                value=os.environ.get("GEMINI_API_KEY", ""),
            )
            openrouter_key = gr.Textbox(
                type="password",
                label="OPENROUTER_API_KEY",
                value=os.environ.get("OPENROUTER_API_KEY", ""),
            )
            save_btn = gr.Button("このPCの .env に保存")
            save_out = gr.Textbox(label="保存結果", lines=1)

        with gr.Row():
            run_btn = gr.Button("キャプション実行", variant="primary")
            list_btn = gr.Button("モデル一覧")
            contains = gr.Textbox(label="モデル絞り込み", placeholder="flash / gemini など")

        out = gr.Textbox(label="結果", lines=18)

        def on_provider(p: str) -> str:
            return _default_model(p)

        provider.change(on_provider, inputs=[provider], outputs=[model])
        save_btn.click(fn=_save_env, inputs=[gemini_key, openrouter_key], outputs=[save_out])
        list_btn.click(
            fn=do_list_models,
            inputs=[provider, gemini_key, openrouter_key, contains],
            outputs=[out],
        )
        run_btn.click(
            fn=do_run,
            inputs=[
                provider,
                model,
                input_dir,
                workers,
                limit,
                overwrite,
                dry_run,
                temperature,
                max_output_tokens,
                max_image_side,
                prompt,
                gemini_key,
                openrouter_key,
            ],
            outputs=[out],
        )
    return demo


def _pick_port(host: str = "127.0.0.1", start: int = 7860, end: int = 7890) -> int:
    import socket

    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(f"No free port in {start}-{end}. Close other Gradio/caption-batch windows.")


if __name__ == "__main__":
    port = _pick_port()
    print(f"Launching on http://127.0.0.1:{port}")
    build().launch(server_name="127.0.0.1", server_port=port, inbrowser=True)

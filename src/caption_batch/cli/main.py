"""Typer CLI for caption-batch."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import typer
from tqdm import tqdm

from caption_batch.core.discover import build_image_index, caption_path_for, is_done
from caption_batch.core.image_prep import (
    DEFAULT_IMAGE_FORMAT,
    DEFAULT_IMAGE_PREP_ENABLED,
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_MAX_IMAGE_SIDE,
)
from caption_batch.core.list_models import format_table, list_gemini, list_openrouter, to_json
from caption_batch.core.prompts import DEFAULT_PROMPT
from caption_batch.core.providers import get_provider
from caption_batch.core.providers.base import CaptionRequest
from caption_batch.core.runner import RunState, _atomic_write_text, run_batch
from caption_batch.logging_utils import configure_logging, get_logger, setup_file_logging
from caption_batch.run_server import find_project_root, load_dotenv_files

configure_logging()
try:
    _root = find_project_root()
    load_dotenv_files(_root)
    setup_file_logging(_root / "logs")
except Exception:
    pass
log = get_logger(__name__)

app = typer.Typer(
    name="caption-batch",
    help="Batch image captioning (Gemini / OpenRouter).",
    no_args_is_help=True,
)


def _temp_tokens(
    temperature: Optional[float],
    no_temperature: bool,
    max_output_tokens: Optional[int],
    no_max_output_tokens: bool,
) -> tuple[Optional[float], Optional[int]]:
    return (
        None if no_temperature else temperature,
        None if no_max_output_tokens else max_output_tokens,
    )


@app.command("run")
def run_cmd(
    provider: str = typer.Option(..., "--provider", help="gemini | openrouter"),
    model: str = typer.Option(..., "--model"),
    input_dir: Path = typer.Option(..., "--input-dir"),
    workers: int = typer.Option(4, "--workers"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive"),
    prompt: Optional[str] = typer.Option(None, "--prompt"),
    prompt_file: Optional[Path] = typer.Option(None, "--prompt-file"),
    state_dir: Optional[Path] = typer.Option(None, "--state-dir"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    limit: Optional[int] = typer.Option(None, "--limit"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    from_index: bool = typer.Option(False, "--from-index"),
    temperature: Optional[float] = typer.Option(None, "--temperature", help="Omit to use API default"),
    no_temperature: bool = typer.Option(False, "--no-temperature", help="Force omit temperature"),
    top_p: Optional[float] = typer.Option(None, "--top-p", help="Omit to use API default"),
    max_output_tokens: Optional[int] = typer.Option(1024, "--max-output-tokens"),
    no_max_output_tokens: bool = typer.Option(False, "--no-max-output-tokens"),
    seed: Optional[int] = typer.Option(None, "--seed", help="Omit to use API default"),
    max_image_side: int = typer.Option(DEFAULT_MAX_IMAGE_SIDE, "--max-image-side"),
    image_prep: bool = typer.Option(DEFAULT_IMAGE_PREP_ENABLED, "--image-prep/--no-image-prep"),
    image_format: str = typer.Option(DEFAULT_IMAGE_FORMAT, "--image-format", help="jpeg|webp|png"),
    image_quality: int = typer.Option(DEFAULT_IMAGE_QUALITY, "--image-quality"),
) -> None:
    """Caption images in a folder."""
    if provider not in ("gemini", "openrouter"):
        typer.secho("provider must be gemini or openrouter", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if image_format not in ("jpeg", "webp", "png"):
        typer.secho("image-format must be jpeg|webp|png", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    temp, tokens = _temp_tokens(
        temperature, no_temperature, max_output_tokens, no_max_output_tokens
    )
    log.info("cli.run provider=%s model=%s dir=%s", provider, model, input_dir)
    stats = run_batch(
        provider_name=provider,
        model=model,
        input_dir=input_dir,
        workers=workers,
        recursive=recursive,
        prompt=prompt,
        prompt_file=prompt_file,
        state_dir=state_dir,
        overwrite=overwrite,
        limit=limit,
        dry_run=dry_run,
        temperature=temp,
        top_p=top_p,
        max_output_tokens=tokens,
        seed=seed,
        max_image_side=max_image_side,
        image_prep_enabled=image_prep,
        image_format=image_format,
        image_quality=image_quality,
        from_index=from_index,
    )
    typer.echo(
        f"done total={stats.total} ok={stats.ok} fail={stats.failed} skip={stats.done_skip}",
        err=True,
    )


@app.command("retry-failed")
def retry_failed_cmd(
    provider: str = typer.Option(..., "--provider"),
    model: str = typer.Option(..., "--model"),
    input_dir: Path = typer.Option(..., "--input-dir"),
    errors: Path = typer.Option(..., "--errors", help="errors.jsonl path"),
    workers: int = typer.Option(2, "--workers"),
    prompt_file: Optional[Path] = typer.Option(None, "--prompt-file"),
    state_dir: Optional[Path] = typer.Option(None, "--state-dir"),
    temperature: Optional[float] = typer.Option(None, "--temperature"),
    no_temperature: bool = typer.Option(False, "--no-temperature"),
    top_p: Optional[float] = typer.Option(None, "--top-p"),
    max_output_tokens: Optional[int] = typer.Option(1024, "--max-output-tokens"),
    no_max_output_tokens: bool = typer.Option(False, "--no-max-output-tokens"),
    seed: Optional[int] = typer.Option(None, "--seed"),
    max_image_side: int = typer.Option(DEFAULT_MAX_IMAGE_SIDE, "--max-image-side"),
    image_prep: bool = typer.Option(DEFAULT_IMAGE_PREP_ENABLED, "--image-prep/--no-image-prep"),
    image_format: str = typer.Option(DEFAULT_IMAGE_FORMAT, "--image-format"),
    image_quality: int = typer.Option(DEFAULT_IMAGE_QUALITY, "--image-quality"),
) -> None:
    """Retry images listed in errors.jsonl."""
    if provider not in ("gemini", "openrouter"):
        raise typer.Exit(1)
    if image_format not in ("jpeg", "webp", "png"):
        typer.secho("image-format must be jpeg|webp|png", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    temp, tokens = _temp_tokens(
        temperature, no_temperature, max_output_tokens, no_max_output_tokens
    )
    paths: list[Path] = []
    for line in errors.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        p = Path(row["image"])
        if p.exists() and not is_done(p):
            paths.append(p)
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in paths:
        s = str(p)
        if s not in seen:
            seen.add(s)
            uniq.append(p)

    prompt_text = (
        prompt_file.read_text(encoding="utf-8").strip() if prompt_file else DEFAULT_PROMPT
    )
    state = RunState(state_dir or (input_dir / ".caption_state"))
    provider_obj = get_provider(provider)
    ok = fail = 0

    def work(image: Path) -> bool:
        try:
            text = provider_obj.caption(
                CaptionRequest(
                    image_path=image,
                    prompt=prompt_text,
                    model=model,
                    temperature=temp,
                    top_p=top_p,
                    max_output_tokens=tokens,
                    seed=seed,
                    max_image_side=max_image_side,
                    image_prep_enabled=image_prep,
                    image_format=image_format,  # type: ignore[arg-type]
                    image_quality=image_quality,
                )
            )
            _atomic_write_text(caption_path_for(image), text)
            return True
        except Exception as e:
            state.log_error(image, str(e))
            return False

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(work, p) for p in uniq]
        for fut in tqdm(as_completed(futs), total=len(futs), desc="retry"):
            if fut.result():
                ok += 1
            else:
                fail += 1
    typer.echo(json.dumps({"retry_ok": ok, "retry_failed": fail, "queued": len(uniq)}, indent=2))


@app.command("build-index")
def build_index_cmd(
    input_dir: Path = typer.Option(..., "--input-dir"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive"),
    state_dir: Optional[Path] = typer.Option(None, "--state-dir"),
) -> None:
    """Write DIR/.caption_state/image_index.txt for large folders."""
    build_image_index(input_dir, recursive=recursive, state_dir=state_dir)


@app.command("list-models")
def list_models_cmd(
    provider: str = typer.Option(..., "--provider"),
    all_models: bool = typer.Option(False, "--all", help="Include non-vision models"),
    as_json: bool = typer.Option(False, "--json"),
    contains: Optional[str] = typer.Option(None, "--contains"),
) -> None:
    """List models (prices when the API provides them)."""
    vision_only = not all_models
    if provider == "openrouter":
        models = list_openrouter(vision_only=vision_only)
    elif provider == "gemini":
        models = list_gemini(vision_only=vision_only)
    else:
        typer.secho("provider must be gemini or openrouter", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if contains:
        q = contains.lower()
        models = [m for m in models if q in m.id.lower() or q in (m.name or "").lower()]
    typer.echo(to_json(models) if as_json else format_table(models))


@app.command("selfcheck")
def selfcheck_cmd() -> None:
    """Offline selfcheck: import package + dry-run runner."""
    import runpy

    script = Path(__file__).resolve().parents[3] / "scripts" / "selfcheck.py"
    if script.is_file():
        ns = runpy.run_path(str(script))
        raise typer.Exit(int(ns["main"]()))
    typer.echo("scripts/selfcheck.py missing", err=True)
    raise typer.Exit(1)


@app.command("serve")
def serve_cmd() -> None:
    """Start local WebUI server (same as start.bat)."""
    from caption_batch.run_server import main as run_main

    run_main()


def main() -> None:
    app()


if __name__ == "__main__":
    main()

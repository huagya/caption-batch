from __future__ import annotations

import argparse
from pathlib import Path

from .image_prep import DEFAULT_MAX_IMAGE_SIDE
from .list_models import format_table, list_gemini, list_openrouter, to_json


def _add_gen_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature (omit via --no-temperature)")
    p.add_argument(
        "--no-temperature",
        action="store_true",
        help="Do not send temperature to the provider",
    )
    p.add_argument(
        "--max-output-tokens",
        type=int,
        default=1024,
        help="Max caption tokens (omit via --no-max-output-tokens)",
    )
    p.add_argument(
        "--no-max-output-tokens",
        action="store_true",
        help="Do not send max output tokens to the provider",
    )
    p.add_argument(
        "--max-image-side",
        type=int,
        default=DEFAULT_MAX_IMAGE_SIDE,
        help="Resize longest side to this before upload (default 1536)",
    )


def _resolve_temp_tokens(args) -> tuple[float | None, int | None]:
    temp: float | None = None if getattr(args, "no_temperature", False) else args.temperature
    tokens: int | None = (
        None if getattr(args, "no_max_output_tokens", False) else args.max_output_tokens
    )
    return temp, tokens


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="caption-batch",
        description="Batch image captioning for large datasets (Gemini / OpenRouter).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Caption images in a folder")
    run.add_argument("--provider", required=True, choices=["gemini", "openrouter"])
    run.add_argument("--model", required=True, help="Model id")
    run.add_argument("--input-dir", required=True, type=Path)
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("--recursive", action="store_true", default=True)
    run.add_argument("--no-recursive", action="store_true")
    run.add_argument("--prompt", type=str, default=None)
    run.add_argument("--prompt-file", type=Path, default=None)
    run.add_argument("--state-dir", type=Path, default=None)
    run.add_argument("--overwrite", action="store_true")
    run.add_argument("--limit", type=int, default=None)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument(
        "--from-index",
        action="store_true",
        help="Read image list from DIR/.caption_state/image_index.txt (build if missing)",
    )
    _add_gen_args(run)

    retry = sub.add_parser("retry-failed", help="Retry images listed in errors.jsonl")
    retry.add_argument("--provider", required=True, choices=["gemini", "openrouter"])
    retry.add_argument("--model", required=True)
    retry.add_argument("--input-dir", required=True, type=Path)
    retry.add_argument("--errors", type=Path, required=True)
    retry.add_argument("--workers", type=int, default=2)
    retry.add_argument("--prompt-file", type=Path, default=None)
    retry.add_argument("--state-dir", type=Path, default=None)
    _add_gen_args(retry)

    idx = sub.add_parser(
        "build-index",
        help="Write DIR/.caption_state/image_index.txt (one path/line) for million-scale runs",
    )
    idx.add_argument("--input-dir", required=True, type=Path)
    idx.add_argument("--recursive", action="store_true", default=True)
    idx.add_argument("--no-recursive", action="store_true")
    idx.add_argument("--state-dir", type=Path, default=None)

    ls_ = sub.add_parser("list-models", help="List models (prices when API provides them)")
    ls_.add_argument("--provider", required=True, choices=["gemini", "openrouter"])
    ls_.add_argument("--all", action="store_true", help="Include non-vision models")
    ls_.add_argument("--json", action="store_true")
    ls_.add_argument("--contains", type=str, default=None)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "list-models":
        vision_only = not args.all
        if args.provider == "openrouter":
            models = list_openrouter(vision_only=vision_only)
        else:
            models = list_gemini(vision_only=vision_only)
        if args.contains:
            q = args.contains.lower()
            models = [m for m in models if q in m.id.lower() or q in (m.name or "").lower()]
        print(to_json(models) if args.json else format_table(models))
        return

    if args.cmd == "build-index":
        from .discover import build_image_index

        recursive = not args.no_recursive
        build_image_index(
            args.input_dir,
            recursive=recursive,
            state_dir=args.state_dir,
        )
        return

    if args.cmd == "run":
        from .runner import run_batch

        recursive = not args.no_recursive
        temp, tokens = _resolve_temp_tokens(args)
        run_batch(
            provider_name=args.provider,
            model=args.model,
            input_dir=args.input_dir,
            workers=args.workers,
            recursive=recursive,
            prompt=args.prompt,
            prompt_file=args.prompt_file,
            state_dir=args.state_dir,
            overwrite=args.overwrite,
            limit=args.limit,
            dry_run=args.dry_run,
            temperature=temp,
            max_output_tokens=tokens,
            max_image_side=args.max_image_side,
            from_index=args.from_index,
        )
        return

    if args.cmd == "retry-failed":
        import json
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from tqdm import tqdm

        from .discover import caption_path_for, is_done
        from .prompts import DEFAULT_PROMPT
        from .providers import get_provider
        from .providers.base import CaptionRequest
        from .runner import RunState, _atomic_write_text

        paths: list[Path] = []
        for line in args.errors.read_text(encoding="utf-8").splitlines():
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
            args.prompt_file.read_text(encoding="utf-8").strip()
            if args.prompt_file
            else DEFAULT_PROMPT
        )
        state = RunState(args.state_dir or (args.input_dir / ".caption_state"))
        provider = get_provider(args.provider)
        temp, tokens = _resolve_temp_tokens(args)
        ok = fail = 0

        def work(image: Path):
            try:
                text = provider.caption(
                    CaptionRequest(
                        image_path=image,
                        prompt=prompt_text,
                        model=args.model,
                        temperature=temp,
                        max_output_tokens=tokens,
                        max_image_side=args.max_image_side,
                    )
                )
                _atomic_write_text(caption_path_for(image), text)
                return True
            except Exception as e:
                state.log_error(image, str(e))
                return False

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futs = [ex.submit(work, p) for p in uniq]
            for fut in tqdm(as_completed(futs), total=len(futs), desc="retry"):
                if fut.result():
                    ok += 1
                else:
                    fail += 1
        print(json.dumps({"retry_ok": ok, "retry_failed": fail, "queued": len(uniq)}, indent=2))


if __name__ == "__main__":
    main()

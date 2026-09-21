from pathlib import Path
from caption_batch.core.runner import run_batch


def test_dry_run(tmp_path: Path) -> None:
    img = tmp_path / "x.png"
    img.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
            "0000000c49444154789c63f80f00000101000518d84e0000000049454e44ae426082"
        )
    )
    stats = run_batch(
        provider_name="gemini",
        model="dry",
        input_dir=tmp_path,
        dry_run=True,
        workers=1,
    )
    assert stats.total == 1
    assert stats.todo == 1

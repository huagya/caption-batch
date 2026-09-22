"""Progress callback increments + job snapshot write/read."""
from __future__ import annotations

import time
from pathlib import Path

from caption_batch.core.job_snapshot import read_job_snapshot, write_job_snapshot
from caption_batch.core.runner import RunStats, run_batch


PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c49444154789c63f80f00000101000518d84e0000000049454e44ae426082"
)


def test_progress_callback_increments(tmp_path: Path) -> None:
    for name in ("a.png", "b.png", "c.png"):
        (tmp_path / name).write_bytes(PNG)
    events: list[dict] = []

    def on_progress(payload: dict) -> None:
        events.append(payload)

    stats = run_batch(
        provider_name="gemini",
        model="dry",
        input_dir=tmp_path,
        dry_run=True,
        workers=1,
        on_progress=on_progress,
    )
    assert stats.total == 3
    assert stats.todo == 3
    assert len(events) >= 1
    last = events[-1]
    assert "stats" in last
    assert last["stats"]["total"] == 3
    assert "started_at" in last
    assert "rate_per_sec" in last
    assert "eta_sec" in last
    assert "recent_done" in last
    assert "recent_errors" in last


def test_job_snapshot_write_read(tmp_path: Path) -> None:
    write_job_snapshot(
        tmp_path,
        status="finished",
        params={"provider": "gemini", "model": "x", "folder": str(tmp_path), "overwrite": False},
        stats={"total": 10, "ok": 8, "failed": 1, "done_skip": 1, "todo": 9},
        started_at=100.0,
        finished_at=110.0,
        error=None,
        kind="batch",
    )
    data = read_job_snapshot(tmp_path)
    assert data is not None
    assert data["schema"] == 1
    assert data["status"] == "finished"
    assert data["params"]["model"] == "x"
    assert "GEMINI_API_KEY" not in data["params"]
    assert data["stats"]["ok"] == 8
    assert data["version"]


def test_snapshot_strips_secrets(tmp_path: Path) -> None:
    write_job_snapshot(
        tmp_path,
        status="running",
        params={"model": "m", "gemini_api_key": "SECRET", "api_key": "SECRET2"},
        stats={},
        started_at=time.time(),
    )
    data = read_job_snapshot(tmp_path)
    assert data is not None
    assert "gemini_api_key" not in data["params"]
    assert "api_key" not in data["params"]
    assert data["params"]["model"] == "m"


def test_run_batch_writes_snapshot(tmp_path: Path) -> None:
    (tmp_path / "z.png").write_bytes(PNG)
    run_batch(
        provider_name="gemini",
        model="dry",
        input_dir=tmp_path,
        dry_run=True,
        workers=1,
        snapshot_params={"provider": "gemini", "model": "dry", "folder": str(tmp_path)},
    )
    snap = read_job_snapshot(tmp_path)
    assert snap is not None
    assert snap["status"] in ("finished", "stopped", "running")
    assert snap["params"]["model"] == "dry"

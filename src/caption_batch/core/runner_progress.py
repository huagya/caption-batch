from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class RunStats:
    total: int = 0
    todo: int = 0
    done_skip: int = 0
    ok: int = 0
    failed: int = 0


@dataclass
class ImageResult:
    image: str
    caption: str | None = None
    error: str | None = None
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "image": self.image,
            "caption": self.caption,
            "error": self.error,
            "skipped": self.skipped,
        }


class RunState:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.errors_path = self.state_dir / "errors.jsonl"
        self.summary_path = self.state_dir / "last_run_summary.json"
        self._lock = threading.Lock()

    def log_error(self, image: Path, error: str) -> None:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "image": str(image),
            "error": error,
        }
        with self._lock:
            with self.errors_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def write_summary(self, payload: dict) -> None:
        self.summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def stats_dict(stats: RunStats) -> dict[str, Any]:
    return {
        "total": stats.total,
        "todo": stats.todo,
        "done_skip": stats.done_skip,
        "ok": stats.ok,
        "failed": stats.failed,
        "skip": stats.done_skip,
        "fail": stats.failed,
    }


class ProgressTracker:
    """Lock-friendly progress state for on_progress callbacks."""

    def __init__(self, stats: RunStats, started_at: float) -> None:
        self.stats = stats
        self.started_at = started_at
        self.current_image: str | None = None
        self.recent_done: list[dict[str, Any]] = []
        self.recent_errors: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._in_flight: set[str] = set()

    def set_current(self, image: Path | None) -> None:
        with self._lock:
            if image is None:
                return
            s = str(image)
            self._in_flight.add(s)
            self.current_image = s

    def clear_current(self, image: Path) -> None:
        with self._lock:
            s = str(image)
            self._in_flight.discard(s)
            if self.current_image == s:
                self.current_image = next(iter(self._in_flight), None)

    def record_done(self, image: Path, ok: bool, error: str = "") -> None:
        with self._lock:
            row = {"image": str(image), "ok": ok, "error": error or None}
            self.recent_done.append(row)
            if len(self.recent_done) > 20:
                self.recent_done = self.recent_done[-20:]
            if not ok:
                err_row = {
                    "image": str(image),
                    "error": error or "unknown",
                    "ts": time.time(),
                }
                self.recent_errors.append(err_row)
                if len(self.recent_errors) > 50:
                    self.recent_errors = self.recent_errors[-50:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            completed = self.stats.ok + self.stats.failed
            elapsed = max(0.0, time.time() - self.started_at)
            rate: float | None = None
            eta: float | None = None
            if completed > 0 and elapsed > 0:
                rate = completed / elapsed
                remaining = max(0, self.stats.todo - completed)
                if rate > 0:
                    eta = remaining / rate
            return {
                "stats": stats_dict(self.stats),
                "current_image": self.current_image,
                "recent_done": list(self.recent_done),
                "recent_errors": list(self.recent_errors),
                "started_at": self.started_at,
                "rate_per_sec": rate,
                "eta_sec": eta,
                "total": self.stats.total,
                "todo": self.stats.todo,
                "ok": self.stats.ok,
                "fail": self.stats.failed,
                "skip": self.stats.done_skip,
            }

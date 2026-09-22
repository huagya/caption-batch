"""In-process job tracker for the WebUI / API."""

from __future__ import annotations

import threading
from typing import Any

from caption_batch.core.runner import RunStats


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
        self.kind: str = "batch"  # "batch" | "preview"
        self.results: list[dict[str, Any]] = []
        self.current_image: str | None = None
        self.recent_done: list[dict[str, Any]] = []
        self.recent_errors: list[dict[str, Any]] = []
        self.rate_per_sec: float | None = None
        self.eta_sec: float | None = None
        self._folder: str | None = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self.running,
                "stopped": self.stopped,
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "params": dict(self.params),
                "kind": self.kind,
                "total": self.stats.total,
                "todo": self.stats.todo,
                "ok": self.stats.ok,
                "fail": self.stats.failed,
                "skip": self.stats.done_skip,
                "current_image": self.current_image,
                "recent_done": list(self.recent_done),
                "recent_errors": list(self.recent_errors),
                "rate_per_sec": self.rate_per_sec,
                "eta_sec": self.eta_sec,
                "results": list(self.results),
            }

    def apply_stats(self, stats: RunStats) -> None:
        with self._lock:
            self.stats = stats

    def apply_progress(self, payload: dict[str, Any]) -> None:
        with self._lock:
            st = payload.get("stats") or {}
            if st:
                self.stats = RunStats(
                    total=int(st.get("total", self.stats.total)),
                    todo=int(st.get("todo", self.stats.todo)),
                    done_skip=int(st.get("done_skip", st.get("skip", self.stats.done_skip))),
                    ok=int(st.get("ok", self.stats.ok)),
                    failed=int(st.get("failed", st.get("fail", self.stats.failed))),
                )
            if "current_image" in payload:
                self.current_image = payload.get("current_image")
            if "recent_done" in payload:
                self.recent_done = list(payload.get("recent_done") or [])
            if "recent_errors" in payload:
                self.recent_errors = list(payload.get("recent_errors") or [])
            if "rate_per_sec" in payload:
                self.rate_per_sec = payload.get("rate_per_sec")
            if "eta_sec" in payload:
                self.eta_sec = payload.get("eta_sec")
            if payload.get("started_at") is not None and self.started_at is None:
                self.started_at = payload.get("started_at")


JOB = JobState()

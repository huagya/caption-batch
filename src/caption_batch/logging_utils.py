"""Ring-buffer + optional file logging shared by API / CLI / server."""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, TextIO


DEFAULT_CAPACITY = 200
PACKAGE_LOGGER = "caption_batch"
LOGS_DIR_NAME = "logs"

_handler: Optional[RingBufferHandler] = None
_configured = False
_file_logging_setup = False
_session_log_path: Optional[Path] = None
_logs_dir: Optional[Path] = None
_dual_handler: Optional["DualFileHandler"] = None


class RingBufferHandler(logging.Handler):
    """Keeps the last N structured log records in memory."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        super().__init__()
        self.capacity = capacity
        self._buffer: Deque[Dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("path", "error", "total", "changed", "failed", "unchanged"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        with self._lock:
            self._buffer.append(entry)

    def get_logs(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._buffer)
        if limit is not None and limit >= 0:
            return items[-limit:]
        return items

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


class DualFileHandler(logging.Handler):
    """One handler that mirrors every record to session-*.log and latest.log.

    Keeps both files in sync for the whole process. Flushes on every emit so a
    diagnostics zip mid-session sees the same lines. latest.log is truncated
    only when fresh_latest=True (server/session start); collect must pass False.

    uvicorn's logging.config.dictConfig calls logging.shutdown which closes all
    handlers; is_open/_reopen/emit recover from that so file logging survives.
    """

    def __init__(
        self,
        session_path: Path,
        latest_path: Path,
        *,
        fresh_latest: bool = True,
        encoding: str = "utf-8",
    ) -> None:
        super().__init__()
        self.session_path = Path(session_path)
        self.latest_path = Path(latest_path)
        self._encoding = encoding
        self._lock_io = threading.Lock()
        self._session: TextIO = open(self.session_path, "a", encoding=encoding)
        latest_mode = "w" if fresh_latest else "a"
        self._latest: TextIO = open(self.latest_path, latest_mode, encoding=encoding)

    def is_open(self) -> bool:
        """True if both streams are usable (not closed by logging.shutdown)."""
        try:
            return (
                not self._session.closed
                and not self._latest.closed
                and self._session.writable()
                and self._latest.writable()
            )
        except Exception:
            return False

    def _reopen(self) -> None:
        """Re-open both files in append mode (repair after dictConfig shutdown).

        Caller must hold _lock_io. Does not truncate latest.log.
        """
        try:
            if not self._session.closed:
                self._session.close()
        except Exception:
            pass
        try:
            if not self._latest.closed:
                self._latest.close()
        except Exception:
            pass
        self._session = open(self.session_path, "a", encoding=self._encoding)
        self._latest = open(self.latest_path, "a", encoding=self._encoding)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            line = msg + "\n"
            with self._lock_io:
                if not self.is_open():
                    self._reopen()
                self._session.write(line)
                self._latest.write(line)
                self._session.flush()
                self._latest.flush()
        except Exception:
            self.handleError(record)

    def flush(self) -> None:
        with self._lock_io:
            try:
                if not self.is_open():
                    self._reopen()
                self._session.flush()
                self._latest.flush()
            except Exception:
                pass

    def close(self) -> None:
        with self._lock_io:
            try:
                self._session.close()
            except Exception:
                pass
            try:
                self._latest.close()
            except Exception:
                pass
        super().close()


def get_ring_handler() -> RingBufferHandler:
    global _handler
    if _handler is None:
        _handler = RingBufferHandler()
    return _handler


def configure_logging(level: int = logging.INFO) -> None:
    """Attach ring buffer (+ stderr) once for the caption_batch package."""
    global _configured
    if _configured:
        return
    root = logging.getLogger(PACKAGE_LOGGER)
    root.setLevel(level)
    ring = get_ring_handler()
    ring.setLevel(level)
    if ring not in root.handlers:
        root.addHandler(ring)
    if not any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, RingBufferHandler)
        and not isinstance(h, logging.FileHandler)
        and not isinstance(h, DualFileHandler)
        for h in root.handlers
    ):
        stream = logging.StreamHandler()
        stream.setLevel(level)
        stream.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root.addHandler(stream)
    _configured = True


SESSION_KEEP_LAST = 10


def prune_old_session_logs(logs_dir: Path | str | None = None, *, keep_last: int = SESSION_KEEP_LAST) -> list[Path]:
    """Delete session-*.log older than keep_last (newest kept). latest.log untouched.

    Returns list of deleted paths. Safe if dir missing.
    """
    path = Path(logs_dir) if logs_dir is not None else _logs_dir
    if path is None:
        return []
    path = Path(path)
    if not path.is_dir():
        return []
    sessions = sorted(
        (p for p in path.glob("session-*.log") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    deleted: list[Path] = []
    for old in sessions[keep_last:]:
        try:
            old.unlink()
            deleted.append(old)
        except OSError:
            pass
    return deleted


def _find_dual_handler(root: logging.Logger) -> Optional[DualFileHandler]:
    for h in root.handlers:
        if isinstance(h, DualFileHandler):
            return h
    return None


def _handler_needs_repair(handler: Optional[DualFileHandler]) -> bool:
    if handler is None:
        return True
    return not handler.is_open()


def setup_file_logging(
    logs_dir: Path | str | None = None,
    *,
    level: int = logging.INFO,
    fresh_latest: bool = True,
    force: bool = False,
) -> Path:
    """Create logs/, attach DualFileHandler (session + latest) for this process.

    Safe to call multiple times. If already set up but the DualFileHandler is
    missing or closed (e.g. after uvicorn dictConfig → logging.shutdown),
    removes the dead handler and recreates (repair path). Pass force=True to
    always recreate.

    fresh_latest=True (default): truncate logs/latest.log at *new* session start.
    On repair, latest is always opened in append mode so prior lines are kept.
    fresh_latest=False: append to latest.log (use from collect so a running
    server's latest.log is not wiped).
    """
    global _file_logging_setup, _session_log_path, _logs_dir, _dual_handler
    configure_logging(level=level)
    root = logging.getLogger(PACKAGE_LOGGER)

    existing = _dual_handler if _dual_handler is not None else _find_dual_handler(root)
    if (
        _file_logging_setup
        and _session_log_path is not None
        and not force
        and not _handler_needs_repair(existing)
    ):
        return _session_log_path

    # Repair path: dead/closed/missing handler after dictConfig shutdown
    repairing = (
        _file_logging_setup
        and _session_log_path is not None
        and not force
        and _handler_needs_repair(existing)
    )

    if logs_dir is None:
        if _logs_dir is not None:
            logs_path = _logs_dir
        else:
            here = Path(__file__).resolve()
            project_root = None
            for candidate in (here.parent, *here.parents):
                if (candidate / "pyproject.toml").is_file():
                    project_root = candidate
                    break
            logs_path = (project_root or here.parents[2]) / LOGS_DIR_NAME
    else:
        logs_path = Path(logs_dir)

    logs_path.mkdir(parents=True, exist_ok=True)

    # Remove dead DualFileHandler(s) from the logger
    for h in list(root.handlers):
        if isinstance(h, DualFileHandler):
            try:
                root.removeHandler(h)
            except Exception:
                pass
            try:
                h.close()
            except Exception:
                pass
    _dual_handler = None

    if repairing and _session_log_path is not None:
        session_path = _session_log_path
        # Repair: never truncate latest
        use_fresh = False
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        session_path = logs_path / f"session-{stamp}.log"
        use_fresh = fresh_latest

    latest_path = logs_path / "latest.log"

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    dual = DualFileHandler(session_path, latest_path, fresh_latest=use_fresh)
    dual.setLevel(level)
    dual.setFormatter(fmt)
    root.addHandler(dual)

    _dual_handler = dual
    _file_logging_setup = True
    _session_log_path = session_path
    _logs_dir = logs_path
    if repairing:
        root.info(
            "file logging repaired session=%s latest=%s",
            session_path.name,
            latest_path.name,
        )
    else:
        root.info(
            "file logging started session=%s latest=%s",
            session_path.name,
            latest_path.name,
        )
    prune_old_session_logs(logs_path, keep_last=SESSION_KEEP_LAST)
    return session_path


def flush_logging() -> None:
    root = logging.getLogger(PACKAGE_LOGGER)
    for h in list(root.handlers):
        try:
            h.flush()
        except Exception:
            pass


def file_logging_active() -> bool:
    return _file_logging_setup


def get_logs_dir() -> Optional[Path]:
    return _logs_dir


def get_session_log_path() -> Optional[Path]:
    return _session_log_path


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


def get_recent_logs(limit: int = 100) -> List[Dict[str, Any]]:
    configure_logging()
    return get_ring_handler().get_logs(limit=limit)


def reset_logging_state_for_tests() -> None:
    """Test helper: clear module flags/handlers."""
    global _configured, _file_logging_setup, _session_log_path, _logs_dir, _handler, _dual_handler
    root = logging.getLogger(PACKAGE_LOGGER)
    for h in list(root.handlers):
        try:
            h.close()
        except Exception:
            pass
        root.removeHandler(h)
    _configured = False
    _file_logging_setup = False
    _session_log_path = None
    _logs_dir = None
    _handler = None
    _dual_handler = None

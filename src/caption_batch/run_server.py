"""Start the FastAPI app with host/port from port.json and free-port fallback."""

from __future__ import annotations

import json
import socket
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn

from caption_batch.logging_utils import configure_logging, get_logger

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8771
MAX_PORT_OFFSET = 50
RUNTIME_PORT_FILE = ".port.runtime"
PORT_CONFIG_NAME = "port.json"


def find_project_root(start: Path | None = None) -> Path:
    """Resolve project root: directory containing pyproject.toml."""
    here = (start or Path(__file__).resolve()).resolve()
    if here.is_file():
        here = here.parent
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return Path(__file__).resolve().parents[2]


def load_dotenv_files(root: Path | None = None) -> None:
    """Load project .env into process env (does not override existing vars)."""
    root = root or find_project_root()
    env_path = root / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    except Exception:
        # Minimal fallback parser
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in __import__("os").environ:
                __import__("os").environ[k] = v


def load_port_config(root: Path | None = None) -> tuple[str, int]:
    """Load host/port from port.json at project root. Defaults if missing/invalid."""
    root = root or find_project_root()
    config_path = root / PORT_CONFIG_NAME
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    if not config_path.is_file():
        alt = root / "config" / PORT_CONFIG_NAME
        if alt.is_file():
            config_path = alt
        else:
            return host, port
    try:
        data: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return host, port
    raw_host = data.get("host", host)
    raw_port = data.get("port", port)
    if isinstance(raw_host, str) and raw_host.strip():
        host = raw_host.strip()
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    if not (1 <= port <= 65535):
        port = DEFAULT_PORT
    return host, port


def is_port_free(host: str, port: int) -> bool:
    """Return True if a TCP bind on (host, port) would succeed."""
    family = socket.AF_INET6 if ":" in host and not host.startswith(":") else socket.AF_INET
    bind_host = host
    if host in ("localhost",):
        bind_host = "127.0.0.1"
        family = socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((bind_host, port))
            return True
    except OSError:
        return False


def find_free_port(host: str, preferred: int, max_offset: int = MAX_PORT_OFFSET) -> int:
    """Return preferred port if free, else scan upward up to max_offset inclusive."""
    for offset in range(0, max_offset + 1):
        candidate = preferred + offset
        if candidate > 65535:
            break
        if is_port_free(host, candidate):
            return candidate
    raise RuntimeError(
        f"No free TCP port found in range {preferred}..{min(preferred + max_offset, 65535)} "
        f"on host {host!r}"
    )


def write_runtime_port(root: Path, port: int) -> None:
    """Optionally write chosen port to .port.runtime for debugging."""
    try:
        (root / RUNTIME_PORT_FILE).write_text(f"{port}\n", encoding="utf-8")
    except OSError:
        pass


def _open_browser_later(url: str, delay_sec: float = 1.5) -> None:
    def _open() -> None:
        time.sleep(delay_sec)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    thread = threading.Thread(target=_open, name="open-browser", daemon=True)
    thread.start()


def main() -> None:
    root = find_project_root()
    load_dotenv_files(root)
    # Only stderr/ring before uvicorn: dictConfig closes file handlers.
    # DualFileHandler is created in FastAPI startup after uvicorn configures logging.
    configure_logging()
    log = get_logger(__name__)
    log.info("run_server starting root=%s", root)
    host, preferred = load_port_config(root)
    port = find_free_port(host, preferred)
    if port != preferred:
        print(f"[port] {preferred} is in use; using free port {port} instead.", flush=True)
    write_runtime_port(root, port)

    url = f"http://{host}:{port}/"
    print(f"URL: {url}", flush=True)
    print(f"PORT={port}", flush=True)
    print("Keep this window open. Stop with Ctrl+C.", flush=True)
    print(flush=True)

    _open_browser_later(url)

    uvicorn.run(
        "caption_batch.api.app:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()

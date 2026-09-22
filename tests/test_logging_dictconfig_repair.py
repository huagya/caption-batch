"""Simulate uvicorn dictConfig closing DualFileHandler; assert repair restores file logs."""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path

from caption_batch.logging_utils import (
    DualFileHandler,
    get_logger,
    reset_logging_state_for_tests,
    setup_file_logging,
)


def test_dictconfig_closes_handler_then_repair_writes(tmp_path: Path) -> None:
    reset_logging_state_for_tests()
    logs_dir = tmp_path / "logs"
    setup_file_logging(logs_dir, fresh_latest=True)
    log = get_logger("caption_batch.test_repair")
    log.info("before-dictconfig marker")

    latest = logs_dir / "latest.log"
    assert latest.is_file()
    assert "before-dictconfig marker" in latest.read_text(encoding="utf-8")

    # Mimic uvicorn: dictConfig → _clearExistingHandlers → logging.shutdown closes all
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "level": "INFO",
                }
            },
            "root": {"level": "INFO", "handlers": ["default"]},
        }
    )

    # Dead closed DualFileHandler should still be attached (or closed)
    root = logging.getLogger("caption_batch")
    duals = [h for h in root.handlers if isinstance(h, DualFileHandler)]
    assert duals, "expected DualFileHandler still attached after dictConfig"
    assert not duals[0].is_open(), "handler streams should be closed by shutdown"

    # Repair path
    setup_file_logging(logs_dir, fresh_latest=True)
    marker = "after-repair-dictconfig-line"
    log.info(marker)

    text = latest.read_text(encoding="utf-8")
    assert marker in text, f"expected repaired log line in latest.log, got:\n{text}"
    assert "file logging repaired" in text or "file logging started" in text

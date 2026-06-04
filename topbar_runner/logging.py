"""File logging helpers for topbar-runner diagnostics."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOGGER_NAME = "topbar_runner"


def configure_file_logging(
    log_path: Path,
    *,
    debug: bool = False,
    stderr: bool = False,
) -> logging.Logger:
    """Configure a plain log file for host diagnostics."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(formatter)
    handler.setLevel(level)
    logger.addHandler(handler)

    if stderr:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        stream.setLevel(level)
        stream._topbar_stderr = True  # type: ignore[attr-defined]
        logger.addHandler(stream)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)

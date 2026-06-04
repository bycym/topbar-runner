import logging
from pathlib import Path

from topbar_runner.logging import configure_file_logging


def test_configure_file_logging(tmp_path: Path) -> None:
    log_path = tmp_path / "topbar-runner.log"
    logger = configure_file_logging(log_path)

    logger.info("hello")
    for handler in logger.handlers:
        handler.flush()

    assert log_path.read_text(encoding="utf-8").endswith("INFO topbar_runner: hello\n")
    logger.handlers.clear()
    logging.shutdown()

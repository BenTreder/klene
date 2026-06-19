from __future__ import annotations

import logging
import tempfile
from pathlib import Path


LOGGER_NAME = "klene"


def configure_logging() -> Path:
    candidates = [
        Path.home() / ".local" / "state" / "klene",
        Path(tempfile.gettempdir()) / "klene",
    ]
    log_dir: Path | None = None
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        log_dir = candidate
        break
    if log_dir is None:
        raise OSError("Unable to create a writable log directory for Klene.")
    log_path = log_dir / "klene.log"

    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(log_path)
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return log_path


def get_logger() -> logging.Logger:
    configure_logging()
    return logging.getLogger(LOGGER_NAME)

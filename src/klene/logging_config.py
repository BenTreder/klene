from __future__ import annotations

import logging
import tempfile
from pathlib import Path


LOGGER_NAME = "klene"


def configure_logging() -> Path:
    candidate_dirs = [
        Path.home() / ".local" / "state" / "klene",
        Path(tempfile.gettempdir()) / "klene",
    ]
    candidate_paths: list[Path] = []
    for candidate in candidate_dirs:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        candidate_paths.append(candidate / "klene.log")
    if not candidate_paths:
        raise OSError("Unable to create a writable log directory for Klene.")

    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        for candidate_path in candidate_paths:
            try:
                handler = logging.FileHandler(candidate_path)
            except OSError:
                continue
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            return candidate_path
        raise OSError("Unable to open a writable Klene log file.")

    handler = logger.handlers[0]
    if isinstance(handler, logging.FileHandler):
        return Path(handler.baseFilename)
    return candidate_paths[-1]


def get_logger() -> logging.Logger:
    configure_logging()
    return logging.getLogger(LOGGER_NAME)

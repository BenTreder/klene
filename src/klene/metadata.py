from __future__ import annotations

from importlib.resources import files
from pathlib import Path


APP_NAME = "Klene"
APP_SLUG = "klene"
APP_VERSION = "0.1.0"
APP_TAGLINE = "Safe cleanup for Arch Linux"
APP_SUMMARY = (
    "Klene helps you find safe cleanup opportunities on Arch Linux with a modern GUI and CLI."
)
APP_DESCRIPTION = "Scan first, review what is safe to remove, then clean only what you choose."
AUTHOR_NAME = "Ben Treder"
AUTHOR_WEBSITE = "BenTreder.com"
AUTHOR_CREDIT = f"Made by {AUTHOR_NAME} • {AUTHOR_WEBSITE}"
GITHUB_REPO_URL = "https://github.com/bdtreder/klene"


def packaged_logo_path() -> Path:
    return Path(str(files("klene").joinpath("assets/klene_logo.png")))

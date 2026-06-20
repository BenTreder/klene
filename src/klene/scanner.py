from __future__ import annotations

from pathlib import Path

from klene.models import ScanReport
from klene.platforms import get_provider
from klene.platforms.arch import AUR_CACHE_DIRS, PACMAN_CACHE_DIR
from klene.platforms.base import (
    LINUX_LOW_RISK_USER_CACHE_DIRS as LOW_RISK_USER_CACHE_DIRS,
    LINUX_THUMBNAILS_DIR as THUMBNAILS_DIR,
    LINUX_TRASH_FILES_DIR as TRASH_FILES_DIR,
    LINUX_TRASH_INFO_DIR as TRASH_INFO_DIR,
    LINUX_USER_CACHE_DIR as USER_CACHE_DIR,
)
from klene.utils import now_iso


def scan_system() -> ScanReport:
    provider = get_provider()
    platform_info = provider.get_platform_info()
    targets = provider.scan()
    platform_info.available_cleanup_areas = [target.title for target in targets]
    return ScanReport(
        arch_linux=platform_info.platform_id == "arch",
        generated_at=now_iso(),
        targets=targets,
        platform=platform_info,
        notes=list(platform_info.safety_notes),
    )


__all__ = [
    "AUR_CACHE_DIRS",
    "LOW_RISK_USER_CACHE_DIRS",
    "PACMAN_CACHE_DIR",
    "THUMBNAILS_DIR",
    "TRASH_FILES_DIR",
    "TRASH_INFO_DIR",
    "USER_CACHE_DIR",
    "scan_system",
]

from __future__ import annotations

import re
from pathlib import Path

from klene.commands import (
    directory_bytes,
    get_flatpak_unused_preview,
    get_journal_disk_usage,
    get_orphan_packages,
)
from klene.models import CleanupStatus, CleanupTarget, ScanReport
from klene.safety import command_exists, is_arch_linux
from klene.utils import now_iso


PACMAN_CACHE_DIR = Path("/var/cache/pacman/pkg")
USER_CACHE_DIR = Path.home() / ".cache"
TRASH_FILES_DIR = Path.home() / ".local" / "share" / "Trash" / "files"
TRASH_INFO_DIR = Path.home() / ".local" / "share" / "Trash" / "info"
THUMBNAILS_DIR = USER_CACHE_DIR / "thumbnails"
LOW_RISK_USER_CACHE_DIRS = [
    THUMBNAILS_DIR,
    USER_CACHE_DIR / "fontconfig",
    USER_CACHE_DIR / "pip",
    USER_CACHE_DIR / "go-build",
    USER_CACHE_DIR / "npm",
    USER_CACHE_DIR / "yarn",
]
AUR_CACHE_DIRS = [
    Path.home() / ".cache" / "yay",
    Path.home() / ".cache" / "paru",
]


def _target(
    key: str,
    title: str,
    description: str,
    status: CleanupStatus,
    **kwargs: object,
) -> CleanupTarget:
    return CleanupTarget(key=key, title=title, description=description, status=status, **kwargs)


def _scan_pacman_cache() -> CleanupTarget:
    size = directory_bytes(PACMAN_CACHE_DIR)
    preview = [str(PACMAN_CACHE_DIR)]
    details = "Uses paccache -r -k <keep> when available."
    if not PACMAN_CACHE_DIR.exists():
        return _target(
            "pacman-cache",
            "Pacman cache",
            "Remove old cached package files while keeping recent versions.",
            CleanupStatus.UNAVAILABLE,
            estimated_bytes=0,
            details="The pacman cache folder was not found on this system.",
            available=False,
            preview=preview,
        )
    if command_exists("paccache"):
        details += " paccache is ready."
    else:
        details += " Install pacman-contrib to use paccache."
    status = CleanupStatus.CLEAN if size == 0 else CleanupStatus.AVAILABLE
    return _target(
        "pacman-cache",
        "Pacman cache",
        "Remove old cached package files while keeping recent versions.",
        status,
        estimated_bytes=size,
        details=details,
        preview=preview,
    )


def _scan_orphans() -> CleanupTarget:
    if not command_exists("pacman"):
        return _target(
            "orphans",
            "Orphan packages",
            "Review packages no longer required by anything else.",
            CleanupStatus.UNAVAILABLE,
            available=False,
            details="pacman is not available, so orphan packages cannot be checked.",
        )
    packages = get_orphan_packages()
    status = CleanupStatus.CLEAN if not packages else CleanupStatus.WARNING
    details = "Extra confirmation is required before package removal."
    return _target(
        "orphans",
        "Orphan packages",
        "Review packages no longer required by anything else.",
        status,
        estimated_bytes=None,
        count=len(packages),
        details=details,
        preview=packages[:25],
    )


def _scan_journal() -> CleanupTarget:
    if not command_exists("journalctl"):
        return _target(
            "journal",
            "System journal",
            "Trim old journal logs to save space.",
            CleanupStatus.UNAVAILABLE,
            available=False,
            details="journalctl is not available on this system.",
        )
    raw = get_journal_disk_usage()
    match = re.search(r"([0-9.]+)\s*([KMGTP]?B)", raw, re.IGNORECASE)
    estimated_bytes = None
    if match:
        value = float(match.group(1))
        unit = match.group(2).upper()
        multipliers = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
        estimated_bytes = int(value * multipliers.get(unit, 1))
    status = CleanupStatus.AVAILABLE if raw else CleanupStatus.UNAVAILABLE
    return _target(
        "journal",
        "System journal",
        "Trim old journal logs to save space.",
        status,
        estimated_bytes=estimated_bytes,
        details=raw or "Journal usage could not be read right now.",
    )


def _scan_user_cache() -> CleanupTarget:
    total = directory_bytes(USER_CACHE_DIR)
    low_risk_total = sum(directory_bytes(path) for path in LOW_RISK_USER_CACHE_DIRS)
    preview = [str(path) for path in LOW_RISK_USER_CACHE_DIRS if path.exists()]
    details = "Reports total ~/.cache usage. Cleanup only targets known low-risk subdirectories."
    status = CleanupStatus.CLEAN if total == 0 else CleanupStatus.AVAILABLE
    return _target(
        "user-cache",
        "User cache",
        "Clean known low-risk cache folders inside your home cache.",
        status,
        estimated_bytes=low_risk_total,
        details=f"{details} Total ~/.cache size: {total} bytes.",
        preview=preview,
    )


def _scan_trash() -> CleanupTarget:
    size = directory_bytes(TRASH_FILES_DIR) + directory_bytes(TRASH_INFO_DIR)
    preview = [str(TRASH_FILES_DIR), str(TRASH_INFO_DIR)]
    status = CleanupStatus.CLEAN if size == 0 else CleanupStatus.AVAILABLE
    return _target(
        "trash",
        "Trash",
        "Empty files currently sitting in the trash.",
        status,
        estimated_bytes=size,
        details="Nothing is removed until you confirm cleanup.",
        preview=preview,
    )


def _scan_thumbnails() -> CleanupTarget:
    size = directory_bytes(THUMBNAILS_DIR)
    status = CleanupStatus.CLEAN if size == 0 else CleanupStatus.AVAILABLE
    return _target(
        "thumbnails",
        "Thumbnails",
        "Clear cached preview thumbnails.",
        status,
        estimated_bytes=size,
        details="This only clears thumbnail cache files.",
        preview=[str(THUMBNAILS_DIR)],
    )


def _scan_aur_cache() -> CleanupTarget:
    existing = [path for path in AUR_CACHE_DIRS if path.exists()]
    size = sum(directory_bytes(path) for path in existing)
    status = CleanupStatus.UNAVAILABLE if not existing else CleanupStatus.AVAILABLE
    return _target(
        "aur-cache",
        "AUR cache",
        "Remove leftover build or package cache from yay or paru.",
        status,
        estimated_bytes=size,
        details="Only known yay and paru cache paths are included.",
        available=bool(existing),
        preview=[str(path) for path in existing],
    )


def _scan_flatpak() -> CleanupTarget | None:
    if not command_exists("flatpak"):
        return None
    preview = get_flatpak_unused_preview()
    preview_unavailable = "does not support dry-run preview" in preview
    status = CleanupStatus.CLEAN if "Nothing unused" in preview else CleanupStatus.AVAILABLE
    return _target(
        "flatpak-cache",
        "Flatpak unused data",
        "Remove unused Flatpak runtimes and related data.",
        status,
        estimated_bytes=None,
        details=(
            "Uses flatpak uninstall --unused."
            if not preview_unavailable
            else "Flatpak cleanup is available, but this Flatpak version cannot preview unused removals."
        ),
        preview=preview.splitlines()[:25],
    )


def scan_system() -> ScanReport:
    arch = is_arch_linux()
    notes: list[str] = []
    if not arch:
        notes.append("Arch Linux was not detected. Cleanup commands are disabled.")
    targets = [
        _scan_pacman_cache(),
        _scan_orphans(),
        _scan_journal(),
        _scan_user_cache(),
        _scan_trash(),
        _scan_thumbnails(),
        _scan_aur_cache(),
    ]
    flatpak_target = _scan_flatpak()
    if flatpak_target is not None:
        targets.append(flatpak_target)
    return ScanReport(arch_linux=arch, generated_at=now_iso(), targets=targets, notes=notes)

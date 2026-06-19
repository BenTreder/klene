from __future__ import annotations

import shutil
from pathlib import Path

from klene.commands import get_orphan_packages
from klene.models import CleanupResult
from klene.safety import command_exists, is_safe_path, safe_run_command
from klene.scanner import (
    AUR_CACHE_DIRS,
    LOW_RISK_USER_CACHE_DIRS,
    THUMBNAILS_DIR,
    TRASH_FILES_DIR,
    TRASH_INFO_DIR,
)
from klene.utils import dir_size


def _delete_children(path: Path, *, dry_run: bool) -> int:
    if not path.exists():
        return 0
    if not is_safe_path(path):
        raise ValueError(f"Refusing unsafe path: {path}")
    reclaimed = 0
    for child in path.iterdir():
        try:
            size = dir_size(child) if child.is_dir() else child.stat().st_size
        except OSError:
            size = 0
        reclaimed += size
        if dry_run:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)
    return reclaimed


def clean_pacman_cache(*, keep: int = 3, dry_run: bool = True) -> CleanupResult:
    command = ["paccache", "-r", "-k", str(keep)]
    if not command_exists("paccache"):
        return CleanupResult(
            key="pacman-cache",
            dry_run=dry_run,
            success=False,
            message="paccache not found. Install pacman-contrib first.",
            command=command,
        )
    if dry_run:
        command = ["paccache", "-d", "-k", str(keep), "-v"]
    result = safe_run_command(command)
    return CleanupResult(
        key="pacman-cache",
        dry_run=dry_run,
        success=result.returncode == 0,
        message=result.stdout.strip() or result.stderr.strip() or "Pacman cache cleanup completed.",
        command=command,
    )


def clean_orphans(*, dry_run: bool = True) -> CleanupResult:
    if not command_exists("pacman"):
        return CleanupResult(
            key="orphans",
            dry_run=dry_run,
            success=False,
            message="pacman not found.",
            command=["pacman", "-Qdtq"],
        )
    packages = get_orphan_packages()
    if not packages:
        return CleanupResult(
            key="orphans",
            dry_run=dry_run,
            success=True,
            message="No orphan packages found.",
            details=[],
        )
    command = ["pacman", "-Rns"] + packages
    if dry_run:
        return CleanupResult(
            key="orphans",
            dry_run=True,
            success=True,
            message="Dry run only. Review orphan packages before removal.",
            command=command,
            details=packages,
        )
    result = safe_run_command(command)
    return CleanupResult(
        key="orphans",
        dry_run=False,
        success=result.returncode == 0,
        message=result.stdout.strip() or result.stderr.strip() or "Orphan removal completed.",
        command=command,
        details=packages,
    )


def clean_journal(*, vacuum_time: str = "14d", dry_run: bool = True) -> CleanupResult:
    command = ["journalctl", f"--vacuum-time={vacuum_time}"]
    if not command_exists("journalctl"):
        return CleanupResult(
            key="journal",
            dry_run=dry_run,
            success=False,
            message="journalctl not found.",
            command=command,
        )
    if dry_run:
        return CleanupResult(
            key="journal",
            dry_run=True,
            success=True,
            message=f"Dry run only. Would run {' '.join(command)}",
            command=command,
        )
    result = safe_run_command(command)
    return CleanupResult(
        key="journal",
        dry_run=False,
        success=result.returncode == 0,
        message=result.stdout.strip() or result.stderr.strip() or "Journal cleanup completed.",
        command=command,
    )


def clean_user_cache(*, dry_run: bool = True) -> CleanupResult:
    reclaimed = 0
    touched: list[str] = []
    for path in LOW_RISK_USER_CACHE_DIRS:
        reclaimed += _delete_children(path, dry_run=dry_run)
        if path.exists():
            touched.append(str(path))
    return CleanupResult(
        key="user-cache",
        dry_run=dry_run,
        success=True,
        message="Processed low-risk user cache directories.",
        reclaimed_bytes=reclaimed,
        details=touched,
    )


def clean_trash(*, dry_run: bool = True) -> CleanupResult:
    reclaimed = _delete_children(TRASH_FILES_DIR, dry_run=dry_run) + _delete_children(
        TRASH_INFO_DIR, dry_run=dry_run
    )
    return CleanupResult(
        key="trash",
        dry_run=dry_run,
        success=True,
        message="Processed trash contents.",
        reclaimed_bytes=reclaimed,
        details=[str(TRASH_FILES_DIR), str(TRASH_INFO_DIR)],
    )


def clean_thumbnails(*, dry_run: bool = True) -> CleanupResult:
    reclaimed = _delete_children(THUMBNAILS_DIR, dry_run=dry_run)
    return CleanupResult(
        key="thumbnails",
        dry_run=dry_run,
        success=True,
        message="Processed thumbnail cache.",
        reclaimed_bytes=reclaimed,
        details=[str(THUMBNAILS_DIR)],
    )


def clean_aur_cache(*, dry_run: bool = True) -> CleanupResult:
    reclaimed = 0
    touched: list[str] = []
    for path in AUR_CACHE_DIRS:
        if path.exists():
            reclaimed += _delete_children(path, dry_run=dry_run)
            touched.append(str(path))
    return CleanupResult(
        key="aur-cache",
        dry_run=dry_run,
        success=True,
        message="Processed AUR helper cache directories.",
        reclaimed_bytes=reclaimed,
        details=touched,
    )


def clean_flatpak_unused(*, dry_run: bool = True) -> CleanupResult:
    command = ["flatpak", "uninstall", "--unused"]
    if not command_exists("flatpak"):
        return CleanupResult(
            key="flatpak-cache",
            dry_run=dry_run,
            success=False,
            message="flatpak not found.",
            command=command,
        )
    if dry_run:
        return CleanupResult(
            key="flatpak-cache",
            dry_run=True,
            success=True,
            message="Dry-run preview is not supported by this Flatpak version. Cleanup was not executed.",
            command=command,
        )
    result = safe_run_command(command)
    return CleanupResult(
        key="flatpak-cache",
        dry_run=dry_run,
        success=result.returncode == 0,
        message=result.stdout.strip() or result.stderr.strip() or "Flatpak cleanup completed.",
        command=command,
    )


def clean_all(*, keep: int = 3, vacuum_time: str = "14d", dry_run: bool = True) -> list[CleanupResult]:
    results = [
        clean_pacman_cache(keep=keep, dry_run=dry_run),
        clean_orphans(dry_run=dry_run),
        clean_journal(vacuum_time=vacuum_time, dry_run=dry_run),
        clean_user_cache(dry_run=dry_run),
        clean_trash(dry_run=dry_run),
        clean_thumbnails(dry_run=dry_run),
        clean_aur_cache(dry_run=dry_run),
    ]
    if command_exists("flatpak"):
        results.append(clean_flatpak_unused(dry_run=dry_run))
    return results

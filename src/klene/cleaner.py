from __future__ import annotations

from klene.models import CleanupResult
from klene.platforms import get_provider


def _clean_single(category_id: str, *, dry_run: bool = True, **options: object) -> CleanupResult:
    provider = get_provider()
    return provider.clean_one(category_id, dry_run=dry_run, **options)


def clean_pacman_cache(*, keep: int = 3, dry_run: bool = True) -> CleanupResult:
    return _clean_single("pacman-cache", keep=keep, dry_run=dry_run)


def clean_orphans(*, dry_run: bool = True) -> CleanupResult:
    return _clean_single("orphans", dry_run=dry_run)


def clean_journal(*, vacuum_time: str = "14d", dry_run: bool = True) -> CleanupResult:
    return _clean_single("journal", vacuum_time=vacuum_time, dry_run=dry_run)


def clean_user_cache(*, dry_run: bool = True) -> CleanupResult:
    return _clean_single("user-cache", dry_run=dry_run)


def clean_trash(*, dry_run: bool = True) -> CleanupResult:
    return _clean_single("trash", dry_run=dry_run)


def clean_thumbnails(*, dry_run: bool = True) -> CleanupResult:
    return _clean_single("thumbnails", dry_run=dry_run)


def clean_aur_cache(*, dry_run: bool = True) -> CleanupResult:
    return _clean_single("aur-cache", dry_run=dry_run)


def clean_flatpak_unused(*, dry_run: bool = True) -> CleanupResult:
    return _clean_single("flatpak-cache", dry_run=dry_run)


def clean_all(*, keep: int = 3, vacuum_time: str = "14d", dry_run: bool = True) -> list[CleanupResult]:
    provider = get_provider()
    options = {"keep": keep, "vacuum_time": vacuum_time}
    return provider.clean(provider.available_category_ids(), dry_run=dry_run, **options)

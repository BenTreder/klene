from __future__ import annotations

from pathlib import Path

from klene.commands import directory_bytes, get_orphan_packages
from klene.models import CleanupResult, CleanupStatus, SupportLevel
from klene.platforms.base import (
    LINUX_LOW_RISK_USER_CACHE_DIRS,
    CleanupCategoryDefinition,
    ProviderDoctorCheck,
)
from klene.platforms.generic_linux import GenericLinuxProvider
from klene.safety import command_exists
from klene.utils import format_bytes, format_display_path

PACMAN_CACHE_DIR = Path("/var/cache/pacman/pkg")
AUR_CACHE_DIRS = [Path.home() / ".cache" / "yay", Path.home() / ".cache" / "paru"]


class ArchProvider(GenericLinuxProvider):
    provider_name = "ArchProvider"
    platform_id = "arch"
    platform_name = "Arch Linux"
    support_level = SupportLevel.FULL
    support_label = "Full support"
    status_message = "Full Arch Linux cleanup support detected."
    safety_notes = [
        "Pacman cache cleanup uses paccache instead of broad pacman -Scc cleanup.",
        "Package removal stays opt-in and requires extra confirmation.",
    ]

    def __init__(self) -> None:
        if not command_exists("pacman"):
            self.support_level = SupportLevel.PREVIEW
            self.support_label = "Partial support"
            self.status_message = "Arch-like system detected, but pacman is not currently available in PATH."
        super().__init__()

    def build_category_definitions(self):
        return [
            CleanupCategoryDefinition(
                id="pacman-cache",
                title="Pacman cache",
                description="Remove older cached package files while keeping recent versions.",
                group="recommended",
                safety_level="recommended",
                what_happens="Klene uses paccache and keeps recent package versions.",
                requires_admin=True,
            ),
            CleanupCategoryDefinition(
                id="trash",
                title="Trash",
                description="Empty files already moved to the trash.",
                group="recommended",
                safety_level="recommended",
                what_happens="Klene removes items inside the trash folders after confirmation.",
            ),
            CleanupCategoryDefinition(
                id="thumbnails",
                title="Thumbnails",
                description="Clear cached preview thumbnails.",
                group="recommended",
                safety_level="recommended",
                what_happens="Klene removes thumbnail cache files only.",
            ),
            CleanupCategoryDefinition(
                id="user-cache",
                title="Low-risk user cache",
                description="Clean allowlisted cache folders inside your home directory.",
                group="recommended",
                safety_level="recommended",
                what_happens="Klene only cleans allowlisted subdirectories inside ~/.cache.",
            ),
            CleanupCategoryDefinition(
                id="journal",
                title="System journal",
                description="Trim old journal logs to save space.",
                group="review",
                safety_level="review_first",
                what_happens="Klene runs journalctl --vacuum-time=14d after confirmation.",
                default_selected=False,
                requires_admin=True,
            ),
            CleanupCategoryDefinition(
                id="aur-cache",
                title="AUR cache",
                description="Remove leftover build or package cache from yay or paru.",
                group="review",
                safety_level="review_first",
                what_happens="Klene only touches known yay and paru cache paths.",
                default_selected=False,
            ),
            CleanupCategoryDefinition(
                id="flatpak-cache",
                title="Flatpak unused data",
                description="Review and remove unused Flatpak runtimes and data.",
                group="review",
                safety_level="review_first",
                what_happens="Klene runs flatpak uninstall --unused after confirmation.",
                default_selected=False,
            ),
            CleanupCategoryDefinition(
                id="orphans",
                title="Orphan packages",
                description="Review packages no longer required by anything else.",
                group="advanced",
                safety_level="advanced",
                what_happens="Klene shows orphan packages first and only removes them after extra confirmation.",
                default_selected=False,
                requires_admin=True,
                requires_extra_confirmation=True,
            ),
        ]

    def scan(self):
        targets = [self._scan_pacman_cache(), self._scan_trash(), self._scan_thumbnails(), self._scan_user_cache()]
        if command_exists("journalctl"):
            targets.append(self._scan_journal())
        targets.append(self._scan_aur_cache())
        if command_exists("flatpak"):
            flatpak = self._scan_flatpak()
            if flatpak is not None:
                targets.append(flatpak)
        targets.append(self._scan_orphans())
        return targets

    def _scan_pacman_cache(self):
        size = directory_bytes(PACMAN_CACHE_DIR)
        details = f"Current cache size: {format_bytes(size)}."
        if command_exists("paccache"):
            details += " paccache is ready."
        else:
            details += " Install pacman-contrib to enable safer cache trimming."
        return self._make_target(
            "pacman-cache",
            CleanupStatus.CLEAN if size == 0 else CleanupStatus.AVAILABLE,
            estimated_bytes=size,
            details=details,
            available=PACMAN_CACHE_DIR.exists(),
            command_preview=["paccache -r -k 3", "paccache -d -k 3 -v"],
            preview=[format_display_path(PACMAN_CACHE_DIR)],
            display_paths=[format_display_path(PACMAN_CACHE_DIR)],
        )

    def _scan_aur_cache(self):
        existing = [path for path in AUR_CACHE_DIRS if path.exists()]
        size = sum(directory_bytes(path) for path in existing)
        return self._make_target(
            "aur-cache",
            CleanupStatus.UNAVAILABLE if not existing else CleanupStatus.AVAILABLE,
            estimated_bytes=size,
            details="Only known yay and paru cache paths are included." if existing else "No supported yay or paru cache paths were found on this system.",
            available=bool(existing),
            preview=[format_display_path(path) for path in existing],
            display_paths=[format_display_path(path) for path in existing],
        )

    def _scan_orphans(self):
        if not command_exists("pacman"):
            return self._make_target(
                "orphans",
                CleanupStatus.UNAVAILABLE,
                available=False,
                details="pacman is not available, so orphan packages cannot be checked.",
                command_preview=["pacman -Qdtq", "pacman -Rns <packages>"],
            )
        packages = get_orphan_packages()
        return self._make_target(
            "orphans",
            CleanupStatus.CLEAN if not packages else CleanupStatus.WARNING,
            details="No orphan packages found." if not packages else f"{len(packages)} orphan package(s) found.",
            count=len(packages),
            preview=packages[:25],
            command_preview=["pacman -Qdtq", "pacman -Rns <packages>"],
        )

    def clean_one(self, category_id: str, *, dry_run: bool = True, **options: object) -> CleanupResult:
        if category_id == "pacman-cache":
            if not command_exists("paccache"):
                return CleanupResult(
                    key="pacman-cache",
                    dry_run=dry_run,
                    success=False,
                    message="paccache not found. Install pacman-contrib first.",
                    command=["paccache", "-r", "-k", str(options.get("keep", 3))],
                )
            keep = str(options.get("keep", 3))
            command = ["paccache", "-d", "-k", keep, "-v"] if dry_run else ["paccache", "-r", "-k", keep]
            return self._run_cleanup_command(
                "pacman-cache",
                command,
                dry_run=dry_run,
                preview_message=f"Dry run only. Would run {' '.join(command)}",
            )
        if category_id == "orphans":
            packages = get_orphan_packages()
            if not packages:
                return CleanupResult(key="orphans", dry_run=dry_run, success=True, message="No orphan packages found.")
            if dry_run:
                return CleanupResult(
                    key="orphans",
                    dry_run=True,
                    success=True,
                    message="Dry run only. Review orphan packages before removal.",
                    command=["pacman", "-Rns", *packages],
                    details=packages,
                )
            return self._run_cleanup_command(
                "orphans",
                ["pacman", "-Rns", *packages],
                dry_run=False,
                preview_message="",
            )
        if category_id == "aur-cache":
            reclaimed = 0
            touched: list[str] = []
            skipped = 0
            for path in AUR_CACHE_DIRS:
                if not path.exists():
                    continue
                outcome = self._delete_children(path, dry_run=dry_run, allowed_roots=[path])
                reclaimed += outcome.reclaimed_bytes
                skipped += outcome.skipped
                touched.extend(outcome.touched)
            message = "Processed AUR helper cache directories."
            if skipped:
                message += f" Skipped {skipped} locked or inaccessible item(s)."
            return CleanupResult(
                key="aur-cache",
                dry_run=dry_run,
                success=True,
                message=message,
                reclaimed_bytes=reclaimed,
                details=touched,
            )
        return super().clean_one(category_id, dry_run=dry_run, **options)

    def doctor_checks(self) -> list[ProviderDoctorCheck]:
        checks = super().doctor_checks()
        checks.extend(
            [
                ProviderDoctorCheck("pacman found", command_exists("pacman"), "Package manager available."),
                ProviderDoctorCheck("paccache found", command_exists("paccache"), "Safer package cache trimming available."),
            ]
        )
        checks.extend(
            ProviderDoctorCheck(f"AUR cache path: {path.name}", path.exists(), str(path)) for path in AUR_CACHE_DIRS
        )
        checks.extend(
            ProviderDoctorCheck(f"Low-risk cache path: {path.name}", path.exists(), str(path))
            for path in LINUX_LOW_RISK_USER_CACHE_DIRS
        )
        return checks

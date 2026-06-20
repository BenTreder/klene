from __future__ import annotations

from pathlib import Path

from klene.commands import directory_bytes
from klene.models import CleanupResult, CleanupStatus, SupportLevel
from klene.platforms.base import CleanupCategoryDefinition, ProviderDoctorCheck
from klene.platforms.generic_linux import GenericLinuxProvider
from klene.safety import command_exists
from klene.utils import format_display_path

ZYPPER_CACHE_DIR = Path("/var/cache/zypp")


class OpenSUSEProvider(GenericLinuxProvider):
    provider_name = "OpenSUSEProvider"
    platform_id = "opensuse"
    platform_name = "openSUSE"
    support_level = SupportLevel.PREVIEW
    support_label = "Working support"
    status_message = "Preview and cleanup support detected for this Linux system."
    safety_notes = [
        "Zypper cache cleanup stays preview-first.",
        "Automatic package autoremove is intentionally not implemented for this provider in this phase.",
    ]

    def build_category_definitions(self):
        return [
            CleanupCategoryDefinition(
                id="zypper-cache",
                title="Zypper cache",
                description="Clean zypp package cache data.",
                group="review",
                safety_level="review_first",
                what_happens="Klene runs zypper clean after confirmation.",
                default_selected=False,
                requires_admin=True,
            ),
            *super().build_category_definitions(),
        ]

    def scan(self):
        targets = [self._scan_zypper_cache(), self._scan_trash(), self._scan_thumbnails(), self._scan_user_cache()]
        if command_exists("journalctl"):
            targets.append(self._scan_journal())
        if command_exists("flatpak"):
            flatpak = self._scan_flatpak()
            if flatpak is not None:
                targets.append(flatpak)
        return targets

    def _scan_zypper_cache(self):
        size = directory_bytes(ZYPPER_CACHE_DIR)
        return self._make_target(
            "zypper-cache",
            CleanupStatus.CLEAN if size == 0 else CleanupStatus.AVAILABLE,
            estimated_bytes=size,
            details="Klene can clean the zypp cache after confirmation.",
            available=ZYPPER_CACHE_DIR.exists(),
            command_preview=["zypper clean"],
            preview=[format_display_path(ZYPPER_CACHE_DIR)],
            display_paths=[format_display_path(ZYPPER_CACHE_DIR)],
        )

    def clean_one(self, category_id: str, *, dry_run: bool = True, **options: object) -> CleanupResult:
        if category_id == "zypper-cache":
            return self._run_cleanup_command(
                "zypper-cache",
                ["zypper", "clean"],
                dry_run=dry_run,
                preview_message="Dry run only. zypper clean removes cached package data.",
            )
        return super().clean_one(category_id, dry_run=dry_run, **options)

    def doctor_checks(self) -> list[ProviderDoctorCheck]:
        checks = super().doctor_checks()
        checks.extend(
            [
                ProviderDoctorCheck("zypper found", command_exists("zypper"), "Zypper command available."),
                ProviderDoctorCheck("Zypper cache directory", ZYPPER_CACHE_DIR.exists(), str(ZYPPER_CACHE_DIR)),
            ]
        )
        return checks

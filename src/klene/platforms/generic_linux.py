from __future__ import annotations

from klene.models import CleanupResult, CleanupStatus, SupportLevel
from klene.platforms.base import LinuxProvider, ProviderDoctorCheck, build_linux_generic_categories
from klene.safety import command_exists


class GenericLinuxProvider(LinuxProvider):
    provider_name = "GenericLinuxProvider"
    platform_id = "generic_linux"
    platform_name = "Generic Linux"
    support_level = SupportLevel.BASIC
    support_label = "Working basic support"
    status_message = "Basic Linux cleanup support detected."
    safety_notes = [
        "Only allowlisted trash and cache paths are cleaned.",
        "Package manager cleanup is only available in distro-specific providers.",
    ]

    def build_category_definitions(self):
        return build_linux_generic_categories()

    def scan(self):
        targets = [
            self._scan_trash(),
            self._scan_thumbnails(),
            self._scan_user_cache(),
        ]
        if command_exists("journalctl"):
            targets.append(self._scan_journal())
        if command_exists("flatpak"):
            flatpak = self._scan_flatpak()
            if flatpak is not None:
                targets.append(flatpak)
        return targets

    def clean_one(self, category_id: str, *, dry_run: bool = True, **options: object) -> CleanupResult:
        if category_id == "trash":
            return self._clean_trash(dry_run=dry_run)
        if category_id == "thumbnails":
            return self._clean_thumbnails(dry_run=dry_run)
        if category_id == "user-cache":
            return self._clean_user_cache(dry_run=dry_run)
        if category_id == "journal":
            return self._clean_journal(dry_run=dry_run, vacuum_time=str(options.get("vacuum_time", "14d")))
        if category_id == "flatpak-cache":
            return self._clean_flatpak(dry_run=dry_run)
        return super().clean_one(category_id, dry_run=dry_run, **options)

    def doctor_checks(self) -> list[ProviderDoctorCheck]:
        checks = super().doctor_checks()
        checks.extend(
            [
                ProviderDoctorCheck("Trash support", True, "User trash folders are allowlisted."),
                ProviderDoctorCheck("Low-risk cache support", True, "Selected ~/.cache subdirectories are allowlisted."),
            ]
        )
        return checks

from __future__ import annotations

from pathlib import Path

from klene.commands import directory_bytes, run_optional_command
from klene.models import CleanupResult, CleanupStatus, SupportLevel
from klene.platforms.base import CleanupCategoryDefinition, ProviderDoctorCheck
from klene.platforms.generic_linux import GenericLinuxProvider
from klene.safety import command_exists
from klene.utils import format_display_path

DNF_CACHE_DIR = Path("/var/cache/dnf")


class FedoraProvider(GenericLinuxProvider):
    provider_name = "FedoraProvider"
    platform_id = "fedora"
    platform_name = "Fedora"
    support_level = SupportLevel.PREVIEW
    support_label = "Working support"
    status_message = "Preview and cleanup support detected for this Linux system."
    safety_notes = [
        "DNF cache cleanup stays preview-first.",
        "Autoremove remains advanced and extra-confirmed.",
    ]

    def build_category_definitions(self):
        return [
            CleanupCategoryDefinition(
                id="dnf-cache",
                title="DNF cache",
                description="Remove cached DNF packages.",
                group="review",
                safety_level="review_first",
                what_happens="Klene runs dnf clean packages after confirmation.",
                default_selected=False,
                requires_admin=True,
            ),
            *super().build_category_definitions(),
            CleanupCategoryDefinition(
                id="dnf-autoremove",
                title="DNF autoremove candidates",
                description="Review packages DNF considers unneeded.",
                group="advanced",
                safety_level="advanced",
                what_happens="Klene previews DNF autoremove first and requires extra confirmation before removal.",
                default_selected=False,
                requires_admin=True,
                requires_extra_confirmation=True,
            ),
        ]

    def scan(self):
        targets = [self._scan_dnf_cache(), self._scan_trash(), self._scan_thumbnails(), self._scan_user_cache()]
        if command_exists("journalctl"):
            targets.append(self._scan_journal())
        if command_exists("flatpak"):
            flatpak = self._scan_flatpak()
            if flatpak is not None:
                targets.append(flatpak)
        targets.append(self._scan_dnf_autoremove())
        return targets

    def _scan_dnf_cache(self):
        size = directory_bytes(DNF_CACHE_DIR)
        return self._make_target(
            "dnf-cache",
            CleanupStatus.CLEAN if size == 0 else CleanupStatus.AVAILABLE,
            estimated_bytes=size,
            details="Klene cleans cached DNF package files after confirmation.",
            available=DNF_CACHE_DIR.exists(),
            command_preview=["dnf clean packages"],
            preview=[format_display_path(DNF_CACHE_DIR)],
            display_paths=[format_display_path(DNF_CACHE_DIR)],
        )

    def _scan_dnf_autoremove(self):
        if not command_exists("dnf"):
            return self._make_target(
                "dnf-autoremove",
                CleanupStatus.UNAVAILABLE,
                available=False,
                details="dnf is not available on this system.",
                command_preview=["dnf repoquery --unneeded", "dnf autoremove"],
            )
        if command_exists("repoquery"):
            outcome = run_optional_command(["repoquery", "--unneeded"])
        else:
            outcome = run_optional_command(["dnf", "autoremove", "--assumeno"])
        preview = [line.strip() for line in outcome.stdout.splitlines() if line.strip()]
        return self._make_target(
            "dnf-autoremove",
            CleanupStatus.CLEAN if not preview else CleanupStatus.WARNING,
            details="No DNF autoremove candidates found." if not preview else f"{len(preview)} candidate line(s) returned.",
            preview=preview[:25],
            command_preview=["dnf repoquery --unneeded", "dnf autoremove --assumeno", "dnf autoremove"],
            count=len(preview),
        )

    def clean_one(self, category_id: str, *, dry_run: bool = True, **options: object) -> CleanupResult:
        if category_id == "dnf-cache":
            return self._run_cleanup_command(
                "dnf-cache",
                ["dnf", "clean", "packages"],
                dry_run=dry_run,
                preview_message="Dry run only. dnf clean packages removes cached package files.",
            )
        if category_id == "dnf-autoremove":
            if dry_run:
                command = ["dnf", "autoremove", "--assumeno"]
                outcome = run_optional_command(command)
                return CleanupResult(
                    key="dnf-autoremove",
                    dry_run=True,
                    success=outcome.ok,
                    message="Dry run only. Review DNF autoremove candidates before removal.",
                    command=command,
                    details=outcome.stdout.splitlines()[:50],
                )
            return self._run_cleanup_command(
                "dnf-autoremove",
                ["dnf", "autoremove"],
                dry_run=False,
                preview_message="",
            )
        return super().clean_one(category_id, dry_run=dry_run, **options)

    def doctor_checks(self) -> list[ProviderDoctorCheck]:
        checks = super().doctor_checks()
        checks.extend(
            [
                ProviderDoctorCheck("dnf found", command_exists("dnf"), "DNF command available."),
                ProviderDoctorCheck("DNF cache directory", DNF_CACHE_DIR.exists(), str(DNF_CACHE_DIR)),
            ]
        )
        return checks

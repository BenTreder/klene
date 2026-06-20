from __future__ import annotations

from pathlib import Path

from klene.commands import directory_bytes, run_optional_command
from klene.models import CleanupResult, CleanupStatus, SupportLevel
from klene.platforms.base import CleanupCategoryDefinition, ProviderDoctorCheck
from klene.platforms.generic_linux import GenericLinuxProvider
from klene.safety import command_exists
from klene.utils import format_display_path

APT_CACHE_DIR = Path("/var/cache/apt/archives")
SNAP_CACHE_DIR = Path("/var/lib/snapd/cache")


class DebianProvider(GenericLinuxProvider):
    provider_name = "DebianProvider"
    platform_id = "debian"
    platform_name = "Debian / Ubuntu"
    support_level = SupportLevel.PREVIEW
    support_label = "Working support"
    status_message = "Preview and cleanup support detected for this Linux system."
    safety_notes = [
        "APT package removal stays advanced and extra-confirmed.",
        "Snap cache cleanup is conservative and may remain preview-only on some systems.",
    ]

    def build_category_definitions(self):
        return [
            CleanupCategoryDefinition(
                id="apt-cache",
                title="APT package cache",
                description="Remove cached .deb package files.",
                group="review",
                safety_level="review_first",
                what_happens="Klene runs apt-get clean after confirmation.",
                default_selected=False,
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
                id="flatpak-cache",
                title="Flatpak unused data",
                description="Review and remove unused Flatpak runtimes and data.",
                group="review",
                safety_level="review_first",
                what_happens="Klene runs flatpak uninstall --unused after confirmation.",
                default_selected=False,
            ),
            CleanupCategoryDefinition(
                id="snap-cache",
                title="Snap cache",
                description="Review conservative Snap cache cleanup.",
                group="review",
                safety_level="review_first",
                what_happens="Klene can clean the snapd cache directory after confirmation when it is present.",
                default_selected=False,
                requires_admin=True,
                can_clean=True,
            ),
            CleanupCategoryDefinition(
                id="apt-autoremove",
                title="APT autoremove candidates",
                description="Review packages that apt considers removable.",
                group="advanced",
                safety_level="advanced",
                what_happens="Klene previews apt-get autoremove first and requires extra confirmation before removal.",
                default_selected=False,
                requires_admin=True,
                requires_extra_confirmation=True,
            ),
        ]

    def scan(self):
        targets = [self._scan_apt_cache(), self._scan_trash(), self._scan_thumbnails(), self._scan_user_cache()]
        if command_exists("journalctl"):
            targets.append(self._scan_journal())
        if command_exists("flatpak"):
            flatpak = self._scan_flatpak()
            if flatpak is not None:
                targets.append(flatpak)
        snap_target = self._scan_snap_cache()
        if snap_target is not None:
            targets.append(snap_target)
        targets.append(self._scan_autoremove())
        return targets

    def _scan_apt_cache(self):
        size = directory_bytes(APT_CACHE_DIR)
        return self._make_target(
            "apt-cache",
            CleanupStatus.CLEAN if size == 0 else CleanupStatus.AVAILABLE,
            estimated_bytes=size,
            details="Klene removes cached .deb files with apt-get clean after confirmation.",
            available=APT_CACHE_DIR.exists(),
            command_preview=["apt-get -s clean", "apt-get clean"],
            preview=[format_display_path(APT_CACHE_DIR)],
            display_paths=[format_display_path(APT_CACHE_DIR)],
        )

    def _scan_autoremove(self):
        if not command_exists("apt-get"):
            return self._make_target(
                "apt-autoremove",
                CleanupStatus.UNAVAILABLE,
                available=False,
                details="apt-get is not available on this system.",
                command_preview=["apt-get -s autoremove", "apt-get autoremove"],
            )
        outcome = run_optional_command(["apt-get", "-s", "autoremove"])
        packages = [line.strip() for line in outcome.stdout.splitlines() if line.strip().startswith("Remv ")]
        return self._make_target(
            "apt-autoremove",
            CleanupStatus.CLEAN if not packages else CleanupStatus.WARNING,
            estimated_bytes=None,
            details="No apt autoremove candidates found." if not packages else f"{len(packages)} removable package(s) detected.",
            preview=packages[:25],
            command_preview=["apt-get -s autoremove", "apt-get autoremove"],
            count=len(packages),
        )

    def _scan_snap_cache(self):
        if not command_exists("snap") and not SNAP_CACHE_DIR.exists():
            return None
        size = directory_bytes(SNAP_CACHE_DIR)
        return self._make_target(
            "snap-cache",
            CleanupStatus.CLEAN if size == 0 else CleanupStatus.AVAILABLE,
            estimated_bytes=size,
            details="Conservative Snap cache cleanup for /var/lib/snapd/cache only.",
            available=SNAP_CACHE_DIR.exists(),
            preview=[format_display_path(SNAP_CACHE_DIR)],
            display_paths=[format_display_path(SNAP_CACHE_DIR)],
        )

    def clean_one(self, category_id: str, *, dry_run: bool = True, **options: object) -> CleanupResult:
        if category_id == "apt-cache":
            command = ["apt-get", "-s", "clean"] if dry_run else ["apt-get", "clean"]
            return self._run_cleanup_command(
                "apt-cache",
                command,
                dry_run=dry_run,
                preview_message="Dry run only. apt-get clean removes cached .deb files.",
            )
        if category_id == "apt-autoremove":
            if dry_run:
                outcome = run_optional_command(["apt-get", "-s", "autoremove"])
                return CleanupResult(
                    key="apt-autoremove",
                    dry_run=True,
                    success=outcome.ok,
                    message="Dry run only. Review apt autoremove candidates before removal.",
                    command=["apt-get", "autoremove"],
                    details=outcome.stdout.splitlines()[:50],
                )
            return self._run_cleanup_command(
                "apt-autoremove",
                ["apt-get", "autoremove"],
                dry_run=False,
                preview_message="",
            )
        if category_id == "snap-cache":
            if not SNAP_CACHE_DIR.exists():
                return CleanupResult(key="snap-cache", dry_run=dry_run, success=False, message="Snap cache path not found.")
            outcome = self._delete_children(SNAP_CACHE_DIR, dry_run=dry_run, allowed_roots=[SNAP_CACHE_DIR])
            message = "Processed snapd cache directory."
            if outcome.skipped:
                message += f" Skipped {outcome.skipped} locked or inaccessible item(s)."
            return CleanupResult(
                key="snap-cache",
                dry_run=dry_run,
                success=True,
                message=message,
                reclaimed_bytes=outcome.reclaimed_bytes,
                details=outcome.touched,
            )
        return super().clean_one(category_id, dry_run=dry_run, **options)

    def doctor_checks(self) -> list[ProviderDoctorCheck]:
        checks = super().doctor_checks()
        checks.extend(
            [
                ProviderDoctorCheck("apt-get found", command_exists("apt-get"), "APT command available."),
                ProviderDoctorCheck("APT cache directory", APT_CACHE_DIR.exists(), str(APT_CACHE_DIR)),
            ]
        )
        if command_exists("snap") or SNAP_CACHE_DIR.exists():
            checks.append(ProviderDoctorCheck("Snap cache directory", SNAP_CACHE_DIR.exists(), str(SNAP_CACHE_DIR)))
        return checks

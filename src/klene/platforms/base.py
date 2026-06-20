from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from klene.commands import (
    directory_bytes,
    get_flatpak_unused_preview,
    get_journal_disk_usage,
    get_orphan_packages,
    run_optional_command,
)
from klene.models import CleanupResult, CleanupStatus, CleanupTarget, PlatformInfo, SupportLevel
from klene.safety import command_exists, is_path_within, is_safe_path
from klene.utils import format_bytes, format_display_path, now_iso

LINUX_USER_CACHE_DIR = Path.home() / ".cache"
LINUX_TRASH_FILES_DIR = Path.home() / ".local" / "share" / "Trash" / "files"
LINUX_TRASH_INFO_DIR = Path.home() / ".local" / "share" / "Trash" / "info"
LINUX_THUMBNAILS_DIR = LINUX_USER_CACHE_DIR / "thumbnails"
LINUX_LOW_RISK_USER_CACHE_DIRS = [
    LINUX_THUMBNAILS_DIR,
    LINUX_USER_CACHE_DIR / "fontconfig",
    LINUX_USER_CACHE_DIR / "pip",
    LINUX_USER_CACHE_DIR / "go-build",
    LINUX_USER_CACHE_DIR / "npm",
    LINUX_USER_CACHE_DIR / "yarn",
]


@dataclass(frozen=True, slots=True)
class CleanupCategoryDefinition:
    id: str
    title: str
    description: str
    group: str
    safety_level: str
    what_happens: str
    default_selected: bool = True
    can_clean: bool = True
    requires_admin: bool = False
    requires_extra_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class ProviderDoctorCheck:
    label: str
    ok: bool
    detail: str


@dataclass(slots=True)
class DeletionOutcome:
    reclaimed_bytes: int
    skipped: int
    touched: list[str]


class CleanupProvider:
    provider_name = "CleanupProvider"
    platform_id = "unknown"
    platform_name = "Unknown"
    platform_family = "unknown"
    support_level = SupportLevel.UNSUPPORTED
    support_label = "Unsupported"
    status_message = "Klene could not determine safe cleanup support for this system."
    safety_notes: list[str] = []

    def __init__(self) -> None:
        self.category_definitions: dict[str, CleanupCategoryDefinition] = {
            category.id: category for category in self.build_category_definitions()
        }

    def build_category_definitions(self) -> list[CleanupCategoryDefinition]:
        raise NotImplementedError

    def get_category_definitions(self) -> list[CleanupCategoryDefinition]:
        return list(self.category_definitions.values())

    def get_platform_info(self) -> PlatformInfo:
        return PlatformInfo(
            platform_id=self.platform_id,
            platform_name=self.platform_name,
            platform_family=self.platform_family,
            is_supported=self.support_level is not SupportLevel.UNSUPPORTED,
            support_level=self.support_level,
            provider_name=self.provider_name,
            support_label=self.support_label,
            status_message=self.status_message,
            safety_notes=list(self.safety_notes),
            available_cleanup_areas=[category.title for category in self.get_category_definitions()],
            unavailable_cleanup_areas=[],
        )

    def scan(self) -> list[CleanupTarget]:
        raise NotImplementedError

    def preview(self, selected_category_ids: list[str]) -> list[str]:
        targets = {target.key: target for target in self.scan()}
        lines = ["This is only a preview. Nothing has been removed.", ""]
        for key in selected_category_ids:
            target = targets.get(key)
            if target is None:
                continue
            lines.append(f"{target.title} ({format_bytes(target.estimated_bytes)})")
            lines.append(f"Safety: {target.safety_level.replace('_', ' ')}")
            lines.append(f"What happens: {target.what_happens or target.details}")
            if target.command_preview:
                lines.append("Commands or actions:")
                lines.extend(f"  - {line}" for line in target.command_preview)
            if target.display_paths:
                lines.append("Paths:")
                lines.extend(f"  - {line}" for line in target.display_paths[:10])
            elif target.preview:
                lines.append("Preview:")
                lines.extend(f"  - {line}" for line in target.preview[:10])
            lines.append("")
        return lines

    def clean(self, selected_category_ids: list[str], *, dry_run: bool = True, **options: object) -> list[CleanupResult]:
        return [self.clean_one(category_id, dry_run=dry_run, **options) for category_id in selected_category_ids]

    def clean_one(self, category_id: str, *, dry_run: bool = True, **options: object) -> CleanupResult:
        return CleanupResult(
            key=category_id,
            dry_run=dry_run,
            success=False,
            message="This cleanup area is not available on this platform.",
        )

    def doctor_checks(self) -> list[ProviderDoctorCheck]:
        return []

    def available_category_ids(self) -> list[str]:
        return [category.id for category in self.get_category_definitions()]

    def category(self, category_id: str) -> CleanupCategoryDefinition | None:
        return self.category_definitions.get(category_id)

    def _make_target(
        self,
        category_id: str,
        status: CleanupStatus,
        *,
        estimated_bytes: int | None = None,
        details: str = "",
        preview: list[str] | None = None,
        count: int | None = None,
        available: bool = True,
        cleanup_supported: bool | None = None,
        command_preview: list[str] | None = None,
        display_paths: list[str] | None = None,
    ) -> CleanupTarget:
        category = self.category_definitions[category_id]
        return CleanupTarget(
            key=category.id,
            title=category.title,
            description=category.description,
            status=status,
            estimated_bytes=estimated_bytes,
            details=details,
            count=count,
            available=available,
            selected_by_default=category.default_selected,
            preview=preview or [],
            cleanup_supported=category.can_clean if cleanup_supported is None else cleanup_supported,
            group=category.group,
            safety_level=category.safety_level,
            what_happens=category.what_happens,
            command_preview=command_preview or [],
            requires_admin=category.requires_admin,
            requires_extra_confirmation=category.requires_extra_confirmation,
            display_paths=display_paths or [],
        )


class LinuxProvider(CleanupProvider):
    platform_family = "linux"

    def _scan_trash(self) -> CleanupTarget:
        size = directory_bytes(LINUX_TRASH_FILES_DIR) + directory_bytes(LINUX_TRASH_INFO_DIR)
        return self._make_target(
            "trash",
            CleanupStatus.CLEAN if size == 0 else CleanupStatus.AVAILABLE,
            estimated_bytes=size,
            details="Nothing is removed until you confirm cleanup.",
            preview=[format_display_path(LINUX_TRASH_FILES_DIR), format_display_path(LINUX_TRASH_INFO_DIR)],
            display_paths=[format_display_path(LINUX_TRASH_FILES_DIR), format_display_path(LINUX_TRASH_INFO_DIR)],
        )

    def _scan_thumbnails(self) -> CleanupTarget:
        size = directory_bytes(LINUX_THUMBNAILS_DIR)
        return self._make_target(
            "thumbnails",
            CleanupStatus.CLEAN if size == 0 else CleanupStatus.AVAILABLE,
            estimated_bytes=size,
            details="This only clears thumbnail cache files.",
            preview=[format_display_path(LINUX_THUMBNAILS_DIR)],
            display_paths=[format_display_path(LINUX_THUMBNAILS_DIR)],
        )

    def _scan_user_cache(self) -> CleanupTarget:
        low_risk_total = sum(directory_bytes(path) for path in LINUX_LOW_RISK_USER_CACHE_DIRS)
        display_paths = [format_display_path(path) for path in LINUX_LOW_RISK_USER_CACHE_DIRS if path.exists()]
        return self._make_target(
            "user-cache",
            CleanupStatus.CLEAN if low_risk_total == 0 else CleanupStatus.AVAILABLE,
            estimated_bytes=low_risk_total,
            details=(
                f"Klene only targets allowlisted cache folders inside ~/.cache. "
                f"Estimated low-risk cleanup: {format_bytes(low_risk_total)}."
            ),
            preview=display_paths,
            display_paths=display_paths,
        )

    def _scan_journal(self) -> CleanupTarget:
        if not command_exists("journalctl"):
            return self._make_target(
                "journal",
                CleanupStatus.UNAVAILABLE,
                available=False,
                details="journalctl is not available on this system.",
                command_preview=["journalctl --vacuum-time=14d"],
            )
        raw = get_journal_disk_usage()
        return self._make_target(
            "journal",
            CleanupStatus.AVAILABLE,
            estimated_bytes=None,
            details=raw,
            command_preview=["journalctl --vacuum-time=14d"],
        )

    def _scan_flatpak(self) -> CleanupTarget | None:
        if not command_exists("flatpak"):
            return None
        preview = get_flatpak_unused_preview()
        details = (
            "Flatpak can clean unused data after confirmation."
            if "--dry-run" not in preview
            else "Flatpak preview available."
        )
        return self._make_target(
            "flatpak-cache",
            CleanupStatus.CLEAN if "Nothing unused" in preview else CleanupStatus.AVAILABLE,
            estimated_bytes=None,
            details=details,
            preview=preview.splitlines()[:25],
            command_preview=["flatpak uninstall --unused --dry-run", "flatpak uninstall --unused"],
        )

    def _delete_children(
        self,
        path: Path | PureWindowsPath,
        *,
        dry_run: bool,
        allowed_roots: list[Path | PureWindowsPath] | None = None,
        name_prefixes: tuple[str, ...] | None = None,
    ) -> DeletionOutcome:
        real_path = Path(path)
        if not real_path.exists():
            return DeletionOutcome(0, 0, [])
        if not is_safe_path(real_path):
            raise ValueError(f"Refusing unsafe path: {path}")
        if allowed_roots and not any(is_path_within(real_path, Path(root)) for root in allowed_roots):
            raise ValueError(f"Refusing non-allowlisted path: {path}")

        reclaimed = 0
        skipped = 0
        touched = [format_display_path(real_path)]
        for child in real_path.iterdir():
            if name_prefixes and not child.name.startswith(name_prefixes):
                continue
            try:
                size = directory_bytes(child) if child.is_dir() else child.stat().st_size
            except OSError:
                size = 0
            reclaimed += size
            if dry_run:
                continue
            try:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink(missing_ok=True)
            except (OSError, PermissionError):
                skipped += 1
        return DeletionOutcome(reclaimed, skipped, touched)

    def _run_cleanup_command(
        self,
        category_id: str,
        command: list[str],
        *,
        dry_run: bool,
        preview_message: str,
    ) -> CleanupResult:
        if dry_run:
            return CleanupResult(
                key=category_id,
                dry_run=True,
                success=True,
                message=preview_message,
                command=command,
            )
        result = subprocess.run(command, capture_output=True, text=True)
        success = result.returncode == 0
        message = result.stdout.strip() or result.stderr.strip() or "Cleanup command completed."
        if not success and ("permission denied" in message.lower() or "not permitted" in message.lower()):
            message += " Run Klene as root or with administrator privileges for this cleanup area."
        return CleanupResult(
            key=category_id,
            dry_run=False,
            success=success,
            message=message,
            command=command,
        )

    def _clean_trash(self, *, dry_run: bool) -> CleanupResult:
        outcome = self._delete_children(
            LINUX_TRASH_FILES_DIR,
            dry_run=dry_run,
            allowed_roots=[LINUX_TRASH_FILES_DIR],
        )
        info_outcome = self._delete_children(
            LINUX_TRASH_INFO_DIR,
            dry_run=dry_run,
            allowed_roots=[LINUX_TRASH_INFO_DIR],
        )
        return CleanupResult(
            key="trash",
            dry_run=dry_run,
            success=True,
            message="Processed trash contents.",
            reclaimed_bytes=outcome.reclaimed_bytes + info_outcome.reclaimed_bytes,
            details=outcome.touched + info_outcome.touched,
        )

    def _clean_thumbnails(self, *, dry_run: bool) -> CleanupResult:
        outcome = self._delete_children(
            LINUX_THUMBNAILS_DIR,
            dry_run=dry_run,
            allowed_roots=[LINUX_THUMBNAILS_DIR],
        )
        return CleanupResult(
            key="thumbnails",
            dry_run=dry_run,
            success=True,
            message="Processed thumbnail cache.",
            reclaimed_bytes=outcome.reclaimed_bytes,
            details=outcome.touched,
        )

    def _clean_user_cache(self, *, dry_run: bool) -> CleanupResult:
        reclaimed = 0
        touched: list[str] = []
        skipped = 0
        for path in LINUX_LOW_RISK_USER_CACHE_DIRS:
            outcome = self._delete_children(path, dry_run=dry_run, allowed_roots=[path])
            reclaimed += outcome.reclaimed_bytes
            skipped += outcome.skipped
            touched.extend(outcome.touched)
        message = "Processed low-risk user cache directories."
        if skipped:
            message += f" Skipped {skipped} locked or inaccessible item(s)."
        return CleanupResult(
            key="user-cache",
            dry_run=dry_run,
            success=True,
            message=message,
            reclaimed_bytes=reclaimed,
            details=touched,
        )

    def _clean_journal(self, *, dry_run: bool, vacuum_time: str = "14d") -> CleanupResult:
        return self._run_cleanup_command(
            "journal",
            ["journalctl", f"--vacuum-time={vacuum_time}"],
            dry_run=dry_run,
            preview_message=f"Dry run only. Would run journalctl --vacuum-time={vacuum_time}",
        )

    def _clean_flatpak(self, *, dry_run: bool) -> CleanupResult:
        if not command_exists("flatpak"):
            return CleanupResult(
                key="flatpak-cache",
                dry_run=dry_run,
                success=False,
                message="flatpak not found.",
                command=["flatpak", "uninstall", "--unused"],
            )
        if dry_run:
            preview = get_flatpak_unused_preview()
            return CleanupResult(
                key="flatpak-cache",
                dry_run=True,
                success=True,
                message="Preview only. Nothing has been removed.",
                command=["flatpak", "uninstall", "--unused", "--dry-run"],
                details=preview.splitlines()[:25],
            )
        return self._run_cleanup_command(
            "flatpak-cache",
            ["flatpak", "uninstall", "--unused"],
            dry_run=False,
            preview_message="",
        )

    def doctor_checks(self) -> list[ProviderDoctorCheck]:
        return [
            ProviderDoctorCheck("journalctl found", command_exists("journalctl"), "System journal support."),
            ProviderDoctorCheck("flatpak found", command_exists("flatpak"), "Flatpak cleanup support."),
        ]


def build_linux_generic_categories() -> list[CleanupCategoryDefinition]:
    return [
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
    ]

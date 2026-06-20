from __future__ import annotations

import os
import shutil
from pathlib import Path

from klene.commands import directory_bytes
from klene.models import CleanupResult, CleanupStatus, SupportLevel
from klene.platforms.base import (
    CleanupCategoryDefinition,
    CleanupProvider,
    DeletionOutcome,
    ProviderDoctorCheck,
)
from klene.safety import is_path_within, is_safe_path
from klene.utils import format_display_path


class WindowsProvider(CleanupProvider):
    provider_name = "WindowsProvider"
    platform_id = "windows"
    platform_name = "Windows"
    platform_family = "windows"
    support_level = SupportLevel.BASIC
    support_label = "Safe cleanup support"
    status_message = "Windows safe cleanup support detected."
    safety_notes = [
        "Klene only cleans allowlisted temp, cache, and error-report paths.",
        "Browser data, registry cleanup, driver cleanup, and system component cleanup stay blocked.",
    ]

    def __init__(self) -> None:
        self.user_temp_dir = Path(os.environ.get("TEMP", r"C:\Users\Default\AppData\Local\Temp"))
        self.windows_temp_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Temp"
        local_appdata = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local"))
        program_data = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
        self.thumbnail_dir = local_appdata / "Microsoft" / "Windows" / "Explorer"
        self.local_wer_dir = local_appdata / "Microsoft" / "Windows" / "WER"
        self.programdata_wer_dir = program_data / "Microsoft" / "Windows" / "WER"
        super().__init__()

    def build_category_definitions(self):
        return [
            CleanupCategoryDefinition(
                id="windows-user-temp",
                title="User temp files",
                description="Clean temporary files inside your user temp directory.",
                group="recommended",
                safety_level="recommended",
                what_happens="Klene removes the contents of %TEMP% after confirmation and skips locked files.",
            ),
            CleanupCategoryDefinition(
                id="windows-recycle-bin",
                title="Recycle Bin",
                description="Empty the Windows Recycle Bin.",
                group="review",
                safety_level="review_first",
                what_happens="Klene asks Windows to empty the Recycle Bin after confirmation.",
                default_selected=False,
            ),
            CleanupCategoryDefinition(
                id="windows-temp",
                title="Windows temp files",
                description="Clean files inside C:\\Windows\\Temp.",
                group="review",
                safety_level="review_first",
                what_happens="Klene removes the contents of the Windows temp folder after confirmation and skips locked files.",
                default_selected=False,
                requires_admin=True,
            ),
            CleanupCategoryDefinition(
                id="windows-thumbnails",
                title="Windows thumbnail cache",
                description="Review Windows thumbnail and icon cache files.",
                group="review",
                safety_level="review_first",
                what_happens="Klene removes thumbcache_*.db and iconcache_*.db files when they are not locked.",
                default_selected=False,
            ),
            CleanupCategoryDefinition(
                id="windows-error-reports",
                title="Windows error reports",
                description="Clean Windows Error Reporting cache folders.",
                group="review",
                safety_level="review_first",
                what_happens="Klene removes the contents of allowlisted WER cache folders after confirmation and skips inaccessible files.",
                default_selected=False,
                requires_admin=True,
            ),
        ]

    def scan(self):
        return [
            self._scan_directory_target("windows-user-temp", self.user_temp_dir),
            self._scan_recycle_bin(),
            self._scan_directory_target("windows-temp", self.windows_temp_dir),
            self._scan_thumbnail_cache(),
            self._scan_error_reports(),
        ]

    def _scan_directory_target(self, category_id: str, path: Path):
        size = directory_bytes(path)
        return self._make_target(
            category_id,
            CleanupStatus.CLEAN if size == 0 else CleanupStatus.AVAILABLE,
            estimated_bytes=size,
            details="Klene only removes contents inside the allowlisted directory.",
            available=path.exists(),
            preview=[format_display_path(path)],
            display_paths=[format_display_path(path)],
        )

    def _scan_recycle_bin(self):
        return self._make_target(
            "windows-recycle-bin",
            CleanupStatus.AVAILABLE,
            estimated_bytes=None,
            details="Windows does not provide an exact preview size here. Klene can still ask Windows to empty the Recycle Bin after confirmation.",
            command_preview=["Windows Shell API: SHEmptyRecycleBinW"],
        )

    def _scan_thumbnail_cache(self):
        if not self.thumbnail_dir.exists():
            return self._make_target(
                "windows-thumbnails",
                CleanupStatus.UNAVAILABLE,
                available=False,
                details="Windows Explorer thumbnail cache directory not found.",
                preview=[format_display_path(self.thumbnail_dir)],
                display_paths=[format_display_path(self.thumbnail_dir)],
            )
        files = [path for path in self.thumbnail_dir.glob("thumbcache_*.db")] + [
            path for path in self.thumbnail_dir.glob("iconcache_*.db")
        ]
        size = sum(path.stat().st_size for path in files if path.exists())
        return self._make_target(
            "windows-thumbnails",
            CleanupStatus.CLEAN if not files else CleanupStatus.AVAILABLE,
            estimated_bytes=size,
            details="Only thumbcache_*.db and iconcache_*.db files are included.",
            preview=[format_display_path(path) for path in files[:25]],
            display_paths=[format_display_path(self.thumbnail_dir)],
            count=len(files),
        )

    def _scan_error_reports(self):
        paths = [path for path in [self.local_wer_dir, self.programdata_wer_dir] if path.exists()]
        size = sum(directory_bytes(path) for path in paths)
        return self._make_target(
            "windows-error-reports",
            CleanupStatus.CLEAN if size == 0 else CleanupStatus.AVAILABLE,
            estimated_bytes=size,
            details="Only allowlisted Windows Error Reporting directories are included.",
            available=bool(paths),
            preview=[format_display_path(path) for path in paths],
            display_paths=[format_display_path(path) for path in paths],
        )

    def _delete_windows_children(
        self,
        path: Path,
        *,
        dry_run: bool,
        allowed_roots: list[Path],
        name_prefixes: tuple[str, ...] | None = None,
    ) -> DeletionOutcome:
        if not path.exists():
            return DeletionOutcome(0, 0, [])
        if not is_safe_path(path):
            raise ValueError(f"Refusing unsafe path: {path}")
        if not any(is_path_within(path, root) for root in allowed_roots):
            raise ValueError(f"Refusing non-allowlisted Windows path: {path}")

        reclaimed = 0
        skipped = 0
        touched = [format_display_path(path)]
        for child in path.iterdir():
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

    def _clean_recycle_bin(self, *, dry_run: bool) -> CleanupResult:
        if dry_run:
            return CleanupResult(
                key="windows-recycle-bin",
                dry_run=True,
                success=True,
                message="Dry run only. Windows will empty the Recycle Bin after confirmation.",
                details=["Windows Shell API: SHEmptyRecycleBinW"],
            )
        try:
            import ctypes

            result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x00000001 | 0x00000002 | 0x00000004)
        except Exception as exc:
            return CleanupResult(
                key="windows-recycle-bin",
                dry_run=False,
                success=False,
                message=f"Recycle Bin cleanup failed: {exc}",
            )
        return CleanupResult(
            key="windows-recycle-bin",
            dry_run=False,
            success=result == 0,
            message="Recycle Bin cleanup completed." if result == 0 else f"Windows returned status code {result}.",
        )

    def clean_one(self, category_id: str, *, dry_run: bool = True, **options: object) -> CleanupResult:
        if category_id == "windows-user-temp":
            outcome = self._delete_windows_children(
                self.user_temp_dir,
                dry_run=dry_run,
                allowed_roots=[self.user_temp_dir],
            )
            message = "Processed user temp files."
        elif category_id == "windows-temp":
            outcome = self._delete_windows_children(
                self.windows_temp_dir,
                dry_run=dry_run,
                allowed_roots=[self.windows_temp_dir],
            )
            message = "Processed Windows temp files."
        elif category_id == "windows-thumbnails":
            outcome = self._delete_windows_children(
                self.thumbnail_dir,
                dry_run=dry_run,
                allowed_roots=[self.thumbnail_dir],
                name_prefixes=("thumbcache_", "iconcache_"),
            )
            message = "Processed Windows thumbnail cache files."
        elif category_id == "windows-error-reports":
            reclaimed = 0
            skipped = 0
            touched: list[str] = []
            for root in [self.local_wer_dir, self.programdata_wer_dir]:
                outcome = self._delete_windows_children(root, dry_run=dry_run, allowed_roots=[root])
                reclaimed += outcome.reclaimed_bytes
                skipped += outcome.skipped
                touched.extend(outcome.touched)
            message = "Processed Windows error reporting caches."
            if skipped:
                message += f" Skipped {skipped} locked or inaccessible item(s)."
            return CleanupResult(
                key="windows-error-reports",
                dry_run=dry_run,
                success=True,
                message=message,
                reclaimed_bytes=reclaimed,
                details=touched,
            )
        elif category_id == "windows-recycle-bin":
            return self._clean_recycle_bin(dry_run=dry_run)
        else:
            return super().clean_one(category_id, dry_run=dry_run, **options)

        if outcome.skipped:
            message += f" Skipped {outcome.skipped} locked or inaccessible item(s)."
        return CleanupResult(
            key=category_id,
            dry_run=dry_run,
            success=True,
            message=message,
            reclaimed_bytes=outcome.reclaimed_bytes,
            details=outcome.touched,
        )

    def doctor_checks(self) -> list[ProviderDoctorCheck]:
        return [
            ProviderDoctorCheck("User temp directory", self.user_temp_dir.exists(), str(self.user_temp_dir)),
            ProviderDoctorCheck("Windows temp directory", self.windows_temp_dir.exists(), str(self.windows_temp_dir)),
            ProviderDoctorCheck("Windows Explorer cache directory", self.thumbnail_dir.exists(), str(self.thumbnail_dir)),
            ProviderDoctorCheck("Windows WER directory", self.local_wer_dir.exists() or self.programdata_wer_dir.exists(), "At least one allowlisted WER directory found." if self.local_wer_dir.exists() or self.programdata_wer_dir.exists() else "No allowlisted WER directories found."),
        ]

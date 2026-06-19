from __future__ import annotations

import getpass
from dataclasses import dataclass

from klene.metadata import packaged_logo_path
from klene.safety import command_exists, is_arch_linux
from klene.scanner import (
    AUR_CACHE_DIRS,
    LOW_RISK_USER_CACHE_DIRS,
    PACMAN_CACHE_DIR,
    THUMBNAILS_DIR,
    TRASH_FILES_DIR,
    TRASH_INFO_DIR,
    USER_CACHE_DIR,
)


@dataclass(slots=True)
class DoctorCheck:
    label: str
    ok: bool
    detail: str


def build_doctor_checks() -> list[DoctorCheck]:
    checks: list[DoctorCheck] = [
        DoctorCheck("Arch Linux detected", is_arch_linux(), "/etc/arch-release present" if is_arch_linux() else "This system does not look like Arch Linux."),
        DoctorCheck("pacman found", command_exists("pacman"), "Package manager available." if command_exists("pacman") else "pacman is not in PATH."),
        DoctorCheck("paccache found", command_exists("paccache"), "pacman-contrib is ready." if command_exists("paccache") else "Install pacman-contrib to enable safer cache trimming."),
        DoctorCheck("journalctl found", command_exists("journalctl"), "Journal cleanup is available." if command_exists("journalctl") else "journalctl is not in PATH."),
        DoctorCheck("yay found", command_exists("yay"), "yay cache can be reviewed." if command_exists("yay") else "yay is not installed."),
        DoctorCheck("paru found", command_exists("paru"), "paru cache can be reviewed." if command_exists("paru") else "paru is not installed."),
        DoctorCheck("flatpak found", command_exists("flatpak"), "Flatpak cleanup checks are available." if command_exists("flatpak") else "flatpak is not installed."),
        DoctorCheck("Packaged logo exists", packaged_logo_path().exists(), str(packaged_logo_path())),
    ]

    try:
        import PySide6  # noqa: F401
    except Exception as exc:  # pragma: no cover
        checks.append(DoctorCheck("GUI dependencies importable", False, str(exc)))
    else:
        checks.append(DoctorCheck("GUI dependencies importable", True, "PySide6 imports successfully."))

    path_checks = [
        ("User cache directory", USER_CACHE_DIR.exists(), str(USER_CACHE_DIR)),
        ("Pacman cache directory", PACMAN_CACHE_DIR.exists(), str(PACMAN_CACHE_DIR)),
        ("Trash files directory", TRASH_FILES_DIR.exists(), str(TRASH_FILES_DIR)),
        ("Trash info directory", TRASH_INFO_DIR.exists(), str(TRASH_INFO_DIR)),
        ("Thumbnail cache directory", THUMBNAILS_DIR.exists(), str(THUMBNAILS_DIR)),
    ]
    path_checks.extend((f"Low-risk cache path: {path.name}", path.exists(), str(path)) for path in LOW_RISK_USER_CACHE_DIRS)
    path_checks.extend((f"AUR cache path: {path.name}", path.exists(), str(path)) for path in AUR_CACHE_DIRS)

    checks.append(DoctorCheck("Current user", True, getpass.getuser()))
    checks.extend(DoctorCheck(label, ok, detail) for label, ok, detail in path_checks)
    return checks

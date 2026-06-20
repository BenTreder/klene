from __future__ import annotations

import shutil
import subprocess
from pathlib import Path, PureWindowsPath
import re


PROTECTED_EXACT_PATHS = {
    Path("/"),
    Path("/home"),
}

PROTECTED_RECURSIVE_PATHS = {
    Path("/usr"),
    Path("/etc"),
    Path("/var"),
    Path("/var/cache"),
}

PROTECTED_HOME_EXACT_PATHS = {
    Path.home(),
    Path.home() / ".config",
    Path.home() / ".ssh",
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "Pictures",
    Path.home() / "Videos",
}

WINDOWS_PROTECTED_PATHS = {
    PureWindowsPath("C:/"),
    PureWindowsPath("C:/Windows"),
    PureWindowsPath("C:/Users"),
    PureWindowsPath("C:/Program Files"),
    PureWindowsPath("C:/Program Files (x86)"),
    PureWindowsPath("C:/ProgramData"),
}


def is_arch_linux() -> bool:
    return Path("/etc/arch-release").exists()


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _looks_like_windows_path(raw: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", raw))


def is_path_within(path: Path, root: Path) -> bool:
    try:
        resolved_path = path.resolve(strict=False)
        resolved_root = root.resolve(strict=False)
    except OSError:
        return False
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def is_safe_windows_path(path: str | Path) -> bool:
    raw = str(path).replace("\\", "/")
    candidate = PureWindowsPath(raw)
    if candidate in WINDOWS_PROTECTED_PATHS:
        return False
    parts = candidate.parts
    if len(parts) == 3 and len(parts[0]) == 3 and parts[1].lower() == "users":
        return False
    if len(parts) <= 5 and parts[1].lower() == "users" and parts[3].lower() == "appdata":
        return False
    return True


def is_safe_path(path: Path) -> bool:
    expanded = path.expanduser()
    if _looks_like_windows_path(str(expanded)):
        return is_safe_windows_path(expanded)
    try:
        resolved = expanded.resolve(strict=False)
    except OSError:
        return False

    if resolved in PROTECTED_EXACT_PATHS | PROTECTED_HOME_EXACT_PATHS:
        return False
    for root in PROTECTED_RECURSIVE_PATHS:
        if resolved == root or root in resolved.parents:
            return False
    return True


def require_confirmation(message: str, *, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    answer = input(f"{message} [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def safe_run_command(command: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=check,
    )

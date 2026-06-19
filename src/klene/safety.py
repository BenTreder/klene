from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


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


def is_arch_linux() -> bool:
    return Path("/etc/arch-release").exists()


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def is_safe_path(path: Path) -> bool:
    expanded = path.expanduser()
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

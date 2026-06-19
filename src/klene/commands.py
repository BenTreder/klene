from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from klene.safety import command_exists, safe_run_command
from klene.utils import dir_size


@dataclass(slots=True)
class CommandOutcome:
    ok: bool
    stdout: str
    stderr: str
    returncode: int


def run_optional_command(command: list[str]) -> CommandOutcome:
    if not command_exists(command[0]):
        return CommandOutcome(False, "", f"{command[0]} is not installed", 127)
    result = safe_run_command(command)
    return CommandOutcome(
        ok=result.returncode == 0,
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
        returncode=result.returncode,
    )


def get_orphan_packages() -> list[str]:
    outcome = run_optional_command(["pacman", "-Qdtq"])
    if not outcome.ok and outcome.returncode not in {0, 1}:
        return []
    return [line.strip() for line in outcome.stdout.splitlines() if line.strip()]


def get_journal_disk_usage() -> str:
    outcome = run_optional_command(["journalctl", "--disk-usage"])
    if not outcome.ok:
        return outcome.stderr or "journalctl unavailable"
    return outcome.stdout


def get_flatpak_unused_preview() -> str:
    help_outcome = run_optional_command(["flatpak", "uninstall", "--help"])
    if "--dry-run" not in help_outcome.stdout:
        return "Flatpak is installed, but this version does not support dry-run preview for unused cleanup."
    outcome = run_optional_command(["flatpak", "uninstall", "--unused", "--dry-run"])
    if not outcome.ok:
        return outcome.stderr or "Flatpak preview unavailable"
    return outcome.stdout


def directory_bytes(path: Path) -> int:
    return dir_size(path)

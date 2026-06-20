from __future__ import annotations

import platform
import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DetectedPlatform:
    provider_id: str
    platform_id: str
    platform_name: str
    platform_family: str
    system_name: str
    raw_id: str = ""
    raw_like: tuple[str, ...] = ()


def parse_os_release_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parts = shlex.split(value) if value else []
        values[key] = " ".join(parts) if parts else value.strip().strip('"')
    return values


def load_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    try:
        return parse_os_release_text(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def detect_platform(
    *,
    system_name: str | None = None,
    os_release: dict[str, str] | None = None,
) -> DetectedPlatform:
    resolved_system = (system_name or platform.system()).strip()
    if resolved_system == "Windows":
        return DetectedPlatform(
            provider_id="windows",
            platform_id="windows",
            platform_name="Windows",
            platform_family="windows",
            system_name="Windows",
        )

    if resolved_system != "Linux":
        return DetectedPlatform(
            provider_id="generic_linux",
            platform_id=resolved_system.lower() or "unknown",
            platform_name=resolved_system or "Unknown",
            platform_family="linux",
            system_name=resolved_system or "Unknown",
        )

    release = os_release if os_release is not None else load_os_release()
    platform_id = release.get("ID", "").strip().lower()
    platform_name = release.get("PRETTY_NAME", "").strip() or release.get("NAME", "").strip() or "Linux"
    like_values = tuple(value.strip().lower() for value in release.get("ID_LIKE", "").split() if value.strip())
    tokens = {platform_id, *like_values}

    if platform_id in {"arch", "endeavouros", "manjaro", "garuda"} or "arch" in tokens:
        return DetectedPlatform("arch", platform_id or "arch", platform_name, "linux", "Linux", platform_id, like_values)
    if platform_id in {"debian", "ubuntu", "linuxmint", "pop", "elementary", "zorin"} or tokens & {"debian", "ubuntu"}:
        return DetectedPlatform("debian", platform_id or "debian", platform_name, "linux", "Linux", platform_id, like_values)
    if platform_id in {"fedora", "nobara"} or ((platform_id in {"rhel", "centos"} or tokens & {"fedora", "rhel"}) and Path("/usr/bin/dnf").exists()):
        return DetectedPlatform("fedora", platform_id or "fedora", platform_name, "linux", "Linux", platform_id, like_values)
    if platform_id in {"opensuse", "opensuse-tumbleweed", "opensuse-leap"} or (
        platform_id == "sles" and Path("/usr/bin/zypper").exists()
    ):
        return DetectedPlatform("opensuse", platform_id or "opensuse", platform_name, "linux", "Linux", platform_id, like_values)
    return DetectedPlatform("generic_linux", platform_id or "linux", platform_name, "linux", "Linux", platform_id, like_values)

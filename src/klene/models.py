from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class CleanupStatus(str, Enum):
    AVAILABLE = "available"
    CLEAN = "clean"
    UNAVAILABLE = "unavailable"
    WARNING = "warning"


class SupportLevel(str, Enum):
    FULL = "full"
    PREVIEW = "preview"
    BASIC = "basic"
    EXPERIMENTAL = "experimental"
    UNSUPPORTED = "unsupported"


@dataclass(slots=True)
class CleanupTarget:
    key: str
    title: str
    description: str
    status: CleanupStatus
    estimated_bytes: int | None = None
    details: str = ""
    count: int | None = None
    available: bool = True
    selected_by_default: bool = True
    preview: list[str] = field(default_factory=list)
    cleanup_supported: bool = True
    group: str = "recommended"
    safety_level: str = "recommended"
    what_happens: str = ""
    command_preview: list[str] = field(default_factory=list)
    requires_admin: bool = False
    requires_extra_confirmation: bool = False
    display_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(slots=True)
class PlatformInfo:
    platform_id: str
    platform_name: str
    platform_family: str
    is_supported: bool
    support_level: SupportLevel
    provider_name: str
    support_label: str
    status_message: str
    safety_notes: list[str] = field(default_factory=list)
    available_cleanup_areas: list[str] = field(default_factory=list)
    unavailable_cleanup_areas: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["support_level"] = self.support_level.value
        return payload


@dataclass(slots=True)
class ScanReport:
    arch_linux: bool
    generated_at: str
    targets: list[CleanupTarget]
    platform: PlatformInfo | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "arch_linux": self.arch_linux,
            "generated_at": self.generated_at,
            "notes": self.notes,
            "targets": [target.to_dict() for target in self.targets],
        }
        if self.platform is not None:
            payload["platform"] = self.platform.to_dict()
        return payload


@dataclass(slots=True)
class CleanupResult:
    key: str
    dry_run: bool
    success: bool
    message: str
    reclaimed_bytes: int | None = None
    command: list[str] | None = None
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

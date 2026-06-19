from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class CleanupStatus(str, Enum):
    AVAILABLE = "available"
    CLEAN = "clean"
    UNAVAILABLE = "unavailable"
    WARNING = "warning"


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

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(slots=True)
class ScanReport:
    arch_linux: bool
    generated_at: str
    targets: list[CleanupTarget]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arch_linux": self.arch_linux,
            "generated_at": self.generated_at,
            "notes": self.notes,
            "targets": [target.to_dict() for target in self.targets],
        }


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

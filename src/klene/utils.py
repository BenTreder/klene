from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def format_bytes(num_bytes: int | None) -> str:
    if num_bytes is None:
        return "Unknown"
    if num_bytes < 0:
        raise ValueError("Byte size cannot be negative")
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"


def dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_pretty_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)

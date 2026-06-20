from pathlib import Path

from klene.utils import format_bytes, format_display_path, shorten_home_paths


def test_format_bytes_none() -> None:
    assert format_bytes(None) == "Unknown"


def test_format_bytes_binary_units() -> None:
    assert format_bytes(1024) == "1.0 KiB"


def test_format_display_path_shortens_home() -> None:
    assert format_display_path(Path.home() / ".cache" / "thumbnails") == "~/.cache/thumbnails"


def test_shorten_home_paths_rewrites_embedded_paths() -> None:
    text = f"Path: {Path.home()}/.cache/thumbnails"
    assert shorten_home_paths(text) == "Path: ~/.cache/thumbnails"

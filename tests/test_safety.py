from pathlib import Path

from klene.safety import is_safe_path


def test_safe_path_allows_thumbnail_dir() -> None:
    assert is_safe_path(Path.home() / ".cache" / "thumbnails") is True


def test_safe_path_blocks_home_root() -> None:
    assert is_safe_path(Path.home()) is False


def test_safe_path_blocks_documents() -> None:
    assert is_safe_path(Path.home() / "Documents") is False

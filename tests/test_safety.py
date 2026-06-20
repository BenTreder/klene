from pathlib import Path

from klene.safety import is_safe_path


def test_safe_path_allows_thumbnail_dir() -> None:
    assert is_safe_path(Path.home() / ".cache" / "thumbnails") is True


def test_safe_path_blocks_home_root() -> None:
    assert is_safe_path(Path.home()) is False


def test_safe_path_blocks_documents() -> None:
    assert is_safe_path(Path.home() / "Documents") is False


def test_safe_path_blocks_windows_root() -> None:
    assert is_safe_path(Path(r"C:\Windows")) is False


def test_safe_path_blocks_windows_user_root() -> None:
    assert is_safe_path(Path(r"C:\Users\Ben")) is False


def test_safe_path_allows_windows_temp_subdirectory() -> None:
    assert is_safe_path(Path(r"C:\Users\Ben\AppData\Local\Temp\cache")) is True

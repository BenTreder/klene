from klene.utils import format_bytes


def test_format_bytes_none() -> None:
    assert format_bytes(None) == "Unknown"


def test_format_bytes_binary_units() -> None:
    assert format_bytes(1024) == "1.0 KiB"

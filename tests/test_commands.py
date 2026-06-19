from klene.commands import CommandOutcome
from klene.safety import is_safe_path
from pathlib import Path


def test_command_outcome_fields() -> None:
    outcome = CommandOutcome(ok=True, stdout="a", stderr="", returncode=0)
    assert outcome.ok is True
    assert outcome.stdout == "a"


def test_safe_path_allows_cache_subdir() -> None:
    assert is_safe_path(Path.home() / ".cache" / "yay") is True

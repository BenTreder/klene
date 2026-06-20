from klene import APP_NAME, APP_TAGLINE, __version__
from klene.metadata import packaged_logo_path


def test_metadata_values_exist() -> None:
    assert APP_NAME == "Klene"
    assert APP_TAGLINE == "Safe cleanup with previews first."
    assert __version__ == "0.2.0"


def test_packaged_logo_exists() -> None:
    assert packaged_logo_path().exists() is True

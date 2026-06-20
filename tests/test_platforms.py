from typer.testing import CliRunner

from klene.cli import app
from klene.platforms import get_provider
from klene.platforms.detect import detect_platform, parse_os_release_text
from klene.scanner import scan_system

runner = CliRunner()


def test_parse_arch_os_release() -> None:
    release = parse_os_release_text('ID=arch\nPRETTY_NAME="Arch Linux"\nID_LIKE=arch')
    detected = detect_platform(system_name="Linux", os_release=release)
    assert detected.provider_id == "arch"


def test_parse_arch_like_os_release() -> None:
    release = parse_os_release_text('ID=manjaro\nPRETTY_NAME="Manjaro Linux"\nID_LIKE="arch"')
    detected = detect_platform(system_name="Linux", os_release=release)
    assert detected.provider_id == "arch"


def test_parse_debian_like_os_release() -> None:
    release = parse_os_release_text('ID=ubuntu\nPRETTY_NAME="Ubuntu 24.04"\nID_LIKE="debian"')
    detected = detect_platform(system_name="Linux", os_release=release)
    assert detected.provider_id == "debian"


def test_parse_linuxmint_os_release() -> None:
    release = parse_os_release_text('ID=linuxmint\nPRETTY_NAME="Linux Mint"\nID_LIKE="ubuntu debian"')
    detected = detect_platform(system_name="Linux", os_release=release)
    assert detected.provider_id == "debian"


def test_parse_fedora_os_release() -> None:
    release = parse_os_release_text('ID=fedora\nPRETTY_NAME=Fedora')
    detected = detect_platform(system_name="Linux", os_release=release)
    assert detected.provider_id == "fedora"


def test_parse_opensuse_os_release() -> None:
    release = parse_os_release_text('ID=opensuse-tumbleweed\nPRETTY_NAME="openSUSE Tumbleweed"')
    detected = detect_platform(system_name="Linux", os_release=release)
    assert detected.provider_id == "opensuse"


def test_parse_generic_linux_os_release() -> None:
    release = parse_os_release_text('ID=gentoo\nPRETTY_NAME=Gentoo')
    detected = detect_platform(system_name="Linux", os_release=release)
    assert detected.provider_id == "generic_linux"


def test_detect_windows() -> None:
    detected = detect_platform(system_name="Windows")
    assert detected.provider_id == "windows"


def test_provider_selection_for_arch() -> None:
    provider = get_provider(detect_platform(system_name="Linux", os_release={"ID": "arch", "PRETTY_NAME": "Arch Linux"}))
    assert provider.provider_name == "ArchProvider"
    assert any(category.id == "pacman-cache" for category in provider.get_category_definitions())


def test_provider_selection_for_debian() -> None:
    provider = get_provider(detect_platform(system_name="Linux", os_release={"ID": "ubuntu", "PRETTY_NAME": "Ubuntu", "ID_LIKE": "debian"}))
    assert provider.provider_name == "DebianProvider"
    assert any(category.id == "apt-cache" for category in provider.get_category_definitions())


def test_provider_selection_for_fedora() -> None:
    provider = get_provider(detect_platform(system_name="Linux", os_release={"ID": "fedora", "PRETTY_NAME": "Fedora"}))
    assert provider.provider_name == "FedoraProvider"
    assert any(category.id == "dnf-cache" for category in provider.get_category_definitions())


def test_provider_selection_for_opensuse() -> None:
    provider = get_provider(detect_platform(system_name="Linux", os_release={"ID": "opensuse", "PRETTY_NAME": "openSUSE"}))
    assert provider.provider_name == "OpenSUSEProvider"
    assert any(category.id == "zypper-cache" for category in provider.get_category_definitions())


def test_provider_selection_for_generic_linux() -> None:
    provider = get_provider(detect_platform(system_name="Linux", os_release={"ID": "gentoo", "PRETTY_NAME": "Gentoo"}))
    assert provider.provider_name == "GenericLinuxProvider"
    assert any(category.id == "trash" for category in provider.get_category_definitions())


def test_provider_selection_for_windows() -> None:
    provider = get_provider(detect_platform(system_name="Windows"))
    assert provider.provider_name == "WindowsProvider"
    assert any(category.id == "windows-user-temp" for category in provider.get_category_definitions())


def test_cli_platform_command_works() -> None:
    result = runner.invoke(app, ["platform"])
    assert result.exit_code == 0
    assert "Provider:" in result.output


def test_scan_json_includes_platform_info() -> None:
    report = scan_system().to_dict()
    assert "platform" in report
    assert "provider_name" in report["platform"]

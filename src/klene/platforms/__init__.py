from __future__ import annotations

from klene.platforms.arch import ArchProvider
from klene.platforms.debian import DebianProvider
from klene.platforms.detect import DetectedPlatform, detect_platform
from klene.platforms.fedora import FedoraProvider
from klene.platforms.generic_linux import GenericLinuxProvider
from klene.platforms.opensuse import OpenSUSEProvider
from klene.platforms.windows import WindowsProvider


def get_provider(detected: DetectedPlatform | None = None):
    resolved = detected or detect_platform()
    if resolved.provider_id == "arch":
        return ArchProvider()
    if resolved.provider_id == "debian":
        provider = DebianProvider()
        provider.platform_name = resolved.platform_name
        return provider
    if resolved.provider_id == "fedora":
        provider = FedoraProvider()
        provider.platform_name = resolved.platform_name
        return provider
    if resolved.provider_id == "opensuse":
        provider = OpenSUSEProvider()
        provider.platform_name = resolved.platform_name
        return provider
    if resolved.provider_id == "windows":
        return WindowsProvider()
    provider = GenericLinuxProvider()
    provider.platform_name = resolved.platform_name
    return provider


__all__ = ["DetectedPlatform", "detect_platform", "get_provider"]

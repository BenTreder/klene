from __future__ import annotations

import getpass
from dataclasses import dataclass

from klene.metadata import packaged_logo_path
from klene.platforms import get_provider


@dataclass(slots=True)
class DoctorCheck:
    label: str
    ok: bool
    detail: str


def build_doctor_checks() -> list[DoctorCheck]:
    provider = get_provider()
    platform_info = provider.get_platform_info()
    checks: list[DoctorCheck] = [
        DoctorCheck("Detected platform", platform_info.is_supported, platform_info.platform_name),
        DoctorCheck("Selected provider", True, platform_info.provider_name),
        DoctorCheck("Support level", True, platform_info.support_label),
        DoctorCheck("Packaged logo exists", packaged_logo_path().exists(), str(packaged_logo_path())),
    ]

    try:
        import PySide6  # noqa: F401
    except Exception as exc:  # pragma: no cover
        checks.append(DoctorCheck("GUI dependencies importable", False, str(exc)))
    else:
        checks.append(DoctorCheck("GUI dependencies importable", True, "PySide6 imports successfully."))

    checks.append(DoctorCheck("Current user", True, getpass.getuser()))
    checks.extend(DoctorCheck(check.label, check.ok, check.detail) for check in provider.doctor_checks())
    return checks

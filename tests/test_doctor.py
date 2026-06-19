from klene.doctor import build_doctor_checks


def test_doctor_checks_include_current_user_and_logo() -> None:
    checks = build_doctor_checks()
    labels = {check.label for check in checks}
    assert "Current user" in labels
    assert "Packaged logo exists" in labels


def test_doctor_checks_have_boolean_status() -> None:
    checks = build_doctor_checks()
    assert all(isinstance(check.ok, bool) for check in checks)

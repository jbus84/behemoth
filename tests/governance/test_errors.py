from src.behemoth.governance import errors


def test_missing_governance_field_error_message():
    e = errors.MissingGovernanceFieldError(
        symbol="EURUSD", family="directional_run", field="capacity_floor_monthly"
    )
    msg = str(e)
    assert "EURUSD" in msg
    assert "directional_run" in msg
    assert "capacity_floor_monthly" in msg


def test_unknown_family_error_message():
    e = errors.UnknownFamilyError(family="not_a_real_family")
    assert "not_a_real_family" in str(e)


def test_invalid_model_month_error_message():
    e = errors.InvalidModelMonthError(value="2026/05")
    assert "2026/05" in str(e)


def test_required_family_missing_thresholds_error_message():
    e = errors.RequiredFamilyMissingThresholdsError(
        symbol="EURUSD", family="directional_run"
    )
    assert "EURUSD" in str(e) and "directional_run" in str(e)

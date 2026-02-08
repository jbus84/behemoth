import wfo_mom_full_params as wfo_m15
import wfo_mom_full_params_m5 as wfo_m5


def test_wfo_defaults_match_strategy():
    # Ensure WFO parameter grids include production defaults
    assert 1.5 in wfo_m15.Z_ENTRIES
    assert 4.0 in wfo_m15.Z_STOPS
    assert 750 in wfo_m15.Z_LOOKBACKS
    assert 3 in wfo_m15.LOSS_STREAKS
    assert 7 in wfo_m15.COOLDOWN_DAYS

    assert 1.5 in wfo_m5.Z_ENTRIES
    assert 4.0 in wfo_m5.Z_STOPS
    assert 750 in wfo_m5.Z_LOOKBACKS
    assert 3 in wfo_m5.LOSS_STREAKS
    assert 7 in wfo_m5.COOLDOWN_DAYS

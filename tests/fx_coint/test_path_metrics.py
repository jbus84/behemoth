import numpy as np

from scripts.fx_coint.path_metrics import path_excursions


def test_long_excursions():
    entry = 1.0
    # path goes up to +20bps then down to -10bps, ends +5bps (approx via small moves)
    mins = entry * np.exp(np.array([0.0010, 0.0020, -0.0010, 0.0005]))  # cumulative? no: levels
    # build explicit levels: +10, +20, -10, +5 bps from entry
    mins = entry * np.exp(np.array([10, 20, -10, 5]) / 1e4)
    r = path_excursions(entry, mins, "long", sigma_bps=10.0)
    assert np.isclose(r["terminal_bps"], 5.0, atol=1e-6)
    assert np.isclose(r["mfe_sigma"], 2.0, atol=1e-6)   # +20bps / 10
    assert np.isclose(r["mae_sigma"], -1.0, atol=1e-6)  # -10bps / 10
    assert r["n_steps"] == 4


def test_short_flips_sign():
    entry = 1.0
    mins = entry * np.exp(np.array([10, -20, 5]) / 1e4)  # raw +10,-20,+5
    r = path_excursions(entry, mins, "short", sigma_bps=10.0)
    # short: signed = -raw -> -10,+20,-5 ; mfe=+20bps/10=2, mae=-10bps/10=-1, terminal=-5
    assert np.isclose(r["terminal_bps"], -5.0, atol=1e-6)
    assert np.isclose(r["mfe_sigma"], 2.0, atol=1e-6)
    assert np.isclose(r["mae_sigma"], -1.0, atol=1e-6)


def test_empty():
    r = path_excursions(1.0, np.empty(0), "long", 10.0)
    assert r["n_steps"] == 0 and np.isnan(r["terminal_bps"])

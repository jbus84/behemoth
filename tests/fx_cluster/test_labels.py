import numpy as np

from scripts.fx_cluster.labels import barrier_outcome


def test_long_target_hit_before_stop():
    # flat then a jump up that crosses +target at bar 2.
    mid = np.array([100.0, 100.0, 100.0, 100.0])
    hi = np.array([100.0, 100.05, 102.0, 100.0])
    lo = np.array([100.0, 99.95, 100.0, 100.0])
    out = barrier_outcome(mid, hi, lo, i=0, target=1.0, patience=3, side=+1)
    assert out["exit_reason"] == "target"
    assert out["hold_bars"] == 2
    assert out["mfe"] >= 1.0          # reached at least +target
    assert out["gross"] > 0


def test_long_stop_hit():
    mid = np.array([100.0, 100.0, 100.0])
    hi = np.array([100.0, 100.1, 100.1])
    lo = np.array([100.0, 98.0, 100.0])   # crosses -target at bar 1
    out = barrier_outcome(mid, hi, lo, i=0, target=1.0, patience=2, side=+1)
    assert out["exit_reason"] == "stop"
    assert out["gross"] < 0


def test_patience_timeout_exits_at_last_close():
    mid = np.array([100.0, 100.2, 100.3, 100.25])
    hi = mid.copy()
    lo = mid.copy()
    out = barrier_outcome(mid, hi, lo, i=0, target=5.0, patience=3, side=+1)
    assert out["exit_reason"] == "timeout"
    assert out["hold_bars"] == 3
    assert np.isclose(out["gross"], 100.25 - 100.0)


def test_same_bar_ambiguity_is_conservative_stop_first():
    # bar 1 touches BOTH +target and -target -> must resolve as stop.
    mid = np.array([100.0, 100.0])
    hi = np.array([100.0, 102.0])
    lo = np.array([100.0, 98.0])
    out = barrier_outcome(mid, hi, lo, i=0, target=1.0, patience=1, side=+1)
    assert out["exit_reason"] == "stop"


def test_short_side_mirrors_long():
    mid = np.array([100.0, 100.0, 100.0])
    hi = np.array([100.0, 100.1, 100.1])
    lo = np.array([100.0, 99.95, 98.0])   # price falls -> good for a short
    out = barrier_outcome(mid, hi, lo, i=0, target=1.0, patience=2, side=-1)
    assert out["exit_reason"] == "target"
    assert out["gross"] > 0               # short profits from the fall

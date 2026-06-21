import numpy as np

from scripts.fx_coint.path_bracket import evaluate_bracket


def _levels(entry, bps_list):
    return entry * np.exp(np.array(bps_list) / 1e4)

def test_stop_triggers_first():
    entry = 1.0
    mins = _levels(entry, [5, -25, 40])     # long: hits -25 at i=1 before +40
    net = evaluate_bracket(entry, mins, "long", sigma_bps=10.0,
                           stop_sigma=2.0, tp_sigma=3.0, cost_bps=0.6)
    # stop at -2*10 = -20bps; signed -25 at i=1 -> exit -25 - 0.6
    assert np.isclose(net, -25.0 - 0.6, atol=1e-6)

def test_tp_triggers():
    entry = 1.0
    mins = _levels(entry, [10, 35, -50])    # +35 hits tp 3*10=30 at i=1
    net = evaluate_bracket(entry, mins, "long", 10.0, stop_sigma=2.0, tp_sigma=3.0, cost_bps=0.6)
    assert np.isclose(net, 35.0 - 0.6, atol=1e-6)

def test_no_trigger_exits_last():
    entry = 1.0
    mins = _levels(entry, [5, -5, 8])
    net = evaluate_bracket(entry, mins, "long", 10.0, stop_sigma=2.0, tp_sigma=3.0, cost_bps=0.6)
    assert np.isclose(net, 8.0 - 0.6, atol=1e-6)

def test_straddle_resolves_stop_first():
    entry = 1.0
    mins = _levels(entry, [-30, 0])          # one minute already past both stop(-20) & tp(+...)? only stop
    net = evaluate_bracket(entry, mins, "long", 10.0, stop_sigma=2.0, tp_sigma=2.0, cost_bps=0.0)
    assert np.isclose(net, -30.0, atol=1e-6)

def test_short_side_and_disabled_legs():
    entry = 1.0
    mins = _levels(entry, [-10, -40])        # short: signed = +10, +40 -> tp 3*10=30 hit at i=1
    net = evaluate_bracket(entry, mins, "short", 10.0, stop_sigma=None, tp_sigma=3.0, cost_bps=0.0)
    assert np.isclose(net, 40.0, atol=1e-6)

def test_empty_is_nan():
    assert np.isnan(evaluate_bracket(1.0, np.empty(0), "long", 10.0, 2.0, 3.0, 0.6))

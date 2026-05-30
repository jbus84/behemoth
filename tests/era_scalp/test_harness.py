import numpy as np

from scripts.era_scalp.harness import entry_diagnostics, evaluate_signal, scale_signal, task_score


def test_scale_signal_mad():
    s = scale_signal(np.array([0.0, 1.0, -1.0, 2.0, -2.0]))
    assert np.all(np.isfinite(s))
    # zero-variation -> all nan
    assert np.all(np.isnan(scale_signal(np.full(5, 3.0))))


def test_evaluate_signal_directional():
    signal = np.concatenate([np.full(50, 3.0), np.full(50, -3.0)])
    y_fwd = np.concatenate([np.full(50, 2.0), np.full(50, -2.0)])
    cost = np.full(100, 0.4)
    tm = np.array(["2025-01"] * 50 + ["2025-02"] * 50)
    df = evaluate_signal(signal, y_fwd, cost, tm, threshold=0.5)
    assert len(df) == 100
    # long when signal>0 & y_fwd>0 => +2-0.4 ; short when signal<0 & y_fwd<0 => +2-0.4
    assert np.allclose(df["net"].to_numpy(), 1.6)


def test_entry_diagnostics_hit_rate():
    signal = np.array([3.0, 3.0, -3.0, -3.0])
    y_fwd = np.array([2.0, -2.0, -2.0, 2.0])  # 2 correct, 2 wrong
    cost = np.full(4, 0.4)
    tm = np.array(["2025-01"] * 4)
    d = entry_diagnostics(signal, y_fwd, cost, tm, threshold=0.5)
    assert d["n_entries"] == 4
    assert abs(d["hit_rate"] - 0.5) < 1e-9


def test_task_score_reused():
    import pandas as pd

    df = pd.DataFrame({"net": np.full(200, 0.5), "test_month": ["2025-01"] * 200})
    assert task_score(df) > 0

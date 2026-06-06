import numpy as np
import pandas as pd

import scripts.era_scalp.basket_panel as bp
from scripts.cross_symbol import CROSS_SYMBOLS


def _fake_frame(symbol, horizon, n=12):
    ts = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    df = pd.DataFrame({"close_ts": ts})
    _sym_idx = next(i for i, s in enumerate(CROSS_SYMBOLS) if s.upper() == symbol.upper())
    df["ret_z"] = np.linspace(-1, 1, n) + _sym_idx
    for s in CROSS_SYMBOLS:
        df[f"xs_ret_z__{s}"] = np.linspace(-1, 1, n) + CROSS_SYMBOLS.index(s)
    df[f"y_fwd_pips_h{horizon}"] = np.full(n, float(_sym_idx))
    df["cost_est_pips"] = np.full(n, 0.3)
    df["hour_utc"] = df["close_ts"].dt.hour
    return df


def test_panel_shapes_and_per_symbol_yfwd(monkeypatch):
    monkeypatch.setattr(
        bp, "get_or_build_cross_symbol_frame",
        lambda symbol, bar_ticks, velocity_dir, horizons: _fake_frame(symbol, horizons[0]),
    )
    splits = bp.build_basket_panel(
        bar_ticks=100, velocity_dir="/tmp/unused", horizon=3,
        train=("2025-01",), validation=("2025-01",), holdout=("2025-01",),
    )
    tr = splits["train"]
    m = len(CROSS_SYMBOLS)
    assert tr.r.shape[1] == m
    assert tr.y_fwd_panel.shape == tr.r.shape == tr.cost_panel.shape
    # each column's y_fwd equals that symbol's constant (index), proving per-symbol placement
    for j, s in enumerate(tr.names):
        col = tr.y_fwd_panel[:, j]
        assert np.allclose(col[np.isfinite(col)], float(CROSS_SYMBOLS.index(s)))
    assert tr.names == list(CROSS_SYMBOLS)

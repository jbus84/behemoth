from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import polars as pl

from scripts.fx_coint.reg_signal_hunt import build_freq_bars, build_panel
from scripts.fx_coint.tail_wfo import walk_forward


def _synthetic_1m(start, n, seed=0):
    ts = [start + timedelta(minutes=i) for i in range(n)]
    rng = np.random.default_rng(seed)
    steps = 1e-5 + rng.normal(0.0, 5e-5, n)
    mid = 1.10 + np.cumsum(steps)
    return pl.DataFrame({
        "bucket": ts, "mid": mid, "bid": mid - 5e-5, "ask": mid + 5e-5,
        "n_ticks": np.ones(n, dtype=np.int64), "flow_tick": np.zeros(n), "flow_ofi": np.zeros(n),
    })


def test_walk_forward_folds_expanding_and_oos():
    df = _synthetic_1m(datetime(2025, 1, 6, 7, 0), 1500 * 60)
    panel = build_panel(build_freq_bars(df, "2h", session=(0, 24)))
    folds = walk_forward(panel, n_folds=4, min_train_frac=0.5)
    assert len(folds) == 4
    # train grows across folds; every fold has non-empty test arrays of equal length
    prev_train = 0
    for f in folds:
        assert len(f["train_pred"]) > prev_train
        prev_train = len(f["train_pred"])
        assert len(f["test_pred"]) == len(f["test_actual_bps"]) == len(f["test_hour"]) > 0

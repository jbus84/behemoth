from __future__ import annotations

import pandas as pd

from scripts.meta_kf_directional_wfo import _mark_actionable, _train_quantile_threshold


def test_train_quantile_threshold_is_train_only() -> None:
    train = pd.DataFrame({"kf_z_accel": [1.0, 2.0, 3.0, 4.0, 5.0]})
    test = pd.DataFrame({"kf_z_accel": [0.5, 4.3, 100.0]})

    thr = _train_quantile_threshold(train, col="kf_z_accel", q=0.80)
    flags = _mark_actionable(test, col="kf_z_accel", threshold=thr)

    assert abs(thr - 4.2) < 1e-9
    assert flags.tolist() == [False, True, True]


def test_train_quantile_threshold_empty_train_defaults_zero() -> None:
    train = pd.DataFrame({"kf_z_accel": []})
    test = pd.DataFrame({"kf_z_accel": [0.0, 0.1]})

    thr = _train_quantile_threshold(train, col="kf_z_accel", q=0.80)
    flags = _mark_actionable(test, col="kf_z_accel", threshold=thr)

    assert thr == 0.0
    assert flags.tolist() == [True, True]

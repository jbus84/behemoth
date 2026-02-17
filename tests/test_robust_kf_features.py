from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.lib.robust_kf_features import add_robust_kf_features


def test_add_robust_kf_features_populates_expected_columns() -> None:
    ts = pd.date_range("2025-01-01", periods=8, freq="15min", tz="UTC").view("int64")
    state_cache = {
        "m15": {
            "EURUSD_GBPUSD": {
                "z": np.asarray([0.0, 0.2, -0.1, 0.4, 0.35, -0.2, 0.1, 0.05], dtype=float),
                "ts": np.asarray(ts, dtype="int64"),
            }
        }
    }
    df = pd.DataFrame(
        {
            "pair": ["EURUSD_GBPUSD", "EURUSD_GBPUSD"],
            "timeframe": ["m15", "m15"],
            "entry_idx": [3, 6],
            "timestamp": [int(ts[3]), int(ts[6])],
        }
    )

    out = add_robust_kf_features(df, state_cache=state_cache)

    for col in [
        "kf_abs_z",
        "kf_innov",
        "kf_innov_std",
        "kf_robust_z",
        "kf_student_loglik",
        "kf_tod_scale",
        "kf_huber_weight",
        "kf_jump_prob",
    ]:
        assert col in out.columns
        assert np.isfinite(out[col].to_numpy(dtype=float)).all()

    # kf_abs_z is directly mapped from |z[idx]|
    assert np.isclose(out.loc[0, "kf_abs_z"], abs(state_cache["m15"]["EURUSD_GBPUSD"]["z"][3]))
    assert np.isclose(out.loc[1, "kf_abs_z"], abs(state_cache["m15"]["EURUSD_GBPUSD"]["z"][6]))


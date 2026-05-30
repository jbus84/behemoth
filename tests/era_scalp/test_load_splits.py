import numpy as np
import pandas as pd

from scripts.era_scalp.load_splits import WHITELIST, build_splits


def _write_fake_parquet(path, n=3000):
    rng = np.random.default_rng(0)
    ts = pd.to_datetime(np.r_[
        pd.date_range("2023-06-01", periods=n // 3, freq="5min", tz="UTC"),
        pd.date_range("2024-06-01", periods=n // 3, freq="5min", tz="UTC"),
        pd.date_range("2025-06-01", periods=n - 2 * (n // 3), freq="5min", tz="UTC"),
    ])
    cols = {c: rng.standard_normal(n) for c in WHITELIST}
    cols["close_ts"] = ts
    cols["cost_est_pips"] = np.full(n, 0.4)
    for h in (1, 2, 3):
        cols[f"y_fwd_pips_h{h}"] = rng.standard_normal(n)
    cols["close_bid"] = rng.standard_normal(n)  # leakage column, must be excluded
    pd.DataFrame(cols).to_parquet(path)


def test_build_splits_embargo_and_no_leakage(tmp_path):
    p = tmp_path / "EURUSD_100tick_velocity.parquet"
    _write_fake_parquet(p)
    splits = build_splits("EURUSD", p, horizon=3,
                          train=("2023",), validation=("2024",), holdout=("2025",))
    for name in ("train", "validation", "holdout"):
        d = splits[name]
        assert d.X.shape[0] == len(d.y_fwd) == len(d.test_month)
        assert d.X.shape[1] == len(WHITELIST)
        assert "close_bid" not in d.names and "y_fwd_pips_h3" not in d.names
        assert d.X.shape[0] > 0
    full_train = (pd.read_parquet(p)["close_ts"].dt.year == 2023).sum()
    assert splits["train"].X.shape[0] == full_train - 3

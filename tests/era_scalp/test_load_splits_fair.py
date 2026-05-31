import numpy as np
import pandas as pd

from scripts.era_scalp.load_splits import WHITELIST, build_fair_splits


def _write_fake(path, n=3000):
    rng = np.random.default_rng(0)
    ts = pd.to_datetime(np.r_[
        pd.date_range("2023-06-01", periods=n // 3, freq="5min", tz="UTC"),
        pd.date_range("2024-06-01", periods=n // 3, freq="5min", tz="UTC"),
        pd.date_range("2025-06-01", periods=n - 2 * (n // 3), freq="5min", tz="UTC"),
    ])
    cols = {c: rng.standard_normal(n) for c in WHITELIST}
    cols["close_ts"] = ts
    cols["close_bid"] = 1.1 + rng.standard_normal(n) * 1e-3
    cols["close_ask"] = cols["close_bid"] + 3e-5
    pd.DataFrame(cols).to_parquet(path)


def test_build_fair_splits_mid_and_embargo(tmp_path):
    p = tmp_path / "EURUSD_100tick_velocity.parquet"
    _write_fake(p)
    splits = build_fair_splits("EURUSD", p, embargo=50,
                               train=("2023",), validation=("2024",), holdout=("2025",))
    for name in ("train", "validation", "holdout"):
        d = splits[name]
        assert d.X.shape[1] == len(WHITELIST)
        assert len(d.mid) == d.X.shape[0] == len(d.test_month)
        assert "close_bid" not in d.names and "close_ask" not in d.names
        assert np.all(d.mid > 1.0)
    full_train = (pd.read_parquet(p)["close_ts"].dt.year == 2023).sum()
    assert splits["train"].X.shape[0] == full_train - 50

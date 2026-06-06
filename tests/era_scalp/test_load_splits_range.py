import numpy as np
import pandas as pd

from scripts.era_scalp.load_splits import WHITELIST, build_range_splits


def _write_fake(path, n=3000):
    rng = np.random.default_rng(0)
    ts = pd.to_datetime(np.r_[
        pd.date_range("2023-06-01", periods=n // 3, freq="5min", tz="UTC"),
        pd.date_range("2024-06-01", periods=n // 3, freq="5min", tz="UTC"),
        pd.date_range("2025-06-01", periods=n - 2 * (n // 3), freq="5min", tz="UTC"),
    ])
    cols = {c: rng.standard_normal(n) for c in WHITELIST if c != "range_pips"}
    cols["close_ts"] = ts
    cols["close_bid"] = 1.1 + rng.standard_normal(n) * 1e-3
    cols["high_bid"] = cols["close_bid"] + np.abs(rng.standard_normal(n)) * 1e-3
    cols["low_bid"] = cols["close_bid"] - np.abs(rng.standard_normal(n)) * 1e-3
    cols["spread_pips"] = np.full(n, 0.3)
    cols["cost_est_pips"] = np.full(n, 0.4)
    pd.DataFrame(cols).to_parquet(path)


def test_build_range_splits_carries_prices_and_embargo(tmp_path):
    p = tmp_path / "EURUSD_100tick_velocity.parquet"
    _write_fake(p)
    splits = build_range_splits("EURUSD", p, max_hold=4,
                                train=("2023",), validation=("2024",), holdout=("2025",))
    for name in ("train", "validation", "holdout"):
        d = splits[name]
        assert d.X.shape[1] == len(WHITELIST)
        assert "range_pips" in d.names
        assert len(d.close_bid) == len(d.high_bid) == len(d.low_bid) == d.X.shape[0]
        assert len(d.spread) == len(d.cost) == d.X.shape[0]
    full_train = (pd.read_parquet(p)["close_ts"].dt.year == 2023).sum()
    assert splits["train"].X.shape[0] == full_train - 4


def test_range_pips_is_in_whitelist_and_nonneg(tmp_path):
    p = tmp_path / "EURUSD_100tick_velocity.parquet"
    _write_fake(p)
    splits = build_range_splits("EURUSD", p, max_hold=4,
                                train=("2023",), validation=("2024",), holdout=("2025",))
    j = splits["train"].names.index("range_pips")
    assert np.all(splits["train"].X[:, j] >= 0)


def test_cap_recent_range_slices_all_arrays(tmp_path):
    from scripts.era_scalp.load_splits import cap_recent_range
    p = tmp_path / "EURUSD_100tick_velocity.parquet"
    _write_fake(p, n=5000)
    splits = build_range_splits("EURUSD", p, max_hold=4,
                                train=("2023",), validation=("2024",), holdout=("2025",))
    orig_val = splits["validation"]
    capped = cap_recent_range(orig_val, max_bars=100)
    assert capped.close_bid.shape[0] == 100
    assert capped.X.shape[0] == 100
    assert capped.high_bid.shape[0] == 100
    assert capped.low_bid.shape[0] == 100
    assert capped.spread.shape[0] == 100

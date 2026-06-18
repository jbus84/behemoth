from datetime import datetime, timedelta

import numpy as np
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


def test_gate_trades_uses_train_threshold_long_and_short():
    from scripts.fx_coint.tail_wfo import gate_trades
    # one fold: train preds 0..99, q=0.9 -> thr ~ 89.1; test preds chosen around it
    train = np.arange(100.0)
    test_pred = np.array([50.0, 90.0, 95.0, 10.0])
    test_act = np.array([1.0, 2.0, 3.0, 4.0])
    test_hour = np.array([12, 13, 14, 15])
    test_bucket = np.array(["2025-01-06T12:00", "2025-01-06T13:00",
                            "2025-01-06T14:00", "2025-01-06T15:00"], dtype="datetime64[ns]")
    folds = [{"train_pred": train, "test_pred": test_pred, "test_actual_bps": test_act,
              "test_hour": test_hour, "test_bucket": test_bucket}]
    # long: thr=quantile(0..99,0.9)=89.1 -> selects test_pred 90,95 -> net = act - cost
    res = gate_trades(folds, q=0.9, cost_bps=0.5, side="long")
    assert res["n"] == 2
    assert np.allclose(sorted(res["net"]), sorted([2.0 - 0.5, 3.0 - 0.5]))
    assert set(res["hour"].tolist()) == {13, 14}
    # short: thr_low=quantile(0..99,0.1)=9.9 -> selects test_pred 10? (10>=9.9 false for <=) -> none<=9.9
    res_s = gate_trades(folds, q=0.9, cost_bps=0.5, side="short")
    assert res_s["n"] == 0
    # widen: q=0.85 -> thr_low=quantile(.,0.15)=14.85 -> selects 10.0 -> net = -act - cost
    res_s2 = gate_trades(folds, q=0.85, cost_bps=0.5, side="short")
    assert res_s2["n"] == 1
    assert np.allclose(res_s2["net"], [-4.0 - 0.5])


def test_cell_stats_known_arrays():
    from scripts.fx_coint.tail_wfo import cell_stats
    # 2 folds: fold 0 all positive, fold 1 mostly negative
    net = np.array([1.0, 2.0, 1.5, -1.0, -0.5, -2.0])
    fid = np.array([0, 0, 0, 1, 1, 1])
    s = cell_stats(net, fid)
    assert s["n"] == 6
    assert abs(s["mean_net_bps"] - net.mean()) < 1e-9
    assert abs(s["total_net_bps"] - net.sum()) < 1e-9
    assert s["pos_fold_pct"] == 0.5  # fold 0 positive, fold 1 negative
    assert abs(s["hit_rate"] - 3 / 6) < 1e-9
    assert np.isfinite(s["t_stat"]) and np.isfinite(s["p_value"])
    # n<3 -> nan stats guard
    s2 = cell_stats(np.array([1.0, 2.0]), np.array([0, 0]))
    assert np.isnan(s2["t_stat"]) and np.isnan(s2["p_value"])


def test_run_cell_wfo_on_synthetic(tmp_path, monkeypatch):
    import scripts.fx_coint.tail_wfo as tw
    df = _synthetic_1m(datetime(2025, 1, 6, 7, 0), 3000 * 60)
    d = tmp_path / "data" / "tick_bars"
    d.mkdir(parents=True)
    df.write_parquet(d / "EURUSD_1m_flow.parquet")
    monkeypatch.setattr(tw, "_REPO_ROOT", tmp_path)
    row = tw.run_cell_wfo("EURUSD", "2h", side="long", q=0.9, n_folds=4)
    assert row is not None
    assert row["symbol"] == "EURUSD" and row["freq"] == "2h" and row["side"] == "long"
    for k in ["n", "mean_net_bps", "t_stat", "p_value", "pos_fold_pct", "hit_rate"]:
        assert k in row
    assert row["n"] > 0


def test_day_clustered_tstat_groups_by_date():
    from scripts.fx_coint.tail_wfo import day_clustered_tstat
    # two trades per day across 4 days; daily means = [1, 1, 1, 1] -> strongly positive
    buckets = np.array([
        "2025-01-06T10:00", "2025-01-06T12:00",
        "2025-01-07T10:00", "2025-01-07T12:00",
        "2025-01-08T10:00", "2025-01-08T12:00",
        "2025-01-09T10:00", "2025-01-09T12:00",
    ], dtype="datetime64[ns]")
    net = np.array([0.5, 1.5, 0.8, 1.2, 0.9, 1.1, 1.0, 1.0])  # each day mean = 1.0
    r = day_clustered_tstat(net, buckets)
    assert r["n_days"] == 4
    assert abs(r["daily_mean"] - 1.0) < 1e-9
    # zero within-day variance of daily means -> huge t, tiny p
    assert r["t_stat"] > 50 and r["p_value"] < 1e-3
    # empty input guard
    r0 = day_clustered_tstat(np.array([]), np.array([], dtype="datetime64[ns]"))
    assert r0["n_days"] == 0 and np.isnan(r0["t_stat"])

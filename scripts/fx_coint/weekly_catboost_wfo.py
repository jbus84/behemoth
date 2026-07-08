"""Weekly mean-reversion WFO validation — CatBoost regression on daily bars.

Replicates the June-11 memory claim: pooled 6 majors, momentum/vol features,
predict forward 5d log-return, trade top/bottom decile, hold 5 days.

Walk-forward: annual retraining (train 2018→test 2019, train 2018-19→test 2020, ...).
Causal: all thresholds/deciles from training data only.
Real Razor cost.

Usage:
    uv run python scripts/fx_coint/weekly_catboost_wfo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostRegressor
from scipy.stats import ttest_1samp

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402

rsh.FREQ_MINUTES["1d"] = 1440

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF"]
TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
COMM = 0.60
SPR = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2, "USDCAD": .3, "AUDUSD": .15, "USDCHF": .3}
PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": .65, "USDCHF": .89}
RNG = np.random.default_rng(0)


def cost(sym: str) -> float:
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


def load_daily(sym: str) -> pd.DataFrame:
    bars = rsh.build_freq_bars(
        pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"),
        "1d", session=(0, 24),
    )
    bars["ret_bps"] = np.log(bars["mid"]).diff() * 1e4
    bars = bars.set_index("bucket").sort_index()
    return bars


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Daily momentum/vol features.  All lookback-based, no future leakage."""
    r = df["ret_bps"]
    out = pd.DataFrame(index=df.index)
    out["r_1"] = r
    for w in [5, 10, 20, 60, 120]:
        out[f"ret_{w}d"] = r.rolling(w, min_periods=w // 2).sum()
        out[f"vol_{w}d"] = r.rolling(w, min_periods=w // 2).std()
    out["rvol_ratio"] = out["vol_20d"] / out["vol_60d"]
    out["mom_accel"] = out["ret_20d"] - out["ret_60d"]
    out["skew_20d"] = r.rolling(20, min_periods=10).skew()
    out["max_dd_20d"] = (r.rolling(20, min_periods=10).max() - r.rolling(20, min_periods=10).min())
    out["bucket"] = df.index
    out["mid"] = df["mid"]
    out["contig"] = df["contig"]
    # Forward 5-day return  (fwd[i] = log(mid[i+5]) - log(mid[i]))
    mid = df["mid"].to_numpy()
    fwd = np.empty(len(mid))
    fwd[-5:] = np.nan
    fwd[:-5] = (np.log(mid[5:]) - np.log(mid[:-5])) * 1e4
    out["fwd_5d"] = fwd
    return out.dropna()


def boot_ci(net: np.ndarray, buckets: np.ndarray, n_boot: int = 3000) -> tuple[float, float]:
    if len(net) < 3:
        return np.nan, np.nan
    s = pd.Series(net, index=pd.to_datetime(buckets).year)
    arrs = [g.to_numpy() for _, g in s.groupby(level=0)]
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = RNG.integers(0, len(arrs), len(arrs))
        means[b] = np.concatenate([arrs[i] for i in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def pos_years(net: np.ndarray, buckets: np.ndarray) -> tuple[int, int]:
    yr = pd.Series(net, index=pd.to_datetime(buckets).year).groupby(level=0).mean()
    return int((yr > 0).sum()), len(yr)


def line(label: str, net: np.ndarray, bk: np.ndarray) -> None:
    if len(net) < 3:
        print(f"  {label:>16} (too few: n={len(net)})")
        return
    t, p = ttest_1samp(net, 0)
    clo, chi = boot_ci(net, bk)
    py, ny = pos_years(net, bk)
    # Cumulative and drawdown
    df = pd.DataFrame({"net": net, "bucket": pd.to_datetime(bk)}).sort_values("bucket")
    cum = np.cumsum(df["net"].to_numpy())
    dd = cum - np.maximum.accumulate(cum)
    maxdd = dd.min()
    ret_dd = abs(cum[-1] / maxdd) if maxdd < 0 else float("inf")
    print(f"  {label:>16} n={len(net):>4} net={net.mean():>+7.2f} t={t:>+5.2f} p={p:>6.3f} "
          f"hit={(net>0).mean()*100:>3.0f}% posYrs={py}/{ny} boot95=[{clo:>+6.2f},{chi:>+6.2f}] "
          f"maxDD={maxdd:>+8.1f} ret/DD={ret_dd:>+5.2f}")


def annual_wfo(pairs: list[str], q: float = 0.90) -> tuple[np.ndarray, np.ndarray, dict]:
    """
    Annual walk-forward:
      - For each year Y (test), train on all prior years.
      - Fit CatBoost regressor on pooled training data.
      - Predict fwd_5d for each pair in test year.
      - Trade top-q long / bottom-q short, hold 5 days, non-overlapping per pair.
    """
    # Build panels
    panels = {}
    for sym in pairs:
        df = load_daily(sym)
        feat = build_features(df)
        feat["sym"] = sym
        panels[sym] = feat

    all_net, all_bk = [], []
    yearly = {}
    test_years = range(2019, 2026)

    for test_year in test_years:
        train_frames, test_frames = [], []
        for sym, feat in panels.items():
            train = feat[feat["bucket"].dt.year < test_year].copy()
            test = feat[feat["bucket"].dt.year == test_year].copy()
            if len(train) < 100 or len(test) < 10:
                continue
            train["sym"] = sym
            test["sym"] = sym
            train_frames.append(train)
            test_frames.append(test)

        if not train_frames or not test_frames:
            continue

        train_df = pd.concat(train_frames, ignore_index=True)
        test_df = pd.concat(test_frames, ignore_index=True)

        # Feature cols
        feat_cols = [c for c in train_df.columns if c.startswith(("ret_", "vol_", "rvol_", "mom_", "skew_", "max_dd_"))]

        X_train = train_df[feat_cols].to_numpy()
        y_train = train_df["fwd_5d"].to_numpy()
        X_test = test_df[feat_cols].to_numpy()

        # Scale
        mu, sg = X_train.mean(axis=0), X_train.std(axis=0)
        sg[sg == 0] = 1
        X_train_s = (X_train - mu) / sg
        X_test_s = (X_test - mu) / sg

        model = CatBoostRegressor(
            iterations=300,
            depth=4,
            learning_rate=0.05,
            l2_leaf_reg=10.0,
            subsample=0.6,
            rsm=0.6,
            verbose=False,
            random_seed=42,
            thread_count=4,
        )
        model.fit(X_train_s, y_train)
        preds = model.predict(X_test_s)
        test_df = test_df.copy()
        test_df["pred"] = preds

        # Per-pair: trade top/bottom q of predictions, non-overlapping 5d
        for sym in pairs:
            sym_df = test_df[test_df["sym"] == sym].sort_values("bucket").reset_index(drop=True)
            if len(sym_df) < 20:
                continue
            hi = np.quantile(sym_df["pred"], q)
            lo = np.quantile(sym_df["pred"], 1 - q)
            c = cost(sym)
            nets, bks = [], []
            last_i = -10
            for i, row in sym_df.iterrows():
                if i - last_i < 5:
                    continue
                p = row["pred"]
                fwd = row["fwd_5d"]
                if np.isnan(fwd):
                    continue
                if p >= hi:
                    nets.append(fwd - c)
                    bks.append(row["bucket"])
                    last_i = i
                elif p <= lo:
                    nets.append(-fwd - c)
                    bks.append(row["bucket"])
                    last_i = i
            if nets:
                all_net.extend(nets)
                all_bk.extend(bks)
                yr_key = test_year
                yearly.setdefault(yr_key, []).extend(nets)

    return np.array(all_net), np.array(all_bk), yearly


def main() -> None:
    print("=" * 100)
    print("WEEKLY CATBOOST WFO — pooled daily bars, predict fwd-5d return, top/bottom decile")
    print("Walk-forward: train on prior years, test on next year, annual retraining")
    print("=" * 100)

    for q in [0.90, 0.80, 0.70]:
        print(f"\n### Selectivity: top/bottom {int((1-q)*100)}% of predictions ###")
        for pairs, label in [(TIGHT, "TIGHT3"), (PAIRS, "ALL6")]:
            print(f"\n  {label}:")
            net, bk, yearly = annual_wfo(pairs, q=q)
            line(f"{label} q{int(q*100)}", net, bk)
            if yearly:
                print(f"    annual breakdown:")
                for yr in sorted(yearly.keys()):
                    arr = np.array(yearly[yr])
                    print(f"      {yr}: n={len(arr):>3} net={arr.mean():>+7.2f} total={arr.sum():>+8.1f}")

    # Also test: simple non-ML baseline (fade past-20d return)
    print("\n" + "=" * 100)
    print("BASELINE: fade past-20d return (no ML), top-10% |move|, hold 5d, non-overlap")
    print("=" * 100)
    for sym in PAIRS:
        df = load_daily(sym)
        r = df["ret_bps"].to_numpy()
        mid = df["mid"].to_numpy()
        bk = df.index.to_numpy()
        rs = pd.Series(r)
        sig = rs.rolling(20, min_periods=10).sum().to_numpy()
        fwd = np.empty(len(mid))
        fwd[-5:] = np.nan
        fwd[:-5] = (np.log(mid[5:]) - np.log(mid[:-5])) * 1e4
        valid = np.isfinite(sig) & np.isfinite(fwd)
        idx = np.where(valid)[0]
        # Non-overlap step 5
        grid = idx[np.arange(0, len(idx), 5)]
        c = cost(sym)
        hist = []
        nets, bks = [], []
        for gi in grid:
            s = sig[gi]
            if len(hist) >= 60:
                thr = np.quantile(hist, 0.90)
                if abs(s) >= thr:
                    net = -fwd[gi] - c if s > 0 else fwd[gi] - c
                    nets.append(net)
                    bks.append(bk[gi])
            hist.append(abs(s))
        line(sym, np.array(nets), np.array(bks))

    # Pooled baseline
    print("\n  Pooled baseline:")
    all_nets, all_bks = [], []
    for sym in PAIRS:
        df = load_daily(sym)
        r = df["ret_bps"].to_numpy()
        mid = df["mid"].to_numpy()
        bk = df.index.to_numpy()
        rs = pd.Series(r)
        sig = rs.rolling(20, min_periods=10).sum().to_numpy()
        fwd = np.empty(len(mid))
        fwd[-5:] = np.nan
        fwd[:-5] = (np.log(mid[5:]) - np.log(mid[:-5])) * 1e4
        valid = np.isfinite(sig) & np.isfinite(fwd)
        idx = np.where(valid)[0]
        grid = idx[np.arange(0, len(idx), 5)]
        c = cost(sym)
        hist = []
        for gi in grid:
            s = sig[gi]
            if len(hist) >= 60:
                thr = np.quantile(hist, 0.90)
                if abs(s) >= thr:
                    net = -fwd[gi] - c if s > 0 else fwd[gi] - c
                    all_nets.append(net)
                    all_bks.append(bk[gi])
            hist.append(abs(s))
    line("POOLED6", np.array(all_nets), np.array(all_bks))


if __name__ == "__main__":
    main()

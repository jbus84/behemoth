"""Expanding-window WFO for weekly/monthly momentum on TIGHT3.

Train window grows: 2018→test 2019, 2018-19→test 2020, ..., 2018-24→test 2025.
Each fold uses fresh model fit on all prior years.

Usage:
    uv run python scripts/fx_coint/weekly_momentum_expanding_wfo.py
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

TIGHT = ["EURUSD", "GBPUSD", "USDJPY"]
COMM = 0.60
SPR = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2}
PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27}
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


def build_features(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
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
    mid = df["mid"].to_numpy()
    fwd = np.empty(len(mid))
    fwd[-horizon:] = np.nan
    fwd[:-horizon] = (np.log(mid[horizon:]) - np.log(mid[:-horizon])) * 1e4
    out["fwd"] = fwd
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
    df = pd.DataFrame({"net": net, "bucket": pd.to_datetime(bk)}).sort_values("bucket")
    cum = np.cumsum(df["net"].to_numpy())
    dd = cum - np.maximum.accumulate(cum)
    maxdd = dd.min()
    ret_dd = abs(cum[-1] / maxdd) if maxdd < 0 else float("inf")
    print(f"  {label:>16} n={len(net):>4} net={net.mean():>+7.2f} t={t:>+5.2f} p={p:>6.3f} "
          f"hit={(net>0).mean()*100:>3.0f}% posYrs={py}/{ny} boot95=[{clo:>+6.2f},{chi:>+6.2f}] "
          f"maxDD={maxdd:>+8.1f} ret/DD={ret_dd:>+5.2f}")


def expanding_wfo(horizon: int, q: float = 0.90) -> dict:
    """Expanding-window WFO. Returns per-fold results + aggregate."""
    panels = {}
    for sym in TIGHT:
        df = load_daily(sym)
        feat = build_features(df, horizon)
        feat["sym"] = sym
        panels[sym] = feat

    results = []
    all_net, all_bk = [], []

    for test_year in range(2019, 2026):
        train_frames, test_frames = [], []
        for sym, feat in panels.items():
            train = feat[feat["bucket"].dt.year < test_year].copy()
            test = feat[feat["bucket"].dt.year == test_year].copy()
            train["sym"] = sym
            test["sym"] = sym
            train_frames.append(train)
            test_frames.append(test)

        train_df = pd.concat(train_frames, ignore_index=True)
        test_df = pd.concat(test_frames, ignore_index=True)

        if len(train_df) < 200 or len(test_df) < 20:
            continue

        feat_cols = [c for c in train_df.columns if c.startswith(("ret_", "vol_", "rvol_", "mom_", "skew_", "max_dd_"))]
        X_train = train_df[feat_cols].to_numpy()
        y_train = train_df["fwd"].to_numpy()
        X_test = test_df[feat_cols].to_numpy()

        mu, sg = X_train.mean(axis=0), X_train.std(axis=0)
        sg[sg == 0] = 1
        X_train_s = (X_train - mu) / sg
        X_test_s = (X_test - mu) / sg

        model = CatBoostRegressor(
            iterations=300, depth=4, learning_rate=0.05, l2_leaf_reg=10.0,
            subsample=0.6, rsm=0.6, verbose=False, random_seed=42, thread_count=4,
        )
        model.fit(X_train_s, y_train)
        preds = model.predict(X_test_s)
        test_df = test_df.copy()
        test_df["pred"] = preds

        fold_net, fold_bk = [], []
        for sym in TIGHT:
            sym_df = test_df[test_df["sym"] == sym].sort_values("bucket").reset_index(drop=True)
            if len(sym_df) < 10:
                continue
            c = cost(sym)
            hi = np.quantile(sym_df["pred"], q)
            lo = np.quantile(sym_df["pred"], 1 - q)

            for _, row in sym_df.iterrows():
                p = row["pred"]
                fwd = row["fwd"]
                if np.isnan(fwd):
                    continue
                if p >= hi:
                    fold_net.append(fwd - c)
                    fold_bk.append(row["bucket"])
                elif p <= lo:
                    fold_net.append(-fwd - c)
                    fold_bk.append(row["bucket"])

        if fold_net:
            arr = np.array(fold_net)
            b_arr = np.array(fold_bk)
            results.append({
                "test_year": test_year,
                "n": len(arr),
                "net": arr.mean(),
                "total": arr.sum(),
                "pos_pct": (arr > 0).mean() * 100,
            })
            all_net.extend(arr)
            all_bk.extend(b_arr)

    return {
        "folds": results,
        "net": np.array(all_net),
        "bk": np.array(all_bk),
    }


def baseline_wfo(horizon: int, lookback: int, q: float = 0.90, rule: str = "momentum") -> dict:
    """Expanding-window WFO for simple rule (past lookback return)."""
    panels = {}
    for sym in TIGHT:
        df = load_daily(sym)
        feat = build_features(df, horizon)
        feat["sym"] = sym
        panels[sym] = feat

    col = f"ret_{lookback}d"
    results = []
    all_net, all_bk = [], []

    for test_year in range(2019, 2026):
        for sym, feat in panels.items():
            test = feat[feat["bucket"].dt.year == test_year].copy()
            if len(test) < 10 or col not in test.columns:
                continue
            c = cost(sym)
            s = test[col].to_numpy()
            fwd = test["fwd"].to_numpy()
            bk = test["bucket"].to_numpy()
            hi = np.quantile(s, q)
            lo = np.quantile(s, 1 - q)
            fold_net, fold_bk = [], []
            for i in range(len(s)):
                if np.isnan(fwd[i]):
                    continue
                if rule == "momentum":
                    if s[i] >= hi:
                        fold_net.append(fwd[i] - c)
                        fold_bk.append(bk[i])
                    elif s[i] <= lo:
                        fold_net.append(-fwd[i] - c)
                        fold_bk.append(bk[i])
                elif rule == "reversion":
                    if s[i] >= hi:
                        fold_net.append(-fwd[i] - c)
                        fold_bk.append(bk[i])
                    elif s[i] <= lo:
                        fold_net.append(fwd[i] - c)
                        fold_bk.append(bk[i])
            if fold_net:
                arr = np.array(fold_net)
                results.append({
                    "test_year": test_year,
                    "sym": sym,
                    "n": len(arr),
                    "net": arr.mean(),
                    "total": arr.sum(),
                })
                all_net.extend(arr)
                all_bk.extend(fold_bk)

    return {
        "folds": results,
        "net": np.array(all_net),
        "bk": np.array(all_bk),
    }


def main() -> None:
    print("=" * 100)
    print("EXPANDING-WINDOW WFO — TIGHT3 weekly/monthly momentum")
    print("Train: all years < test_year | Test: test_year only")
    print("=" * 100)

    for horizon, h_label in [(5, "WEEKLY (5d)"), (20, "MONTHLY (20d)")]:
        print(f"\n{'='*100}")
        print(f"{h_label}")
        print(f"{'='*100}")

        # CatBoost MOM
        res = expanding_wfo(horizon, q=0.90)
        print(f"\nCatBoost MOM (top/bottom 10%):")
        line("ALL FOLDS", res["net"], res["bk"])
        print(f"  per-fold:")
        for f in res["folds"]:
            print(f"    {f['test_year']}: n={f['n']:>3} net={f['net']:>+7.2f} total={f['total']:>+8.1f} hit={f['pos_pct']:.0f}%")

        # Simple MOM(20d)
        res_base = baseline_wfo(horizon, 20, q=0.90, rule="momentum")
        print(f"\nSimple MOM(20d) baseline:")
        line("ALL FOLDS", res_base["net"], res_base["bk"])

        # Simple REV(20d) for contrast
        res_rev = baseline_wfo(horizon, 20, q=0.90, rule="reversion")
        print(f"\nSimple REV(20d) baseline:")
        line("ALL FOLDS", res_rev["net"], res_rev["bk"])

    # Feature importance from the final model (train 2018-2024, test 2025)
    print(f"\n{'='*100}")
    print("FEATURE IMPORTANCE (final model: train 2018-2024, test 2025, weekly H=5)")
    print(f"{'='*100}")
    panels = {}
    for sym in TIGHT:
        df = load_daily(sym)
        feat = build_features(df, 5)
        feat["sym"] = sym
        panels[sym] = feat

    train_frames = [panels[s][panels[s]["bucket"].dt.year < 2025].copy() for s in TIGHT]
    train_df = pd.concat(train_frames, ignore_index=True)
    feat_cols = [c for c in train_df.columns if c.startswith(("ret_", "vol_", "rvol_", "mom_", "skew_", "max_dd_"))]
    X_train = train_df[feat_cols].to_numpy()
    y_train = train_df["fwd"].to_numpy()
    mu, sg = X_train.mean(axis=0), X_train.std(axis=0)
    sg[sg == 0] = 1
    model = CatBoostRegressor(
        iterations=300, depth=4, learning_rate=0.05, l2_leaf_reg=10.0,
        subsample=0.6, rsm=0.6, verbose=False, random_seed=42, thread_count=4,
    )
    model.fit((X_train - mu) / sg, y_train)
    imp = model.get_feature_importance()
    for name, val in sorted(zip(feat_cols, imp), key=lambda x: -x[1]):
        print(f"  {name:20s} {val:>8.1f}")


if __name__ == "__main__":
    main()

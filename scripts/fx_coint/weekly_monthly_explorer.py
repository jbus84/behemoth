"""Explore weekly/monthly directional edge with the ORIGINAL methodology:
  - Train 2018-2023, test 2024-2026 (single holdout, not annual WFO)
  - Rich features: past returns 1-120d, vol, skew, maxdd
  - Test BOTH momentum (chase) AND reversion (fade)
  - Weekly (H=5d) AND monthly (H=20d)
  - Per-pair AND pooled

Usage:
    uv run python scripts/fx_coint/weekly_monthly_explorer.py
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


def build_features(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Rich daily features + forward return at given horizon."""
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
    # Forward return
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
        print(f"  {label:>20} (too few: n={len(net)})")
        return
    t, p = ttest_1samp(net, 0)
    clo, chi = boot_ci(net, bk)
    py, ny = pos_years(net, bk)
    df = pd.DataFrame({"net": net, "bucket": pd.to_datetime(bk)}).sort_values("bucket")
    cum = np.cumsum(df["net"].to_numpy())
    dd = cum - np.maximum.accumulate(cum)
    maxdd = dd.min()
    ret_dd = abs(cum[-1] / maxdd) if maxdd < 0 else float("inf")
    print(f"  {label:>20} n={len(net):>4} net={net.mean():>+7.2f} t={t:>+5.2f} p={p:>6.3f} "
          f"hit={(net>0).mean()*100:>3.0f}% posYrs={py}/{ny} boot95=[{clo:>+6.2f},{chi:>+6.2f}] "
          f"maxDD={maxdd:>+8.1f} ret/DD={ret_dd:>+5.2f}")


def train_test_split(pairs: list[str], horizon: int, train_end: int = 2023):
    """Build train/test panels. Train = up to end of train_end year. Test = after."""
    panels = {}
    for sym in pairs:
        df = load_daily(sym)
        feat = build_features(df, horizon)
        feat["sym"] = sym
        panels[sym] = feat

    train_frames, test_frames = [], []
    for sym, feat in panels.items():
        train = feat[feat["bucket"].dt.year <= train_end].copy()
        test = feat[feat["bucket"].dt.year > train_end].copy()
        train["sym"] = sym
        test["sym"] = sym
        train_frames.append(train)
        test_frames.append(test)

    return pd.concat(train_frames, ignore_index=True), pd.concat(test_frames, ignore_index=True)


def evaluate_model(train_df: pd.DataFrame, test_df: pd.DataFrame, q: float,
                    direction: str = "both") -> tuple[np.ndarray, np.ndarray]:
    """Fit CatBoost on train, predict on test, trade top/bottom q.
    direction: 'both', 'long_only', 'short_only', 'momentum', 'reversion'
    """
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

    nets, bks = [], []
    for sym in test_df["sym"].unique():
        sym_df = test_df[test_df["sym"] == sym].sort_values("bucket").reset_index(drop=True)
        if len(sym_df) < 20:
            continue
        c = cost(sym)
        hi = np.quantile(sym_df["pred"], q)
        lo = np.quantile(sym_df["pred"], 1 - q)

        for _, row in sym_df.iterrows():
            p = row["pred"]
            fwd = row["fwd"]
            if np.isnan(fwd):
                continue

            if direction in ("both", "long_only"):
                if p >= hi:
                    nets.append(fwd - c)
                    bks.append(row["bucket"])
            if direction in ("both", "short_only"):
                if p <= lo:
                    nets.append(-fwd - c)
                    bks.append(row["bucket"])
            if direction == "momentum":
                if p >= hi:
                    nets.append(fwd - c)
                    bks.append(row["bucket"])
                elif p <= lo:
                    nets.append(-fwd - c)
                    bks.append(row["bucket"])
            if direction == "reversion":
                if p >= hi:
                    nets.append(-fwd - c)
                    bks.append(row["bucket"])
                elif p <= lo:
                    nets.append(fwd - c)
                    bks.append(row["bucket"])

    return np.array(nets), np.array(bks)


def simple_rule(test_df: pd.DataFrame, lookback: int, q: float, rule: str = "momentum") -> tuple[np.ndarray, np.ndarray]:
    """Simple rule: sort by past lookback-day return, trade top/bottom q.
    rule: 'momentum' = chase, 'reversion' = fade."""
    col = f"ret_{lookback}d"
    nets, bks = [], []
    for sym in test_df["sym"].unique():
        sym_df = test_df[test_df["sym"] == sym].sort_values("bucket").reset_index(drop=True)
        if len(sym_df) < 20 or col not in sym_df.columns:
            continue
        c = cost(sym)
        s = sym_df[col].to_numpy()
        fwd = sym_df["fwd"].to_numpy()
        bk = sym_df["bucket"].to_numpy()
        hi = np.quantile(s, q)
        lo = np.quantile(s, 1 - q)
        for i in range(len(s)):
            if np.isnan(fwd[i]):
                continue
            if rule == "momentum":
                if s[i] >= hi:
                    nets.append(fwd[i] - c)
                    bks.append(bk[i])
                elif s[i] <= lo:
                    nets.append(-fwd[i] - c)
                    bks.append(bk[i])
            elif rule == "reversion":
                if s[i] >= hi:
                    nets.append(-fwd[i] - c)
                    bks.append(bk[i])
                elif s[i] <= lo:
                    nets.append(fwd[i] - c)
                    bks.append(bk[i])
    return np.array(nets), np.array(bks)


def main() -> None:
    print("=" * 110)
    print("WEEKLY/MONTHLY EXPLORER — train 2018-2023, test 2024-2026")
    print("Tests BOTH momentum (chase) AND reversion (fade) with ML + simple rules")
    print("=" * 110)

    for horizon, h_label in [(5, "WEEKLY (5d)"), (20, "MONTHLY (20d)")]:
        print(f"\n{'='*110}")
        print(f"{h_label}")
        print(f"{'='*110}")

        for pairs, pool_label in [(TIGHT, "TIGHT3"), (PAIRS, "ALL6")]:
            print(f"\n--- {pool_label} ---")
            train_df, test_df = train_test_split(pairs, horizon)
            if train_df.empty or test_df.empty:
                print(f"  No data for {pool_label}")
                continue
            print(f"  train={len(train_df)} rows, test={len(test_df)} rows")

            for q in [0.90, 0.80]:
                pct = int((1-q)*100)
                print(f"\n  ### top/bottom {pct}% ###")

                # CatBoost MOMENTUM
                net, bk = evaluate_model(train_df, test_df, q, direction="momentum")
                line(f"  CatBoost MOM", net, bk)

                # CatBoost REVERSION
                net, bk = evaluate_model(train_df, test_df, q, direction="reversion")
                line(f"  CatBoost REV", net, bk)

                # Simple rule: momentum on past-20d return
                net, bk = simple_rule(test_df, 20, q, rule="momentum")
                line(f"  Simple MOM(20d)", net, bk)

                # Simple rule: reversion on past-20d return
                net, bk = simple_rule(test_df, 20, q, rule="reversion")
                line(f"  Simple REV(20d)", net, bk)

                # Simple rule: momentum on past-60d return
                net, bk = simple_rule(test_df, 60, q, rule="momentum")
                line(f"  Simple MOM(60d)", net, bk)

                # Simple rule: reversion on past-60d return
                net, bk = simple_rule(test_df, 60, q, rule="reversion")
                line(f"  Simple REV(60d)", net, bk)

    # Also: what if we pool per-pair predictions into a cross-sectional signal?
    print(f"\n{'='*110}")
    print("CROSS-SECTIONAL weekly/monthly — demean predictions across pairs, trade extremes")
    print(f"{'='*110}")
    for horizon, h_label in [(5, "WEEKLY (5d)"), (20, "MONTHLY (20d)")]:
        print(f"\n{h_label}:")
        train_df, test_df = train_test_split(PAIRS, horizon)
        if train_df.empty or test_df.empty:
            continue
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

        for q in [0.90, 0.80]:
            print(f"\n  top/bottom {int((1-q)*100)}%:")
            # Per-pair predictions, then demean across pairs on same day
            test_pred = test_df.copy()
            X_test = test_pred[feat_cols].to_numpy()
            test_pred["pred"] = model.predict((X_test - mu) / sg)
            test_pred["date"] = test_pred["bucket"].dt.date

            nets, bks = [], []
            for date, group in test_pred.groupby("date"):
                if len(group) < 3:
                    continue
                mean_pred = group["pred"].mean()
                group["xs_pred"] = group["pred"] - mean_pred
                hi = np.quantile(group["xs_pred"], q)
                lo = np.quantile(group["xs_pred"], 1 - q)
                for _, row in group.iterrows():
                    p = row["xs_pred"]
                    fwd = row["fwd"]
                    if np.isnan(fwd):
                        continue
                    c = cost(row["sym"])
                    # Long the most positive residual, short the most negative
                    if p >= hi:
                        nets.append(fwd - c)
                        bks.append(row["bucket"])
                    elif p <= lo:
                        nets.append(-fwd - c)
                        bks.append(row["bucket"])
            line(f"  XS MOM", np.array(nets), np.array(bks))

            # Now try REVERSION on the residual
            nets, bks = [], []
            for date, group in test_pred.groupby("date"):
                if len(group) < 3:
                    continue
                mean_pred = group["pred"].mean()
                group["xs_pred"] = group["pred"] - mean_pred
                hi = np.quantile(group["xs_pred"], q)
                lo = np.quantile(group["xs_pred"], 1 - q)
                for _, row in group.iterrows():
                    p = row["xs_pred"]
                    fwd = row["fwd"]
                    if np.isnan(fwd):
                        continue
                    c = cost(row["sym"])
                    if p >= hi:
                        nets.append(-fwd - c)
                        bks.append(row["bucket"])
                    elif p <= lo:
                        nets.append(fwd - c)
                        bks.append(row["bucket"])
            line(f"  XS REV", np.array(nets), np.array(bks))


if __name__ == "__main__":
    main()

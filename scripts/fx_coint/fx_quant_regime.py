"""Quantile-regime directional models: split by spread/vol/session, train simple models per bucket.

Goal: find if direction prediction improves when we condition on observable market states.
Regimes: past-24h spread, past-24h realised vol, hour-of-day, and interactions.
Model: per-regime LogisticRegression (standardised features).
Label: next-6h return sign (up/down).
Eval: AUC + gross/net fade/chase PnL per regime.

Usage:
    uv run python scripts/fx_coint/fx_quant_regime.py --symbol EURUSD
    uv run python scripts/fx_coint/fx_quant_regime.py --symbol all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]


def build_hourly(sym: str) -> pd.DataFrame:
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    df = pl.read_parquet(src).sort("bucket")
    t = df.with_columns(
        pl.col("mid").log().diff().alias("lr1"),
        ((pl.col("ask") - pl.col("bid")) / pl.col("mid")).alias("relspr"),
    )
    out = (
        t.with_columns(pl.col("bucket").dt.truncate("1h").alias("bf"))
        .group_by("bf")
        .agg(
            pl.col("mid").last(),
            pl.col("bid").last(),
            pl.col("ask").last(),
            pl.col("n_ticks").sum(),
            pl.col("flow_tick").mean(),
            pl.col("flow_ofi").mean(),
            (pl.col("lr1").std() * 1e4).alias("rvol_bps"),
            (pl.col("relspr").mean() * 1e4).alias("spread_bps"),
        )
        .rename({"bf": "bucket"})
        .sort("bucket")
        .to_pandas()
    )
    out["bucket"] = pd.to_datetime(out["bucket"])
    return out.sort_values("bucket").reset_index(drop=True)


def build_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Add causal features and labels."""
    mid = df["mid"].to_numpy()
    r = np.empty(len(df))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4

    # Contiguous only
    ts = df["bucket"].to_numpy().astype("datetime64[h]").astype(np.int64)
    contig = np.empty(len(df), bool)
    contig[0] = False
    contig[1:] = (ts[1:] - ts[:-1]) == 1
    r[~contig] = np.nan

    feats = pd.DataFrame({"bucket": df["bucket"]})
    feats["r_1"] = pd.Series(r).shift(1).to_numpy()
    feats["r_sum_2_6"] = pd.Series(r).rolling(5).sum().shift(1).to_numpy()
    feats["r_sum_7_24"] = pd.Series(r).rolling(18).sum().shift(5).to_numpy()
    feats["rvol_24"] = pd.Series(r).rolling(24).std().shift(1).to_numpy()
    feats["spread_bps"] = df["spread_bps"].shift(1).to_numpy()
    feats["flow_tick"] = df["flow_tick"].shift(1).to_numpy()
    feats["flow_ofi"] = df["flow_ofi"].shift(1).to_numpy()
    feats["hour"] = df["bucket"].dt.hour.astype(float)
    feats["dow"] = df["bucket"].dt.dayofweek.astype(float)

    # Upcoming 6h return
    mom6 = pd.Series(r).rolling(6).sum().shift(-6).to_numpy()
    feats["mom6"] = mom6
    up = (mom6 > 0).astype(float)
    up[~np.isfinite(mom6)] = np.nan
    feats["up"] = up

    # Causal regime labels: expanding quantiles on past 500 bars of causal features
    for col in ["spread_bps", "rvol_24", "flow_tick", "flow_ofi"]:
        s = pd.Series(feats[col])
        q33 = s.rolling(500, min_periods=250).quantile(0.33)
        q67 = s.rolling(500, min_periods=250).quantile(0.67)
        reg = np.zeros(len(df), dtype=int)
        reg[feats[col] <= q33] = 0
        reg[(feats[col] > q33) & (feats[col] <= q67)] = 1
        reg[feats[col] > q67] = 2
        feats[f"regime_{col}"] = reg

    # Time regime: London(7-11), NY(12-16), Asia(0-6), overlap(17-23)
    hr = df["bucket"].dt.hour.to_numpy()
    time_reg = np.zeros(len(df), dtype=int)
    time_reg[(hr >= 7) & (hr <= 11)] = 1   # London
    time_reg[(hr >= 12) & (hr <= 16)] = 2  # NY
    time_reg[(hr >= 17) & (hr <= 23)] = 3  # Overlap-ish / evening
    feats["regime_hour"] = time_reg

    # Day-of-week regime: Mon(0), Tue(1), Wed(2), Thu(3), Fri(4), Sat(5), Sun(6)
    dow = df["bucket"].dt.dayofweek.to_numpy()
    dow_reg = np.zeros(len(df), dtype=int)
    dow_reg[dow == 0] = 0  # Mon
    dow_reg[dow == 1] = 1  # Tue
    dow_reg[dow == 2] = 2  # Wed
    dow_reg[dow == 3] = 3  # Thu
    dow_reg[dow == 4] = 4  # Fri
    dow_reg[(dow == 5) | (dow == 6)] = 5  # Sat/Sun
    feats["regime_dow"] = dow_reg

    # Store prices for PnL
    feats["_mid"] = df["mid"].to_numpy()
    feats["_bid"] = df["bid"].to_numpy()
    feats["_ask"] = df["ask"].to_numpy()

    valid = (
        np.isfinite(feats["r_1"].to_numpy()) &
        np.isfinite(feats["rvol_24"].to_numpy()) &
        np.isfinite(feats["spread_bps"].to_numpy()) &
        np.isfinite(feats["up"].to_numpy())
    )
    return feats[valid].reset_index(drop=True)


def train_and_eval(X_train, y_train, X_test, y_test) -> dict:
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X_train)
    Xt = scaler.transform(X_test)
    clf = LogisticRegression(max_iter=1000, class_weight="balanced", n_jobs=5)
    clf.fit(Xs, y_train)
    probs = clf.predict_proba(Xt)[:, 1]
    auc = roc_auc_score(y_test, probs)
    acc = ((probs > 0.5).astype(int) == y_test).mean()
    baseline = y_test.mean()
    return {"probs": probs, "auc": auc, "acc": acc, "baseline": baseline}


def simulate(test_df: pd.DataFrame, probs: np.ndarray, direction: str) -> dict:
    """Simulate fade or chase using model probabilities. Trade top-10% confidence.
    Direction is determined by PAST 6h momentum (causal), not future mom6."""
    n_trade = max(1, len(probs) // 10)
    idx = np.argsort(np.abs(probs - 0.5))[-n_trade:]  # highest confidence = farthest from 0.5
    idx = np.sort(idx)

    # Past 6h momentum (causal, known at signal time)
    mom_past = test_df["r_1"].to_numpy() + test_df["r_sum_2_6"].to_numpy()
    sgn = np.sign(mom_past)
    side = -sgn if direction == "fade" else sgn

    ts = test_df["bucket"].to_numpy().astype("datetime64[h]").astype(np.int64)
    mid = test_df["_mid"].to_numpy()
    bid = test_df["_bid"].to_numpy()
    ask = test_df["_ask"].to_numpy()

    picked = []
    last = -10**9
    for i in idx:
        if i - last >= 3:  # non-overlap 3h  # noqa: SIM102
            if (i + 1 + 3) < len(ts) and (ts[i + 1 + 3] - ts[i]) == 4:  # noqa: SIM102
                if np.isfinite(side[i]):
                    picked.append(i)
                    last = i

    picked = np.array(picked)
    if len(picked) < 5:
        return {"n": 0}

    e, x = picked + 1, picked + 1 + 3
    m = mid[picked]
    gross = np.where(
        side[picked] < 0,
        (mid[e] - mid[x]) / m * 1e4,
        (mid[x] - mid[e]) / m * 1e4,
    )
    net = np.where(
        side[picked] < 0,
        (bid[e] - ask[x]) / m * 1e4,
        (bid[x] - ask[e]) / m * 1e4,
    )
    return {
        "n": len(picked),
        "gross_mean": gross.mean(),
        "net_mean": net.mean(),
        "gross_pos": (gross > 0).mean() * 100,
        "net_pos": (net > 0).mean() * 100,
        "cost_mean": (net - gross).mean(),
    }


def run_regime(df: pd.DataFrame, regime_col: str, feature_cols: list) -> None:
    """Train separate model per regime bucket."""
    regimes = sorted(df[regime_col].unique())
    print(f"\n--- Regime: {regime_col} ({len(regimes)} buckets) ---")

    split = int(len(df) * 0.7)
    train_df = df.iloc[:split]
    test_df = df.iloc[split:].copy().reset_index(drop=True)

    all_gross_fade, all_net_fade = [], []
    all_gross_chase, all_net_chase = [], []

    for reg in regimes:
        tr = train_df[train_df[regime_col] == reg]
        te = test_df[test_df[regime_col] == reg]
        if len(tr) < 200 or len(te) < 50:
            print(f"  bucket {reg}: insufficient data (train={len(tr)}, test={len(te)})")
            continue

        X_train = tr[feature_cols].fillna(0)
        y_train = tr["up"].to_numpy()
        X_test = te[feature_cols].fillna(0)
        y_test = te["up"].to_numpy()

        res = train_and_eval(X_train, y_train, X_test, y_test)

        # Per-regime simulations use test subset only
        te_idx = test_df[test_df[regime_col] == reg].index.to_numpy() - test_df.index.min()
        te_idx = np.arange(len(test_df))[test_df[regime_col] == reg]

        sim_fade = simulate(test_df.iloc[te_idx].copy().reset_index(drop=True), res["probs"], "fade")
        sim_chase = simulate(test_df.iloc[te_idx].copy().reset_index(drop=True), res["probs"], "chase")

        print(f"  bucket {reg}: N_test={len(te):>5}  AUC={res['auc']:.3f}  acc={res['acc']*100:.1f}%  baseline={res['baseline']*100:.1f}%", end="")
        if sim_fade["n"] > 0:
            print(f"  | fade net={sim_fade['net_mean']:+.2f} chase net={sim_chase['net_mean']:+.2f}")
            all_gross_fade.append(sim_fade["gross_mean"])
            all_net_fade.append(sim_fade["net_mean"])
            all_gross_chase.append(sim_chase["gross_mean"])
            all_net_chase.append(sim_chase["net_mean"])
        else:
            print()

    if len(all_net_fade) > 0:
        print(f"  CROSS-BUCKET fade  gross={np.mean(all_gross_fade):+.2f} net={np.mean(all_net_fade):+.2f}")
        print(f"  CROSS-BUCKET chase gross={np.mean(all_gross_chase):+.2f} net={np.mean(all_net_chase):+.2f}")


def run_pair(sym: str) -> None:
    print(f"\n{'='*65}\nPAIR: {sym}\n{'='*65}")
    df_raw = build_hourly(sym)
    df = build_panel(df_raw)

    feature_cols = [c for c in df.columns if c not in {
        "bucket", "mom6", "up", "_mid", "_bid", "_ask",
        "regime_spread_bps", "regime_rvol_24", "regime_flow_tick", "regime_flow_ofi", "regime_hour", "regime_dow"
    }]

    # Global baseline model (no regime)
    split = int(len(df) * 0.7)
    X_train = df.iloc[:split][feature_cols].fillna(0)
    y_train = df.iloc[:split]["up"].to_numpy()
    X_test = df.iloc[split:][feature_cols].fillna(0)
    y_test = df.iloc[split:]["up"].to_numpy()
    res = train_and_eval(X_train, y_train, X_test, y_test)
    print(f"\nGLOBAL baseline: AUC={res['auc']:.3f}  acc={res['acc']*100:.1f}%  baseline={res['baseline']*100:.1f}%")

    test_df = df.iloc[split:].copy().reset_index(drop=True)
    sim_fade = simulate(test_df, res["probs"], "fade")
    sim_chase = simulate(test_df, res["probs"], "chase")
    if sim_fade["n"] > 0:
        print(f"  global fade  gross={sim_fade['gross_mean']:+.2f} net={sim_fade['net_mean']:+.2f}")
        print(f"  global chase gross={sim_chase['gross_mean']:+.2f} net={sim_chase['net_mean']:+.2f}")

    # Per-regime models
    for reg_col in ["regime_spread_bps", "regime_rvol_24", "regime_hour", "regime_flow_ofi", "regime_dow"]:
        run_regime(df, reg_col, feature_cols)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD", choices=PAIRS + ["all"])
    args = ap.parse_args()

    if args.symbol == "all":
        for sym in PAIRS:
            run_pair(sym)
    else:
        run_pair(args.symbol)


if __name__ == "__main__":
    main()

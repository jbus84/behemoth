"""Simulate top-decile predictions with signal-bar spread filter.

Tests: only trade when signal-bar spread_bps <= threshold.
Reports gross vs net at various thresholds.

Usage:
    uv run python scripts/fx_coint/fx_ic_diagnose_spread_filter.py --symbol all --freq 15m
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]
FREQ_MAP = {"15m": ("15m", 15, 24, 12)}


def build_bars(sym: str, freq_label: str) -> pd.DataFrame:
    freq, minutes_per_bar, _, _ = FREQ_MAP[freq_label]
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    df = pl.read_parquet(src).sort("bucket")
    t = df.with_columns(
        pl.col("mid").log().diff().alias("lr1"),
        ((pl.col("ask") - pl.col("bid")) / pl.col("mid")).alias("relspr"),
    )
    out = (
        t.with_columns(pl.col("bucket").dt.truncate(freq).alias("bf"))
        .group_by("bf")
        .agg(
            pl.col("mid").last(), pl.col("bid").last(), pl.col("ask").last(),
            pl.col("n_ticks").sum(), pl.col("flow_tick").mean(), pl.col("flow_ofi").mean(),
            (pl.col("lr1").std() * 1e4).alias("rvol_bps"),
            (pl.col("relspr").mean() * 1e4).alias("spread_bps"),
        )
        .rename({"bf": "bucket"})
        .sort("bucket")
        .to_pandas()
    )
    out["bucket"] = pd.to_datetime(out["bucket"])
    return out.sort_values("bucket").reset_index(drop=True)


def build_panel(df: pd.DataFrame, mom_bars: int, minutes_per_bar: int) -> pd.DataFrame:
    mid = df["mid"].to_numpy()
    r = np.empty(len(df))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    ts = df["bucket"].to_numpy().astype("datetime64[m]").astype(np.int64)
    contig = np.empty(len(df), bool)
    contig[0] = False
    contig[1:] = (ts[1:] - ts[:-1]) == minutes_per_bar
    r[~contig] = np.nan

    feats = pd.DataFrame({"bucket": df["bucket"]})
    feats["r_1"] = pd.Series(r).shift(1).to_numpy()
    feats["r_sum_2_6"] = pd.Series(r).rolling(5, min_periods=3).sum().shift(1).to_numpy()
    feats["r_sum_7_24"] = pd.Series(r).rolling(18, min_periods=9).sum().shift(5).to_numpy()
    feats["rvol_24"] = pd.Series(r).rolling(24, min_periods=12).std().shift(1).to_numpy()
    feats["spread_bps"] = df["spread_bps"].shift(1).to_numpy()
    feats["flow_tick"] = df["flow_tick"].shift(1).to_numpy()
    feats["flow_ofi"] = df["flow_ofi"].shift(1).to_numpy()
    feats["hour"] = df["bucket"].dt.hour.astype(float)
    feats["dow"] = df["bucket"].dt.dayofweek.astype(float)
    mom = pd.Series(r).rolling(mom_bars, min_periods=mom_bars).sum().shift(-mom_bars).to_numpy()
    feats["target"] = mom
    feats["_mid"] = df["mid"].to_numpy()
    feats["_bid"] = df["bid"].to_numpy()
    feats["_ask"] = df["ask"].to_numpy()
    feats["_ts"] = ts
    valid = np.isfinite(feats["r_1"]) & np.isfinite(feats["target"]) & np.isfinite(feats["rvol_24"])
    return feats[valid].reset_index(drop=True)


def simulate_filtered(test_df: pd.DataFrame, preds: np.ndarray, threshold: float,
                       hold_bars: int, minutes_per_bar: int) -> dict:
    n_trade = max(1, len(preds) // 10)
    idx = np.argsort(np.abs(preds))[-n_trade:]
    idx = np.sort(idx)

    ts = test_df["_ts"].to_numpy()
    mid = test_df["_mid"].to_numpy()
    bid = test_df["_bid"].to_numpy()
    ask = test_df["_ask"].to_numpy()
    side = np.sign(preds)

    # Signal-bar spread in bps
    sig_spread = (ask - bid) / mid * 1e4

    picked = []
    last = -10**9
    for i in idx:
        if sig_spread[i] > threshold:
            continue
        if i - last >= hold_bars:  # noqa: SIM102
            if (i + 1 + hold_bars) < len(ts) and (ts[i + 1 + hold_bars] - ts[i]) == minutes_per_bar * (1 + hold_bars):
                picked.append(i)
                last = i

    picked = np.array(picked)
    if len(picked) < 5:
        return {"n": 0}

    e, x = picked + 1, picked + 1 + hold_bars
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


def run_pair(sym: str, freq_label: str) -> None:
    freq, minutes_per_bar, mom_bars, hold_bars = FREQ_MAP[freq_label]
    print(f"\n{'='*65}\nPAIR: {sym}\n{'='*65}")

    df_raw = build_bars(sym, freq_label)
    df = build_panel(df_raw, mom_bars, minutes_per_bar)

    feature_cols = ["r_1", "r_sum_2_6", "r_sum_7_24", "rvol_24", "spread_bps",
                    "flow_tick", "flow_ofi", "hour", "dow"]
    split = int(len(df) * 0.7)
    X_train = df.iloc[:split][feature_cols].fillna(0)
    y_train = df.iloc[:split]["target"].to_numpy()
    X_test = df.iloc[split:][feature_cols].fillna(0)
    df.iloc[split:]["target"].to_numpy()

    scaler = StandardScaler()
    Xs_train = scaler.fit_transform(X_train)
    Xs_test = scaler.transform(X_test)

    model = Ridge(alpha=1.0)
    model.fit(Xs_train, y_train)
    preds = model.predict(Xs_test)

    test_df = df.iloc[split:].reset_index(drop=True)
    test_df["_ts"].to_numpy()
    mid = test_df["_mid"].to_numpy()
    bid = test_df["_bid"].to_numpy()
    ask = test_df["_ask"].to_numpy()
    sig_spread = (ask - bid) / mid * 1e4

    print("\nSignal-bar spread distribution (test set):")
    print(f"  mean={sig_spread.mean():.2f}  med={np.median(sig_spread):.2f}  p90={np.percentile(sig_spread,90):.2f}  p99={np.percentile(sig_spread,99):.2f}")

    print(f"\n{'Threshold':>10} {'N':>5} {'Gross':>8} {'Net':>8} {'Cost':>7} {'Pos%':>5}")
    print("-" * 50)
    for thresh in [999, 3.0, 2.0, 1.5, 1.0, 0.8, 0.6]:
        sim = simulate_filtered(test_df, preds, thresh, hold_bars, minutes_per_bar)
        if sim["n"] == 0:
            print(f"{thresh:>10.1f} {'—':>5} {'—':>8} {'—':>8} {'—':>7} {'—':>5}")
        else:
            label = "(no filter)" if thresh > 50 else f"(spread≤{thresh})"
            print(f"{label:>10} {sim['n']:>5} {sim['gross_mean']:>+8.2f} {sim['net_mean']:>+8.2f} "
                  f"{sim['cost_mean']:>+7.2f} {sim['net_pos']:>4.0f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="AUDUSD", choices=PAIRS + ["all"])
    ap.add_argument("--freq", default="15m", choices=list(FREQ_MAP.keys()))
    args = ap.parse_args()

    if args.symbol == "all":
        for sym in PAIRS:
            run_pair(sym, args.freq)
    else:
        run_pair(args.symbol, args.freq)


if __name__ == "__main__":
    main()

"""Same as fx_ic_diagnose.py but simulates actual non-overlapping trades with real bid/ask.

Trades top-decile predicted-return bars (highest predicted 6h return magnitude).
Reports gross vs net per pair.

Usage:
    uv run python scripts/fx_coint/fx_ic_diagnose_net.py --symbol AUDUSD --freq 15m
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import spearmanr
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


def run_pair(sym: str, freq_label: str) -> None:
    freq, minutes_per_bar, mom_bars, hold_bars = FREQ_MAP[freq_label]
    print(f"\n{'='*65}\nPAIR: {sym}\n{'='*65}")

    df_raw = build_bars(sym, freq_label)
    df = build_panel(df_raw, mom_bars, minutes_per_bar)
    print(f"Usable rows: {len(df):,}")

    feature_cols = ["r_1", "r_sum_2_6", "r_sum_7_24", "rvol_24", "spread_bps",
                    "flow_tick", "flow_ofi", "hour", "dow"]
    split = int(len(df) * 0.7)
    X_train = df.iloc[:split][feature_cols].fillna(0)
    y_train = df.iloc[:split]["target"].to_numpy()
    X_test = df.iloc[split:][feature_cols].fillna(0)
    y_test = df.iloc[split:]["target"].to_numpy()

    scaler = StandardScaler()
    Xs_train = scaler.fit_transform(X_train)
    Xs_test = scaler.transform(X_test)

    model = Ridge(alpha=1.0)
    model.fit(Xs_train, y_train)
    preds = model.predict(Xs_test)

    mask = np.isfinite(y_test) & np.isfinite(preds)
    yt, yp = y_test[mask], preds[mask]
    spr, _ = spearmanr(yt, yp)
    print(f"Overall Spearman={spr:.4f}  N={len(yt):,}")

    # ---- NET SIMULATION ----
    # Trade top-10% predicted-return magnitude, non-overlapping
    n_trade = max(1, len(preds) // 10)
    idx = np.argsort(np.abs(preds))[-n_trade:]
    idx = np.sort(idx)

    test_df = df.iloc[split:].reset_index(drop=True)
    ts = test_df["_ts"].to_numpy()
    mid = test_df["_mid"].to_numpy()
    bid = test_df["_bid"].to_numpy()
    ask = test_df["_ask"].to_numpy()
    side = np.sign(preds)  # chase the predicted sign

    picked = []
    last = -10**9
    for i in idx:
        if i - last >= hold_bars:  # noqa: SIM102
            if (i + 1 + hold_bars) < len(ts) and (ts[i + 1 + hold_bars] - ts[i]) == minutes_per_bar * (1 + hold_bars):
                picked.append(i)
                last = i

    picked = np.array(picked)
    if len(picked) < 5:
        print("Too few tradable predictions.")
        return

    e, x = picked + 1, picked + 1 + hold_bars
    m = mid[picked]
    gross = np.where(
        side[picked] < 0,
        (mid[e] - mid[x]) / m * 1e4,   # short
        (mid[x] - mid[e]) / m * 1e4,   # long
    )
    net = np.where(
        side[picked] < 0,
        (bid[e] - ask[x]) / m * 1e4,
        (bid[x] - ask[e]) / m * 1e4,
    )

    print("\nTop-10% predicted-magnitude trades (non-overlap, real bid/ask):")
    print(f"  n={len(picked)}")
    print(f"  gross mean/med: {gross.mean():+.2f} / {np.median(gross):+.2f} bps  pos%={(gross>0).mean()*100:.0f}%")
    print(f"  net   mean/med: {net.mean():+.2f} / {np.median(net):+.2f} bps  pos%={(net>0).mean()*100:.0f}%")
    print(f"  cost drag     : {(net-gross).mean():+.2f} bps")

    # Also simulate positive-preds-only (long-only overlay)
    pos_idx = np.where(preds > 0)[0]
    if len(pos_idx) >= 100:
        n_pos = max(1, len(pos_idx) // 10)
        top_pos = pos_idx[np.argsort(preds[pos_idx])[-n_pos:]]
        top_pos = np.sort(top_pos)
        picked_pos = []
        last = -10**9
        for i in top_pos:
            if i - last >= hold_bars:  # noqa: SIM102
                if (i + 1 + hold_bars) < len(ts) and (ts[i + 1 + hold_bars] - ts[i]) == minutes_per_bar * (1 + hold_bars):
                    picked_pos.append(i)
                    last = i
        picked_pos = np.array(picked_pos)
        if len(picked_pos) >= 5:
            e, x = picked_pos + 1, picked_pos + 1 + hold_bars
            m = mid[picked_pos]
            gross_pos = (mid[x] - mid[e]) / m * 1e4
            net_pos = (bid[x] - ask[e]) / m * 1e4
            print("\nTop-10% POSITIVE-pred trades (long-only):")
            print(f"  n={len(picked_pos)}")
            print(f"  gross mean/med: {gross_pos.mean():+.2f} / {np.median(gross_pos):+.2f} bps")
            print(f"  net   mean/med: {net_pos.mean():+.2f} / {np.median(net_pos):+.2f} bps")
            print(f"  cost drag     : {(net_pos-gross_pos).mean():+.2f} bps")


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

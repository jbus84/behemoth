"""Same IC diagnostic as fx_ic_diagnose.py but uses XGBoost instead of Ridge.

Usage:
    uv run python scripts/fx_coint/fx_ic_diagnose_xgb.py --symbol AUDUSD --freq 15m
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import xgboost as xgb
from scipy.stats import pearsonr, spearmanr

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
    valid = np.isfinite(feats["r_1"]) & np.isfinite(feats["target"]) & np.isfinite(feats["rvol_24"])
    return feats[valid].reset_index(drop=True)


def run_pair(sym: str, freq_label: str) -> None:
    freq, minutes_per_bar, mom_bars, hold_bars = FREQ_MAP[freq_label]
    print(f"\n{'='*65}\nPAIR: {sym}  |  MODEL: XGBoost  |  FREQ: {freq_label}\n{'='*65}")

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

    dtrain = xgb.DMatrix(X_train, label=y_train)
    dtest = xgb.DMatrix(X_test, label=y_test)

    params = {
        "objective": "reg:squarederror",
        "max_depth": 4,
        "eta": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "eval_metric": "rmse",
        "seed": 42,
    }
    model = xgb.train(params, dtrain, num_boost_round=200, verbose_eval=False)
    preds = model.predict(dtest)

    # Overall IC
    mask = np.isfinite(y_test) & np.isfinite(preds)
    yt, yp = y_test[mask], preds[mask]
    spr, _ = spearmanr(yt, yp)
    prs, _ = pearsonr(yt, yp)
    print(f"\nOverall: Spearman={spr:.4f}  Pearson={prs:.4f}  N={len(yt):,}")

    # Decile analysis
    print("\n--- DECILE CONDITIONAL MEANS ---")
    n_deciles = 10
    dec_edges = np.percentile(yp, np.linspace(0, 100, n_deciles + 1))
    dec_edges[0] -= 1
    dec_edges[-1] += 1
    deciles = np.digitize(yp, dec_edges) - 1
    deciles = np.clip(deciles, 0, n_deciles - 1)

    print(f"{'Decile':>7} {'PredMean':>10} {'ActMean':>10} {'HitRate':>9} {'AbsAct':>9} {'N':>6}")
    for d in range(n_deciles):
        dm = deciles == d
        if dm.sum() < 20:
            continue
        print(f"{d:>7} {yp[dm].mean():>+10.2f} {yt[dm].mean():>+10.2f} {(yt[dm]>0).mean()*100:>8.1f}% {np.abs(yt[dm]).mean():>+9.2f} {dm.sum():>6}")

    # Long-short
    top_mask = deciles == n_deciles - 1
    bot_mask = deciles == 0
    if top_mask.sum() >= 20 and bot_mask.sum() >= 20:
        long_short = yt[top_mask].mean() - yt[bot_mask].mean()
        ls_hit = ((yt[top_mask] > 0).mean() + (yt[bot_mask] < 0).mean()) / 2
        print(f"\nLONG-SHORT: top-bottom spread = {long_short:+.2f} bps  avg hitRate = {ls_hit*100:.1f}%")

    # Asymmetry check
    pos_mask = yp > 0
    if pos_mask.sum() > 100:
        print(f"\nPositive preds: N={pos_mask.sum():,}  meanAct={yt[pos_mask].mean():+.2f}  hit={(yt[pos_mask]>0).mean()*100:.1f}%")
    neg_mask = yp < 0
    if neg_mask.sum() > 100:
        print(f"Negative preds: N={neg_mask.sum():,}  meanAct={yt[neg_mask].mean():+.2f}  hit={(yt[neg_mask]>0).mean()*100:.1f}%")

    # Feature importance
    importance = model.get_score(importance_type="gain")
    imp_sorted = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:5]
    print("\nTop-5 XGB features (gain):")
    for feat, gain in imp_sorted:
        print(f"  {feat:>15s}: {gain:.0f}")


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

"""Diagnose whether IC comes from direction or magnitude prediction.

Decomposes predictions into:
1. Conditional mean return by predicted decile (long-short spread)
2. Positive-prediction-only IC vs negative-prediction-only IC
3. Magnitude correlation: |pred| vs |actual|
4. Conditional hit rate by predicted decile

Usage:
    uv run python scripts/fx_coint/fx_ic_diagnose.py --symbol EURUSD --freq 15m
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import pearsonr, spearmanr
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

    # Overall IC
    mask = np.isfinite(y_test) & np.isfinite(preds)
    yt, yp = y_test[mask], preds[mask]
    spr, _ = spearmanr(yt, yp)
    prs, _ = pearsonr(yt, yp)
    print(f"\nOverall: Spearman={spr:.4f}  Pearson={prs:.4f}  N={len(yt):,}")

    # ---- Decomposition ----
    print("\n--- DECOMPOSITION ---")

    # 1. Magnitude IC: |pred| vs |actual|
    spr_mag, _ = spearmanr(np.abs(yt), np.abs(yp))
    print(f"Magnitude IC  (|pred| vs |actual|): {spr_mag:.4f}")

    # 2. Sign-only IC
    spr_sign, _ = spearmanr(np.sign(yt), np.sign(yp))
    print(f"Sign-only IC  (sign vs sign)       : {spr_sign:.4f}")

    # 3. Conditional: positive predictions only
    pos_mask = yp > 0
    if pos_mask.sum() > 100:
        spr_pos, _ = spearmanr(yt[pos_mask], yp[pos_mask])
        mean_ret_pos = yt[pos_mask].mean()
        hit_pos = (yt[pos_mask] > 0).mean()
        print(f"Positive preds only: N={pos_mask.sum():,}  IC={spr_pos:.4f}  meanRet={mean_ret_pos:+.2f}bps  hitRate={hit_pos*100:.1f}%")
    else:
        print("Positive preds only: insufficient data")

    # 4. Conditional: negative predictions only
    neg_mask = yp < 0
    if neg_mask.sum() > 100:
        spr_neg, _ = spearmanr(yt[neg_mask], yp[neg_mask])
        mean_ret_neg = yt[neg_mask].mean()
        hit_neg = (yt[neg_mask] > 0).mean()
        print(f"Negative preds only: N={neg_mask.sum():,}  IC={spr_neg:.4f}  meanRet={mean_ret_neg:+.2f}bps  hitRate={hit_neg*100:.1f}%")
    else:
        print("Negative preds only: insufficient data")

    # 5. Decile analysis
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

    # Long-short: top decile long, bottom decile short
    top_mask = deciles == n_deciles - 1
    bot_mask = deciles == 0
    if top_mask.sum() >= 20 and bot_mask.sum() >= 20:
        long_short = yt[top_mask].mean() - yt[bot_mask].mean()
        ls_hit = ((yt[top_mask] > 0).mean() + (yt[bot_mask] < 0).mean()) / 2
        print(f"\nLONG-SHORT: top-bottom spread = {long_short:+.2f} bps  avg hitRate = {ls_hit*100:.1f}%")

    # 6. Is it volatility prediction?
    # Compare |pred| vs |actual| to pred_sign × |pred| vs actual
    signed_pred = np.sign(yp) * np.abs(yp)
    spr_signed, _ = spearmanr(yt, signed_pred)
    spr_unsigned, _ = spearmanr(yt, np.abs(yp))
    print(f"\nSigned pred IC   (sgn×|pred| vs actual): {spr_signed:.4f}")
    print(f"Unsigned pred IC (|pred| vs actual)    : {spr_unsigned:.4f}")
    print(f"Ratio signed/unsigned                  : {spr_signed/spr_unsigned if spr_unsigned != 0 else np.nan:.3f}")
    if spr_unsigned > abs(spr_signed) * 2:
        print("  → Signal is PRIMARILY MAGNITUDE (volatility) prediction, NOT direction.")
    elif spr_signed > 0.5 * spr_unsigned:
        print("  → Signal has meaningful DIRECTIONAL component.")
    else:
        print("  → Mixed magnitude + direction; neither dominant.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD", choices=PAIRS + ["all"])
    ap.add_argument("--freq", default="15m", choices=list(FREQ_MAP.keys()))
    args = ap.parse_args()

    if args.symbol == "all":
        for sym in PAIRS:
            run_pair(sym, args.freq)
    else:
        run_pair(args.symbol, args.freq)


if __name__ == "__main__":
    main()

"""Regress next-return magnitude (not just sign) under quantile regimes, at 15m resolution.

Models:
    Ridge / Lasso regression per regime (predict next-6h return in bps)
    + pooled model with dummy-encoded regime bins

Regimes:
    spread_bps tercile, rvol_24 tercile, hour_of_day, DOW, and interactions

Eval:
    Spearman IC, pearson IC, directional accuracy (sign(pred)==sign(actual)),
    and fade/chase PnL when trading strongest-magnitude predictions.

Usage:
    uv run python scripts/fx_coint/fx_quant_regime_reg.py --symbol EURUSD --freq 15m
    uv run python scripts/fx_coint/fx_quant_regime_reg.py --symbol all --freq 15m
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

FREQ_MAP = {
    "15m": ("15m", 15, 24, 12),   # 24-bar mom = 6h, 12-bar hold = 3h
}


def build_bars(sym: str, freq_label: str) -> pd.DataFrame:
    """Aggregate 1m flow bars to target frequency on-the-fly."""
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
    """Add causal features, labels, and regime dummies."""
    mid = df["mid"].to_numpy()
    r = np.empty(len(df))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4

    # Calendar contiguity using datetime64
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

    # Upcoming return (regression target)
    mom = pd.Series(r).rolling(mom_bars, min_periods=mom_bars).sum().shift(-mom_bars).to_numpy()
    feats["target"] = mom

    # ---- Regime assignments (causal: based on past observations) ----
    s = pd.Series(feats["spread_bps"])
    q33_spread = s.rolling(500, min_periods=250).quantile(0.33)
    q67_spread = s.rolling(500, min_periods=250).quantile(0.67)
    feats["regime_spread"] = np.where(s > q67_spread, 2, np.where(s > q33_spread, 1, 0)).astype(int)

    s = pd.Series(feats["rvol_24"])
    q33_vol = s.rolling(500, min_periods=250).quantile(0.33)
    q67_vol = s.rolling(500, min_periods=250).quantile(0.67)
    feats["regime_rvol"] = np.where(s > q67_vol, 2, np.where(s > q33_vol, 1, 0)).astype(int)

    hr = df["bucket"].dt.hour.to_numpy()
    time_reg = np.zeros(len(df), dtype=int)
    time_reg[(hr >= 7) & (hr <= 11)] = 1   # London
    time_reg[(hr >= 12) & (hr <= 16)] = 2  # NY
    time_reg[(hr >= 17) & (hr <= 23)] = 3  # evening
    feats["regime_hour"] = time_reg.astype(int)

    dow = df["bucket"].dt.dayofweek.to_numpy()
    feats["regime_dow"] = np.clip(dow, 0, 5).astype(int)  # 5=Sat/Sun

    # Store prices for PnL
    feats["_mid"] = df["mid"].to_numpy()
    feats["_bid"] = df["bid"].to_numpy()
    feats["_ask"] = df["ask"].to_numpy()
    feats["_ts"] = ts

    valid = (
        np.isfinite(feats["r_1"].to_numpy()) &
        np.isfinite(feats["rvol_24"].to_numpy()) &
        np.isfinite(feats["spread_bps"].to_numpy()) &
        np.isfinite(feats["target"].to_numpy())
    )
    return feats[valid].reset_index(drop=True)


FEATURES_BASE = ["r_1", "r_sum_2_6", "r_sum_7_24", "rvol_24", "spread_bps",
                  "flow_tick", "flow_ofi", "hour", "dow"]
REGIME_COLS = ["regime_spread", "regime_rvol", "regime_hour", "regime_dow"]


def eval_regression(y_true, y_pred) -> dict:
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    yt, yp = y_true[mask], y_pred[mask]
    if len(yt) < 10:
        return {"spearman": np.nan, "pearson": np.nan, "dir_acc": np.nan, "baseline_up": np.nan}
    spr, _ = spearmanr(yt, yp)
    prs, _ = pearsonr(yt, yp)
    dir_acc = np.mean(np.sign(yt) == np.sign(yp))
    baseline_up = np.mean(yt > 0)
    return {"spearman": spr, "pearson": prs, "dir_acc": dir_acc, "baseline_up": baseline_up}


def train_global(df: pd.DataFrame) -> dict:
    """Single pooled model with regime dummies."""
    split = int(len(df) * 0.7)
    train = df.iloc[:split]
    test = df.iloc[split:].reset_index(drop=True)

    # One-hot encode regimes on the full frame
    regime_dummies = pd.get_dummies(df[REGIME_COLS], columns=REGIME_COLS, drop_first=True)
    X = pd.concat([df[FEATURES_BASE], regime_dummies], axis=1)

    X_train = X.iloc[:split].fillna(0)
    y_train = train["target"].to_numpy()
    X_test = X.iloc[split:].fillna(0)
    y_test = test["target"].to_numpy()

    scaler = StandardScaler()
    Xs_train = scaler.fit_transform(X_train)
    Xs_test = scaler.transform(X_test)

    model = Ridge(alpha=1.0)
    model.fit(Xs_train, y_train)
    preds = model.predict(Xs_test)

    ev = eval_regression(y_test, preds)
    print(f"  GLOBAL (pooled+dummies): Spearman={ev['spearman']:.3f}  Pearson={ev['pearson']:.3f}  "
          f"dirAcc={ev['dir_acc']*100:.1f}%  baselineUp={ev['baseline_up']*100:.1f}%")
    return {"model": model, "preds": preds, "test": test, "scaler": scaler, **ev}


def train_per_regime(df: pd.DataFrame, regime_col: str) -> dict:
    """Separate Ridge model per regime bucket."""
    split = int(len(df) * 0.7)
    regimes = sorted(df[regime_col].unique())

    all_preds = np.full(len(df) - split, np.nan)
    all_test = df.iloc[split:].reset_index(drop=True)
    all_true = all_test["target"].to_numpy()

    bucket_results = []
    for reg in regimes:
        tr = df.iloc[:split]
        te = df.iloc[split:]
        tr_reg = tr[tr[regime_col] == reg]
        te_reg = te[te[regime_col] == reg]

        if len(tr_reg) < 200 or len(te_reg) < 50:
            continue

        X_train = tr_reg[FEATURES_BASE].fillna(0)
        y_train = tr_reg["target"].to_numpy()
        X_test = te_reg[FEATURES_BASE].fillna(0)
        y_test = te_reg["target"].to_numpy()

        scaler = StandardScaler()
        Xs_train = scaler.fit_transform(X_train)
        Xs_test = scaler.transform(X_test)

        model = Ridge(alpha=1.0)
        model.fit(Xs_train, y_train)
        preds = model.predict(Xs_test)

        # Map predictions back to global test index
        global_idx = np.where(df.iloc[split:][regime_col].to_numpy() == reg)[0]
        for gi, pi in zip(global_idx, preds):
            all_preds[gi] = pi

        ev = eval_regression(y_test, preds)
        print(f"  {regime_col} bucket {reg}: N_test={len(te_reg):>5}  "
              f"Spearman={ev['spearman']:.3f}  Pearson={ev['pearson']:.3f}  "
              f"dirAcc={ev['dir_acc']*100:.1f}%")
        bucket_results.append({"regime": reg, **ev})

    # Evaluate on test rows that got a prediction
    mask = np.isfinite(all_preds) & np.isfinite(all_true)
    if mask.sum() > 50:
        ev = eval_regression(all_true[mask], all_preds[mask])
        print(f"  {regime_col} COMBINED: Spearman={ev['spearman']:.3f}  Pearson={ev['pearson']:.3f}  "
              f"dirAcc={ev['dir_acc']*100:.1f}%")
    else:
        ev = {"spearman": np.nan, "pearson": np.nan, "dir_acc": np.nan}

    return {"preds": all_preds, "test": all_test, "buckets": bucket_results, **ev}


def simulate(test_df: pd.DataFrame, preds: np.ndarray, direction: str, hold_bars: int, minutes_per_bar: int) -> dict:
    """Trade top-10% highest-confidence predictions.
    Confidence = absolute predicted return magnitude.
    Direction = fade uses -sign(pred), chase uses sign(pred).
    """
    # Align to test_df
    n_trade = max(1, len(preds) // 10)
    idx = np.argsort(np.abs(preds))[-n_trade:]
    idx = np.sort(idx)

    side = np.sign(preds) if direction == "chase" else -np.sign(preds)

    ts = test_df["_ts"].to_numpy()
    mid = test_df["_mid"].to_numpy()
    bid = test_df["_bid"].to_numpy()
    ask = test_df["_ask"].to_numpy()

    picked = []
    last = -10**9
    for i in idx:
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
    print(f"\n{'='*65}\nPAIR: {sym}  |  FREQ: {freq_label}\n{'='*65}")

    df_raw = build_bars(sym, freq_label)
    df = build_panel(df_raw, mom_bars, minutes_per_bar)
    print(f"Total usable rows: {len(df):,}")

    # ---- Global pooled model ----
    print("\n--- POOLED model (regime dummies) ---")
    global_res = train_global(df)
    if "preds" in global_res:
        for mode in ("fade", "chase"):
            sim = simulate(global_res["test"], global_res["preds"], mode, hold_bars, minutes_per_bar)
            if sim["n"] > 0:
                print(f"  {mode.upper():5s}: gross={sim['gross_mean']:+.2f}  net={sim['net_mean']:+.2f}  n={sim['n']}")
            else:
                print(f"  {mode.upper():5s}: insufficient trades")

    # ---- Per-regime separate models ----
    for reg_col in REGIME_COLS:
        print(f"\n--- PER-REGIME: {reg_col} ---")
        res = train_per_regime(df, reg_col)
        if "preds" in res:
            for mode in ("fade", "chase"):
                sim = simulate(res["test"], res["preds"], mode, hold_bars, minutes_per_bar)
                if sim["n"] > 0:
                    print(f"  {mode.upper():5s}: gross={sim['gross_mean']:+.2f}  net={sim['net_mean']:+.2f}  n={sim['n']}")
                else:
                    print(f"  {mode.upper():5s}: insufficient trades")


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

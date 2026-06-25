"""Predict extreme-spike occurrence (top-0.5% |6h momentum|) from recent microstructure.

Labels:  upcoming 6h return magnitude falls in the causal top-0.5% of historical
          |6h momentum| (computed on an expanding / rolling window).
Features: lookback 24h of returns, vol, spread, flow, skew, time effects.
Model:   LogisticRegression (linear, interpretable) + RandomForest (nonlinear).
Eval:    AUC-ROC, avg precision, top-decile lift, and fade-PnL if we only trade
          the highest-confidence predictions.

Usage:
    uv run python scripts/fx_coint/fx_spike_predict.py --symbol EURUSD --freq 1h
    uv run python scripts/fx_coint/fx_spike_predict.py --symbol EURUSD --freq 5m
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCAD"]

FREQ_MAP = {
    "1m": ("1m", 1, 360, 180, 1440),   # mom6h, hold3h, lookback24h in minutes
    "5m": ("5m", 5, 72, 36, 288),       # 24h lookback = 288 bars
    "15m": ("15m", 15, 24, 12, 96),
    "1h": ("1h", 60, 6, 3, 24),
}


def build_bars(sym: str, freq_label: str) -> pd.DataFrame:
    freq, minutes_per_bar, _, _, _ = FREQ_MAP[freq_label]
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    df = pl.read_parquet(src).sort("bucket")
    t = df.with_columns(
        pl.col("mid").log().diff().alias("lr1"),
        ((pl.col("ask") - pl.col("bid")) / pl.col("mid")).alias("relspr"),
    )
    if freq_label == "1m":
        out = t.select([
            pl.col("bucket"), pl.col("mid"), pl.col("bid"), pl.col("ask"),
            pl.col("n_ticks"), pl.col("flow_tick"), pl.col("flow_ofi"),
            (pl.col("lr1").std() * 1e4).alias("rvol_bps"),
            (pl.col("relspr") * 1e4).alias("spread_bps"),
        ]).to_pandas()
        out["bucket"] = pd.to_datetime(out["bucket"])
        return out.sort_values("bucket").reset_index(drop=True)

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


def engineer_features(df: pd.DataFrame, lookback_bars: int) -> pd.DataFrame:
    """Causal feature matrix. Each row t uses data strictly from [t-lookback+1, t]."""
    mid = df["mid"].to_numpy()
    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4

    feats = pd.DataFrame({"bucket": df["bucket"]})
    feats["r_1"] = pd.Series(r).shift(1).to_numpy()
    feats["r_sum_2_6"]   = pd.Series(r).rolling(5).sum().shift(1).to_numpy()
    feats["r_sum_7_24"]  = pd.Series(r).rolling(18).sum().shift(5).to_numpy()
    feats["rvol_24"]     = pd.Series(r).rolling(24).std().shift(1).to_numpy()
    feats["r_max_24"]    = pd.Series(r).rolling(24).max().shift(1).to_numpy()
    feats["r_min_24"]    = pd.Series(r).rolling(24).min().shift(1).to_numpy()
    feats["spread_bps"]  = df["spread_bps"].shift(1).to_numpy()
    feats["flow_tick"]   = df["flow_tick"].shift(1).to_numpy()
    feats["flow_ofi"]    = df["flow_ofi"].shift(1).to_numpy()
    feats["hour"]        = df["bucket"].dt.hour.astype(float)
    feats["dow"]         = df["bucket"].dt.dayofweek.astype(float)
    feats = feats.replace([np.inf, -np.inf], np.nan)
    return feats


def build_labels_and_features(df: pd.DataFrame, mom_bars: int, hold_bars: int,
                               lookback_bars: int, minutes_per_bar: int,
                               pct: float = 0.5) -> pd.DataFrame:
    """Create causal labels: upcoming mom_bars return in top-pct of |mom| historically."""
    mid = df["mid"].to_numpy()
    ts = df["bucket"].to_numpy().astype("datetime64[m]").astype(np.int64)

    # Bar returns in bps
    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    contig = np.empty(len(mid), bool)
    contig[0] = False
    contig[1:] = (ts[1:] - ts[:-1]) == minutes_per_bar
    r[~contig] = np.nan

    # Upcoming momentum (causal: uses future returns, but only for label)
    mom = pd.Series(r).rolling(mom_bars).sum().shift(-mom_bars).to_numpy()
    abs_mom = np.abs(mom)

    # Causal threshold: rolling quantile of |mom| on past 2000 bars
    quant = pd.Series(abs_mom).rolling(2000, min_periods=500).quantile(1 - pct / 100).shift(1).to_numpy()
    is_spike = (abs_mom >= quant).astype(int)

    # Current momentum (causal, known at t)
    mom_current = pd.Series(r).rolling(mom_bars).sum().to_numpy()

    # Features
    feats = engineer_features(df, lookback_bars)
    feats["mom_upcoming"] = mom
    feats["mom_current"] = mom_current
    feats["abs_mom"] = abs_mom
    feats["spike_threshold"] = quant
    feats["is_spike"] = is_spike
    feats["_mid"] = df["mid"].to_numpy()
    feats["_bid"] = df["bid"].to_numpy()
    feats["_ask"] = df["ask"].to_numpy()
    feats["_ts"] = ts

    # Remove rows without valid upcoming mom or insufficient history
    valid = (
        np.isfinite(feats["r_1"].to_numpy()) & np.isfinite(feats["rvol_24"].to_numpy()) &
        np.isfinite(feats["mom_upcoming"].to_numpy()) & np.isfinite(feats["spike_threshold"].to_numpy())
    )
    return feats[valid].reset_index(drop=True)


def evaluate_model(X_train, y_train, X_test, y_test, model, name: str):
    model.fit(X_train, y_train)
    probs = model.predict_proba(X_test)[:, 1]
    preds = model.predict(X_test)

    auc = roc_auc_score(y_test, probs)
    ap = average_precision_score(y_test, probs)
    baseline = y_test.mean()

    # Top-decile lift
    n_top = max(1, len(y_test) // 10)
    top_idx = np.argsort(probs)[-n_top:]
    top_rate = y_test.iloc[top_idx].mean()
    lift = top_rate / (baseline + 1e-12)

    print(f"  {name:>20s}:  AUC={auc:.3f}  AP={ap:.3f}  baseline={baseline*100:.2f}%  top10-rate={top_rate*100:.2f}%  lift={lift:.1f}x")
    return {"probs": probs, "auc": auc, "ap": ap, "lift": lift, "preds": preds}


def simulate(test_df: pd.DataFrame, hold_bars: int, minutes_per_bar: int, direction: str = "fade", side_col: str = "mom_current") -> dict:
    """Trade top-10% predicted-probability spikes; direction = 'fade' or 'chase'.

    side_col controls which column determines trade sign:
        'mom_upcoming' = future direction (CHEAT, for reference only)
        'mom_current'  = past-6h direction, known at signal time (fair)
    fade  = trade opposite to direction sign
    chase = trade in same direction as direction sign
    """
    assert direction in ("fade", "chase")
    assert side_col in ("mom_upcoming", "mom_current")
    probs = test_df["prob"].to_numpy()
    n_trade = max(1, len(probs) // 10)
    idx = np.argsort(probs)[-n_trade:]
    idx = np.sort(idx)

    mid = test_df["_mid"].to_numpy()
    bid = test_df["_bid"].to_numpy()
    ask = test_df["_ask"].to_numpy()
    ts = test_df["_ts"].to_numpy()
    mom = test_df[side_col].to_numpy()
    sgn = np.sign(mom)
    side = -sgn if direction == "fade" else sgn  # trade direction

    # Enforce non-overlap and calendar contiguity
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
    # side < 0 means short entry at e, exit at x
    # side > 0 means long  entry at e, exit at x
    gross = np.where(
        side[picked] < 0,
        (mid[e] - mid[x]) / m * 1e4,   # short gross
        (mid[x] - mid[e]) / m * 1e4,   # long  gross
    )
    net = np.where(
        side[picked] < 0,
        (bid[e] - ask[x]) / m * 1e4,   # short net
        (bid[x] - ask[e]) / m * 1e4,   # long  net
    )
    return {
        "n": len(picked),
        "gross_mean": gross.mean(),
        "gross_med": np.median(gross),
        "net_mean": net.mean(),
        "net_med": np.median(net),
        "gross_pos": (gross > 0).mean() * 100,
        "net_pos": (net > 0).mean() * 100,
        "cost_mean": (net - gross).mean(),
    }


def evaluate_directional(X_train, y_dir_train, X_test, y_dir_test, model, name: str):
    """Evaluate direction prediction (up vs down) on the spike subset."""
    model.fit(X_train, y_dir_train)
    probs = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_dir_test, probs)
    ap = average_precision_score(y_dir_test, probs)
    return {"probs": probs, "auc": auc, "ap": ap}


def run_pair(sym: str, freq_label: str) -> None:
    freq, minutes_per_bar, mom_bars, hold_bars, lookback_bars = FREQ_MAP[freq_label]
    print(f"\n{'='*65}")
    print(f"PAIR: {sym}  |  FREQ: {freq_label}  |  mom={mom_bars}bars  hold={hold_bars}bars")
    print(f"{'='*65}")

    df_raw = build_bars(sym, freq_label)
    df = build_labels_and_features(df_raw, mom_bars, hold_bars, lookback_bars, minutes_per_bar, pct=0.5)
    if len(df) < 500:
        print("Insufficient data after label construction.")
        return

    print(f"Total usable rows: {len(df):,}  |  Spike rate: {df['is_spike'].mean()*100:.2f}%")

    feature_cols = [c for c in df.columns if c not in {
        "bucket", "mom_upcoming", "mom_current", "abs_mom", "spike_threshold", "is_spike",
        "_mid", "_bid", "_ask", "_ts"
    }]
    X = df[feature_cols].fillna(0)
    y = df["is_spike"]

    # Temporal split: 70/30
    split = int(len(df) * 0.7)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    print("\n--- SPIKE OCCURRENCE (Binary) ---")
    lr = LogisticRegression(max_iter=1000, class_weight="balanced", n_jobs=5)
    evaluate_model(X_train_s, y_train, X_test_s, y_test, lr, "LogisticReg")

    rf = RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=50,
                                class_weight="balanced", n_jobs=5, random_state=42)
    rf_res = evaluate_model(X_train, y_train, X_test, y_test, rf, "RandomForest")

    imp = pd.Series(rf.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print("\nTop-5 RF feature importances:")
    for feat, val in imp.head(5).items():
        print(f"  {feat:>15s}: {val:.3f}")

    # ---- Direction Prediction ----
    print("\n--- DIRECTION PREDICTION (Upcoming mom sign) ---")
    mom = df["mom_upcoming"].to_numpy()
    mom_dir = np.full(len(mom), np.nan)
    valid_mom = np.isfinite(mom)
    mom_dir[valid_mom] = (mom[valid_mom] > 0).astype(float)
    y_dir = pd.Series(mom_dir, index=df.index)
    y_dir_train, y_dir_test = y_dir.iloc[:split], y_dir.iloc[split:]

    # Remove rows where direction is unknown
    valid_train = np.isfinite(y_dir_train.to_numpy())
    valid_test = np.isfinite(y_dir_test.to_numpy())

    dir_lr = LogisticRegression(max_iter=1000, class_weight="balanced", n_jobs=5)
    dir_lr.fit(X_train_s[valid_train], y_dir_train[valid_train])
    dir_probs_lr = dir_lr.predict_proba(X_test_s[valid_test])[:, 1]
    auc_lr = roc_auc_score(y_dir_test[valid_test], dir_probs_lr)
    print(f"  LR  direction AUC on ALL test: {auc_lr:.3f}")

    dir_rf = RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=50,
                                   class_weight="balanced", n_jobs=5, random_state=42)
    dir_rf.fit(X_train[valid_train], y_dir_train[valid_train])
    dir_probs_rf = dir_rf.predict_proba(X_test[valid_test])[:, 1]
    auc_rf = roc_auc_score(y_dir_test[valid_test], dir_probs_rf)
    print(f"  RF  direction AUC on ALL test: {auc_rf:.3f}")

    # Direction prediction on the TOP predicted spikes only
    top_n = max(1, len(rf_res["probs"]) // 10)
    top_idx_test = np.argsort(rf_res["probs"])[-top_n:]
    top_dir = y_dir_test.iloc[top_idx_test].to_numpy()
    top_valid = np.isfinite(top_dir)
    if top_valid.sum() >= 20:
        auc_dir_top = roc_auc_score(top_dir[top_valid], dir_probs_rf[top_idx_test][top_valid])
        baseline_dir = top_dir[top_valid].mean()
        pred_dir_acc = ((dir_probs_rf[top_idx_test][top_valid] > 0.5).astype(int) == top_dir[top_valid]).mean()
        print(f"  RF  direction AUC on TOP spikes: {auc_dir_top:.3f}")
        print(f"  Baseline (up-ratio) in top spikes: {baseline_dir*100:.1f}%")
        print(f"  Classifier accuracy on top spikes: {pred_dir_acc*100:.1f}%")

    # ---- Trade simulation ----
    test_df = df.iloc[split:].copy().reset_index(drop=True)
    test_df["prob"] = rf_res["probs"]
    test_df["prob_dir"] = dir_probs_rf

    # Strategy: predict spike, then use mom_current as direction
    for mode in ("fade", "chase"):
        print(f"\n--- {mode.upper()} (fair, spike model + current momentum) ---")
        sim = simulate(test_df, hold_bars, minutes_per_bar, direction=mode, side_col="mom_current")
        if sim["n"] == 0:
            print("  Too few tradable predicted spikes.")
        else:
            print(f"  Trades: {sim['n']}")
            print(f"  gross mean/med: {sim['gross_mean']:+.2f} / {sim['gross_med']:+.2f} bps   pos%: {sim['gross_pos']:.0f}%")
            print(f"  net   mean/med: {sim['net_mean']:+.2f} / {sim['net_med']:+.2f} bps   pos%: {sim['net_pos']:.0f}%")
            print(f"  cost drag     : {sim['cost_mean']:+.2f} bps")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD", choices=PAIRS)
    ap.add_argument("--freq", default="1h", choices=list(FREQ_MAP.keys()))
    args = ap.parse_args()
    run_pair(args.symbol, args.freq)


if __name__ == "__main__":
    main()

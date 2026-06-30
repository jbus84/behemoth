"""
Meta-labeler v2 — improved model for BoostLSS OCO reversion.

Improvements over v1:
  1. New features: oc_abs, oc_x_dir, hour_sin/cos, rolling_sl_rate, xs_mom
  2. Joint cross-pair training (one model, all pairs)
  3. Time-based WFO folds with 48-trade embargo
  4. Isotonic probability calibration
  5. Dynamic per-pair threshold optimising Option B all-in P&L

Usage::

    uv run python scripts/boostlss_xs/meta_label_v2.py \\
        [--trades /tmp/meta_label_out_v2/meta_label_trades.csv] \\
        [--output-dir /tmp/meta_label_out_v3]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

_COMMISSION_RT = 0.70
_N_FOLDS = 5
_EMBARGO = 48  # trades

_BASE_FEATS: list[str] = [
    "sigma_bps", "hour", "dow", "direction",
    "ret_norm", "mom_1", "mom_4", "mom_24",
    "rng_norm", "nt_norm", "oc", "rv", "live_spread",
]
_NEW_FEATS: list[str] = [
    "oc_abs", "oc_x_dir", "hour_sin", "hour_cos",
    "rolling_sl_rate", "xs_mom",
]
_FEAT_COLS_V2 = _BASE_FEATS + _NEW_FEATS


def _engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["oc_abs"]   = df["oc"].abs()
    df["oc_x_dir"] = df["oc"] * df["direction"]
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)

    # rolling_sl_rate: causal 50-trade rolling SL% per pair, shifted by 1
    df["is_sl"] = (df["outcome"] == "sl").astype(float)
    df["rolling_sl_rate"] = (
        df.groupby("sym")["is_sl"]
        .transform(lambda s: s.shift(1).rolling(50, min_periods=10).mean())
    )

    # xs_mom: this pair's ret_norm minus cross-pair mean at same hour bucket
    df["ts_hour"] = df["ts"].str[:13]  # YYYY-MM-DD HH
    hour_mean = df.groupby("ts_hour")["ret_norm"].transform("mean")
    df["xs_mom"] = df["ret_norm"] - hour_mean

    return df


def _option_b_all_in(df: pd.DataFrame, threshold: float, prob_col: str = "prob_tp_v2") -> float:
    acc = df[df[prob_col] >= threshold]
    rej = df[df[prob_col] <  threshold]
    rej_cost = rej["fill_spread"] + _COMMISSION_RT
    return (acc["maker_net"].sum() + (-rej_cost).sum()) / len(df) if len(df) else 0.0


def _optimal_threshold(df: pd.DataFrame, prob_col: str = "prob_tp_v2") -> float:
    best_thr, best_val = 0.5, -np.inf
    for thr in np.arange(0.45, 0.85, 0.01):
        val = _option_b_all_in(df, thr, prob_col)
        if val > best_val:
            best_val, best_thr = val, thr
    return best_thr


def fit_v2(df: pd.DataFrame) -> pd.DataFrame:
    """Joint cross-pair time-WFO with calibration. Returns df with prob_tp_v2."""
    df = df.dropna(subset=_FEAT_COLS_V2).copy().sort_values("ts").reset_index(drop=True)
    n  = len(df)
    fs = n // (_N_FOLDS + 1)

    X  = df[_FEAT_COLS_V2].values
    y  = df["label"].values

    oos_prob = np.full(n, np.nan)
    aucs: list[float] = []

    for fi in range(_N_FOLDS):
        tr_end   = fs * (fi + 1)
        te_start = tr_end + _EMBARGO
        te_end   = min(te_start + fs, n)
        if te_end <= te_start:
            break

        X_te, y_te = X[te_start:te_end], y[te_start:te_end]

        base_clf = HistGradientBoostingClassifier(
            max_iter=300, max_depth=5, learning_rate=0.05,
            min_samples_leaf=20, random_state=42,
        )
        # Isotonic calibration on a held-out slice of the training set
        cal_size = max(500, tr_end // 5)
        cal_end  = tr_end
        cal_start = cal_end - cal_size
        X_fit, y_fit = X[:cal_start], y[:cal_start]
        X_cal, y_cal = X[cal_start:cal_end], y[cal_start:cal_end]

        base_clf.fit(X_fit, y_fit)
        raw_cal = base_clf.predict_proba(X_cal)[:, 1]
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(raw_cal, y_cal)

        raw_te = base_clf.predict_proba(X_te)[:, 1]
        probs  = iso.predict(raw_te)
        oos_prob[te_start:te_end] = probs
        aucs.append(roc_auc_score(y_te, probs))

    mask = ~np.isnan(oos_prob)
    df_oos = df[mask].copy()
    df_oos["prob_tp_v2"] = oos_prob[mask]
    df_oos["mean_auc_v2"] = float(np.mean(aucs))
    return df_oos


def compare(df_v1: pd.DataFrame, df_v2: pd.DataFrame, threshold: float = 0.55) -> None:
    print(f"\n{'═'*70}")
    print("V1 vs V2 COMPARISON")
    print(f"{'═'*70}")

    # V1 numbers (using existing prob_tp column)
    v1_auc   = roc_auc_score(df_v1["label"], df_v1["prob_tp"])
    v1_brier = brier_score_loss(df_v1["label"], df_v1["prob_tp"])
    v1_b55   = _option_b_all_in(df_v1, threshold, "prob_tp")

    # V2 numbers
    v2_auc   = roc_auc_score(df_v2["label"], df_v2["prob_tp_v2"])
    v2_brier = brier_score_loss(df_v2["label"], df_v2["prob_tp_v2"])
    v2_b55   = _option_b_all_in(df_v2, threshold, "prob_tp_v2")

    print(f"\n  {'Metric':<30} {'V1':>10} {'V2':>10} {'Delta':>10}")
    print(f"  {'-'*60}")
    print(f"  {'AUC (OOS)':<30} {v1_auc:>10.4f} {v2_auc:>10.4f} {v2_auc-v1_auc:>+10.4f}")
    print(f"  {'Brier score (lower=better)':<30} {v1_brier:>10.4f} {v2_brier:>10.4f} {v2_brier-v1_brier:>+10.4f}")
    print(f"  {'Option B all-in @0.55':<30} {v1_b55:>10.4f} {v2_b55:>10.4f} {v2_b55-v1_b55:>+10.4f}")

    # Dynamic threshold
    opt_thr = _optimal_threshold(df_v2)
    v2_opt  = _option_b_all_in(df_v2, opt_thr, "prob_tp_v2")
    v1_opt_thr = _optimal_threshold(df_v1.rename(columns={"prob_tp": "prob_tp_v2"}))
    v1_opt  = _option_b_all_in(df_v1.rename(columns={"prob_tp": "prob_tp_v2"}),
                                v1_opt_thr, "prob_tp_v2")
    print(f"\n  V1 optimal threshold: {v1_opt_thr:.2f}  →  B all-in {v1_opt:+.4f} bps")
    print(f"  V2 optimal threshold: {opt_thr:.2f}  →  B all-in {v2_opt:+.4f} bps")

    print("\n── V2 per-pair dynamic threshold ──")
    print(f"  {'Pair':<8}  {'Opt thr':>8}  {'B all-in':>10}  {'n_all':>6}  {'kept%':>7}")
    for sym, g in df_v2.groupby("sym"):
        thr_sym = _optimal_threshold(g)
        b       = _option_b_all_in(g, thr_sym, "prob_tp_v2")
        kept    = (g["prob_tp_v2"] >= thr_sym).mean()
        print(f"  {sym:<8}  {thr_sym:>8.2f}  {b:>+10.4f}  {len(g):>6}  {kept:>6.1%}")

    print(f"\n── V2 by year (dynamic threshold={opt_thr:.2f}, pooled) ──")
    df_v2 = df_v2.copy()
    df_v2["year"] = df_v2["ts"].str[:4]
    df_v2["ob_net"] = df_v2.apply(
        lambda r: r["maker_net"] if r["prob_tp_v2"] >= opt_thr
        else -(r["fill_spread"] + _COMMISSION_RT), axis=1
    )
    for yr, g in df_v2.groupby("year"):
        print(f"  {yr}  n={len(g):>5}  ob_net={g.ob_net.mean():>+6.3f}  "
              f"win%={(g.ob_net > 0).mean():.3f}")

    print("\n── V2 threshold sweep (all-in per fill) ──")
    print(f"  {'Thresh':>7}  {'kept%':>6}  {'B all-in':>10}  {'TP% kept':>9}")
    for thr in np.arange(0.45, 0.86, 0.05):
        sub  = df_v2[df_v2["prob_tp_v2"] >= thr]
        b    = _option_b_all_in(df_v2, thr, "prob_tp_v2")
        kept = len(sub) / len(df_v2)
        tp   = sub["label"].mean() if len(sub) else 0
        print(f"  {thr:>7.2f}  {kept:>5.1%}  {b:>+10.4f}  {tp:>8.1%}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--trades",     default="/tmp/meta_label_out_v2/meta_label_trades.csv")
    p.add_argument("--output-dir", default="/tmp/meta_label_out_v3")
    args = p.parse_args()

    print("Loading trades...", flush=True)
    df_raw = pd.read_csv(args.trades)
    df_raw["label"] = (df_raw["outcome"] == "tp").astype(int)
    print(f"  {len(df_raw):,} trades, {df_raw.sym.nunique()} pairs, "
          f"years {df_raw.ts.str[:4].min()}–{df_raw.ts.str[:4].max()}")

    print("\nEngineering features...", flush=True)
    df_feat = _engineer_features(df_raw)
    missing = df_feat[_FEAT_COLS_V2].isna().mean()
    print(f"  NaN rates: {missing[missing > 0.01].to_dict()}")

    print("\nFitting V2 (joint cross-pair time-WFO + calibration)...", flush=True)
    df_v2 = fit_v2(df_feat)
    print(f"  OOS trades: {len(df_v2):,}  mean AUC: {df_v2.mean_auc_v2.mean():.4f}")

    # V1 OOS subset (same rows as v2 for fair comparison)
    df_v1_oos = df_raw[df_raw.index.isin(df_v2.index)].copy()

    compare(df_v1_oos, df_v2)

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    out = args.output_dir + "/meta_label_trades_v2.csv"
    df_v2.to_csv(out, index=False)
    print(f"\nTrade log → {out}")
    print("✓ Done.")

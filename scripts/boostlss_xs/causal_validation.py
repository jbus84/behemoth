"""
Causal validation of the meta-labeler `oc` signal.

Three tests to establish whether open-to-close of the trigger bar is a
genuinely structural predictor of OCO reversion outcomes, or a regime artefact.

  Test 1 — Placebo shuffle:
    AUC with real `oc` vs AUC with `oc` randomly shuffled within-pair.
    A real signal should degrade meaningfully when destroyed.

  Test 2 — Cross-pair transfer:
    Train on 10 pairs, test on 11 unseen pairs with zero retraining.
    A structural signal transfers; a pair-specific one does not.

  Test 3 — Sub-period stability:
    Fit separate meta-labelers on pre-2023 and post-2023 trades.
    Report AUC and `oc` permutation importance rank in each half.

Usage::

    uv run python scripts/boostlss_xs/causal_validation.py \\
        [--trades /tmp/meta_label_out_v2/meta_label_trades.csv]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score

_FEAT_COLS: list[str] = [
    "sigma_bps", "hour", "dow", "direction",
    "ret_norm", "mom_1", "mom_4", "mom_24",
    "rng_norm", "nt_norm", "oc", "rv", "live_spread",
]
_N_FOLDS = 5
_GROUP_A = {"EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF",
            "AUDUSD", "EURAUD", "EURCHF", "EURGBP", "EURJPY"}
_GROUP_B = {"EURNZD", "GBPAUD", "GBPCHF", "GBPJPY", "GBPNZD",
            "AUDCAD", "AUDJPY", "AUDNZD", "CADJPY", "CHFJPY", "NZDUSD"}


def _wfo_auc(df: pd.DataFrame, feat_cols: list[str]) -> float:
    """Causal WFO AUC, splitting by trade count within each pair then pooling."""
    oos_rows: list[pd.DataFrame] = []
    for _, g in df.groupby("sym"):
        g = g.dropna(subset=feat_cols).copy()
        if len(g) < _N_FOLDS * 20:
            continue
        X, y = g[feat_cols].values, g["label"].values
        n, fs = len(g), len(g) // (_N_FOLDS + 1)
        probs = np.full(n, np.nan)
        for fi in range(_N_FOLDS):
            tr_end = fs * (fi + 1)
            te_end = min(tr_end + fs, n)
            clf = HistGradientBoostingClassifier(max_iter=200, max_depth=4, random_state=42)
            clf.fit(X[:tr_end], y[:tr_end])
            probs[tr_end:te_end] = clf.predict_proba(X[tr_end:te_end])[:, 1]
        mask = ~np.isnan(probs)
        row = g[mask].copy()
        row["prob"] = probs[mask]
        oos_rows.append(row)
    oos = pd.concat(oos_rows)
    return roc_auc_score(oos["label"], oos["prob"])


def test1_placebo(df: pd.DataFrame) -> None:
    print("\n── Test 1: Placebo shuffle of `oc` ──")
    auc_real = _wfo_auc(df, _FEAT_COLS)

    df_shuf = df.copy()
    rng = np.random.default_rng(42)
    for _sym, g in df_shuf.groupby("sym"):
        idx = g.index
        df_shuf.loc[idx, "oc"] = rng.permutation(g["oc"].values)

    auc_shuf = _wfo_auc(df_shuf, _FEAT_COLS)
    print(f"  Real AUC:     {auc_real:.4f}")
    print(f"  Shuffled AUC: {auc_shuf:.4f}")
    print(f"  Delta:        {auc_real - auc_shuf:+.4f}")


def test2_cross_pair(df: pd.DataFrame) -> None:
    print("\n── Test 2: Cross-pair transfer ──")
    train = df[df.sym.isin(_GROUP_A)].dropna(subset=_FEAT_COLS).copy()
    test  = df[df.sym.isin(_GROUP_B)].dropna(subset=_FEAT_COLS).copy()

    clf = HistGradientBoostingClassifier(max_iter=200, max_depth=4, random_state=42)
    clf.fit(train[_FEAT_COLS].values, train["label"].values)
    probs = clf.predict_proba(test[_FEAT_COLS].values)[:, 1]
    auc = roc_auc_score(test["label"].values, probs)

    baseline = _wfo_auc(df, _FEAT_COLS)
    print(f"  WFO baseline AUC (all pairs): {baseline:.4f}")
    print(f"  Cross-pair transfer AUC:      {auc:.4f}")
    print(f"  Train pairs: {sorted(_GROUP_A)}")
    print(f"  Test pairs:  {sorted(_GROUP_B)}")


def test3_subperiod(df: pd.DataFrame) -> None:
    print("\n── Test 3: Sub-period stability ──")
    df = df.copy()
    df["year"] = df["ts"].str[:4].astype(int)
    pre  = df[df.year <= 2022].copy()
    post = df[df.year >= 2023].copy()

    for label, sub in [("Pre-2023  (2020–2022)", pre), ("Post-2023 (2023–2025)", post)]:
        auc = _wfo_auc(sub, _FEAT_COLS)

        # Permutation importance on full-period model for this subset
        sub_clean = sub.dropna(subset=_FEAT_COLS)
        clf = HistGradientBoostingClassifier(max_iter=200, max_depth=4, random_state=42)
        clf.fit(sub_clean[_FEAT_COLS].values, sub_clean["label"].values)
        pi = permutation_importance(
            clf, sub_clean[_FEAT_COLS].values, sub_clean["label"].values,
            n_repeats=10, random_state=42, scoring="roc_auc",
        )
        order = np.argsort(pi.importances_mean)[::-1]
        oc_rank = int(np.where(order == _FEAT_COLS.index("oc"))[0][0]) + 1
        oc_imp  = pi.importances_mean[_FEAT_COLS.index("oc")]

        print(f"\n  {label}")
        print(f"    OOS AUC:        {auc:.4f}")
        print(f"    `oc` rank:      #{oc_rank} of {len(_FEAT_COLS)}")
        print(f"    `oc` perm imp:  {oc_imp:.4f}")
        print("    Top-3 features: "
              + ", ".join(f"{_FEAT_COLS[i]} ({pi.importances_mean[i]:.4f})"
                          for i in order[:3]))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--trades", default="/tmp/meta_label_out_v2/meta_label_trades.csv")
    args = p.parse_args()

    df = pd.read_csv(args.trades)
    df["label"] = (df["outcome"] == "tp").astype(int)

    print(f"Loaded {len(df):,} trades across {df.sym.nunique()} pairs")
    print(f"Years: {df.ts.str[:4].min()} – {df.ts.str[:4].max()}")
    print(f"Label balance: {df.label.mean():.1%} TP")

    test1_placebo(df)
    test2_cross_pair(df)
    test3_subperiod(df)

    print("\n✓ Causal validation complete.")

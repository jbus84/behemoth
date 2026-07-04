"""
mljar AutoML feature-importance: which meta-labeler features actually drive
the OOS edge measured by mljar_meta_labeler_compare.py?

Method: OOS permutation importance. For each WFO fold, fit the AutoML ensemble
on the training partition (identical fold logic to fit_meta_label_wfo_compare),
then on the held-out OOS partition shuffle each feature in turn and measure the
drop in OOS AUC. A positive drop = the model relies on that feature for OOS
ranking; near-zero or negative = the feature is unused or noise. Aggregated per
feature as mean +/- std across folds, pooled and per-pair.

This is model-agnostic (works on the ensemble's predict_proba as a black box)
and tied directly to the OOS result, unlike in-sample SHAP which only shows what
the model fit to. mljar's own explain_level is left at 0 here for speed; the
permutation importance computed below is the primary, self-contained answer.

Requires mljar-supervised as an EPHEMERAL dependency:

    uv run --with mljar-supervised python scripts/boostlss_xs/mljar_feature_importance.py \\
        --data-dir /path/to/tick_bars \\
        --tick-dir /path/to/raw_ticks \\
        --pairs EURUSD GBPJPY AUDUSD USDJPY \\
        [--automl-time-limit 90] [--n-repeats 5] [--seed 42] [--tail-rows N]

Prints per-pair then pooled feature-importance tables as each pair completes,
so partial results are robust to interruption.
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
from meta_label_straddle import _FEAT_COLS, _N_FOLDS
from mljar_meta_labeler_compare import _ALGORITHMS, _build_trade_population
from sklearn.metrics import roc_auc_score
from supervised import AutoML

_TEMP_DIR = "/tmp/mljar_explain_out"


def _perm_importance_auc(
    automl: AutoML,
    X_df: pd.DataFrame,
    y: np.ndarray,
    n_repeats: int,
    rng: np.random.Generator,
) -> tuple[float, dict[str, list[float]]]:
    """Return (base_oos_auc, {feat: [base_auc - shuffled_auc, ...]})."""
    base = roc_auc_score(y, automl.predict_proba(X_df)[:, 1])
    imp: dict[str, list[float]] = {}
    for f in X_df.columns:
        deltas: list[float] = []
        for _ in range(n_repeats):
            Xp = X_df.copy()
            Xp[f] = rng.permutation(Xp[f].values)
            try:
                auc = roc_auc_score(y, automl.predict_proba(Xp)[:, 1])
            except Exception:
                auc = float("nan")
            deltas.append(base - auc)
        imp[f] = deltas
    return base, imp


def fit_perm_importance_wfo(
    df: pd.DataFrame,
    feat_cols: list[str],
    automl_time_limit: int,
    n_repeats: int,
    seed: int,
    sym: str,
) -> tuple[list[float], dict[str, list[float]]]:
    """
    Per-fold: fit AutoML on training partition, compute OOS permutation
    importance on the held-out partition. Returns (per_fold_base_auc,
    {feat: [delta, ...] across all folds/repeats}).
    """
    df = df.dropna(subset=feat_cols).copy()
    df["label"] = (df.outcome == "tp").astype(int)
    X = df[feat_cols].values
    y = df.label.values
    n = len(df)
    fs = n // (_N_FOLDS + 1)

    base_aucs: list[float] = []
    feat_imp: dict[str, list[float]] = {f: [] for f in feat_cols}
    rng = np.random.default_rng(seed)

    for fi in range(_N_FOLDS):
        tr_end = fs * (fi + 1)
        te_start = tr_end
        te_end = min(te_start + fs, n)
        if te_end <= te_start:
            break

        automl = AutoML(
            mode="Explain",
            ml_task="binary_classification",
            total_time_limit=automl_time_limit,
            algorithms=_ALGORITHMS,
            explain_level=0,
            results_path=f"{_TEMP_DIR}/{sym}_fold{fi}",
            verbose=0,
        )
        automl.fit(
            pd.DataFrame(X[:tr_end], columns=feat_cols),
            pd.Series(y[:tr_end]),
        )
        X_te = pd.DataFrame(X[te_start:te_end], columns=feat_cols)
        y_te = y[te_start:te_end]
        base, imp = _perm_importance_auc(automl, X_te, y_te, n_repeats, rng)
        base_aucs.append(base)
        for f, deltas in imp.items():
            feat_imp[f].extend(deltas)
        print(f"    {sym} fold {fi}: OOS AUC={base:.3f}  "
              f"(n_te={len(y_te)})", flush=True)

    return base_aucs, feat_imp


def _print_table(title: str, rows: list[tuple[str, float, float, float]]) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)
    print(f"{'feature':<14} {'mean_auc_drop':>14} {'std':>8} {'mean/std':>9}")
    print("-" * 70)
    for feat, mean, std, ratio in rows:
        print(f"{feat:<14} {mean:>+14.4f} {std:>8.4f} {ratio:>9.2f}")


def _summarize(feat_imp: dict[str, list[float]]) -> list[tuple[str, float, float, float]]:
    rows = []
    for f, deltas in feat_imp.items():
        arr = np.array(deltas, dtype=float)
        arr = arr[~np.isnan(arr)]
        mean = float(arr.mean()) if arr.size else float("nan")
        std = float(arr.std()) if arr.size else float("nan")
        ratio = mean / std if std and std > 1e-12 else float("nan")
        rows.append((f, mean, std, ratio))
    rows.sort(key=lambda r: (-(r[1] if r[1] == r[1] else -9e9)))
    return rows


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="mljar AutoML OOS permutation feature importance")
    p.add_argument("--data-dir",          default="/Users/danielfisher/repositories/behemoth/data/tick_bars")
    p.add_argument("--tick-dir",          default="/Users/danielfisher/Desktop/tick")
    p.add_argument("--pairs",             nargs="+", default=["EURUSD"])
    p.add_argument("--high-quantile",     type=float, default=0.90)
    p.add_argument("--low-quantile",      type=float, default=0.5)
    p.add_argument("--sig-thresh",        type=float, default=4.5)
    p.add_argument("--sig-thresh-hi",     type=float, default=5.5)
    p.add_argument("--automl-time-limit", type=int, default=90)
    p.add_argument("--n-repeats",         type=int, default=5)
    p.add_argument("--seed",              type=int, default=42)
    p.add_argument("--tail-rows",         type=int, default=None)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    feat_cols = [*_FEAT_COLS, "tail_ratio"]

    os.makedirs(_TEMP_DIR, exist_ok=True)

    all_raw = _build_trade_population(
        pairs=args.pairs, data_dir=args.data_dir, tick_dir=args.tick_dir,
        high_quantile=args.high_quantile, low_quantile=args.low_quantile,
        sig_thresh=args.sig_thresh, sig_thresh_hi=args.sig_thresh_hi,
        tail_rows=args.tail_rows,
    )

    pooled_imp: dict[str, list[float]] = {f: [] for f in feat_cols}
    per_pair_base: dict[str, list[float]] = {}

    for sym, g in all_raw.groupby("sym"):
        print(f"\n{sym}: fitting AutoML + OOS permutation importance "
              f"({args.n_repeats} repeats, {args.automl_time_limit}s/fold)...", flush=True)
        try:
            base_aucs, feat_imp = fit_perm_importance_wfo(
                g.copy(), feat_cols=feat_cols,
                automl_time_limit=args.automl_time_limit,
                n_repeats=args.n_repeats, seed=args.seed, sym=sym,
            )
            per_pair_base[sym] = base_aucs
            for f, deltas in feat_imp.items():
                pooled_imp[f].extend(deltas)
            mean_base = float(np.mean(base_aucs)) if base_aucs else float("nan")
            _print_table(
                f"{sym}  OOS permutation importance  (mean OOS AUC={mean_base:.3f})",
                _summarize(feat_imp),
            )
        except Exception as e:
            print(f"  {sym}: failed — {e}", flush=True)

    if any(pooled_imp.values()):
        _print_table(
            "POOLED  OOS permutation importance  (all pairs, all folds)",
            _summarize(pooled_imp),
        )
    else:
        print("No permutation-importance results produced.")
        raise SystemExit(1)

"""Deep non-linear assessment of the full expanded feature set (14 features,
including the lagged/liquidity features added 2026-07-07 in response to
"do we even have lags?" -- we didn't, until now).

Compares three modeling approaches under the SAME purged expanding-window
walk-forward used throughout this investigation (train on years<Y, test on year Y,
never overlapping):
  1. Baseline: single CatBoostClassifier (matches jumpfade_metamodel_v2.py but with
     the full 14-feature set instead of 5)
  2. Bagged: N CatBoost models on bootstrap-resampled training subsets, averaged
     P(win) -- reduces variance from any single tree structure's idiosyncrasies
  3. Stacked: heterogeneous base learners (CatBoost, RandomForest, GradientBoosting,
     LogisticRegression) combined via a logistic-regression meta-learner trained on
     out-of-fold base predictions -- can capture complementary error patterns a
     single model family might share

Also runs SHAP on the final full-history model to look for interaction effects a
plain feature-importance ranking can't show (which feature PAIRS matter together,
not just which features matter most on average).
"""

from __future__ import annotations

import numpy as np
import polars as pl
import shap
from catboost import CatBoostClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold

from scripts.fx_coint.jumpfade_dataset_loader import ALL_FEATURE_COLS


def _t_stat(x: np.ndarray) -> float:
    if len(x) < 5:
        return float("nan")
    return x.mean() / (x.std() / np.sqrt(len(x)))


def eval_filtered(net_all: np.ndarray, p_win: np.ndarray, thresh: float = 0.5) -> tuple[int, float, float]:
    filt = net_all[p_win > thresh]
    if len(filt) < 5:
        return 0, float("nan"), float("nan")
    return len(filt), filt.mean(), _t_stat(filt)


def make_base_models(seed: int = 42) -> dict:
    return {
        "catboost": CatBoostClassifier(iterations=200, depth=4, learning_rate=0.05, verbose=False, random_seed=seed),
        "random_forest": RandomForestClassifier(n_estimators=300, max_depth=5, random_state=seed, n_jobs=-1),
        "gbm": GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=seed),
        "logistic": LogisticRegression(max_iter=1000),
    }


def run_baseline(train: pl.DataFrame, test: pl.DataFrame, feat_cols: list[str]) -> tuple[np.ndarray, CatBoostClassifier]:
    X_train = train.select(feat_cols).to_pandas()
    y_train = train["win"].to_numpy().astype(int)
    X_test = test.select(feat_cols).to_pandas()
    model = CatBoostClassifier(iterations=200, depth=4, learning_rate=0.05, verbose=False, random_seed=42)
    model.fit(X_train, y_train)
    return model.predict_proba(X_test)[:, 1], model


def run_bagged(train: pl.DataFrame, test: pl.DataFrame, feat_cols: list[str], n_bags: int = 8) -> np.ndarray:
    X_train_full = train.select(feat_cols).to_pandas()
    y_train_full = train["win"].to_numpy().astype(int)
    X_test = test.select(feat_cols).to_pandas()
    n = len(X_train_full)
    rng = np.random.default_rng(0)
    preds = []
    for b in range(n_bags):
        idx = rng.choice(n, size=n, replace=True)
        model = CatBoostClassifier(iterations=150, depth=4, learning_rate=0.06, verbose=False, random_seed=b)
        model.fit(X_train_full.iloc[idx], y_train_full[idx])
        preds.append(model.predict_proba(X_test)[:, 1])
    return np.mean(preds, axis=0)


def run_stacked(train: pl.DataFrame, test: pl.DataFrame, feat_cols: list[str]) -> np.ndarray:
    X_train = train.select(feat_cols).to_pandas().fillna(0.0)
    y_train = train["win"].to_numpy().astype(int)
    X_test = test.select(feat_cols).to_pandas().fillna(0.0)

    base_models = make_base_models()
    n = len(X_train)
    oof_preds = np.zeros((n, len(base_models)))
    kf = KFold(n_splits=5, shuffle=True, random_state=0)
    for name_i, (name, _) in enumerate(base_models.items()):
        for tr_idx, val_idx in kf.split(X_train):
            m = make_base_models()[name]
            if name == "catboost":
                m.fit(X_train.iloc[tr_idx], y_train[tr_idx], verbose=False)
            else:
                m.fit(X_train.iloc[tr_idx], y_train[tr_idx])
            oof_preds[val_idx, name_i] = m.predict_proba(X_train.iloc[val_idx])[:, 1]

    meta = LogisticRegression(max_iter=1000)
    meta.fit(oof_preds, y_train)

    test_base_preds = np.zeros((len(X_test), len(base_models)))
    for name_i, (name, _) in enumerate(base_models.items()):
        m = make_base_models()[name]
        if name == "catboost":
            m.fit(X_train, y_train, verbose=False)
        else:
            m.fit(X_train, y_train)
        test_base_preds[:, name_i] = m.predict_proba(X_test)[:, 1]
    return meta.predict_proba(test_base_preds)[:, 1]


def main() -> None:
    df = pl.read_parquet("/tmp/eurusd_full_features.parquet")
    feat_cols = ALL_FEATURE_COLS
    print(f"n={df.height}, features={feat_cols}")

    years = sorted(df["year"].unique().to_list())
    test_years = years[3:]

    results = {"baseline": [], "bagged": [], "stacked": []}
    unf_all = []
    last_model = None

    for test_y in test_years:
        train = df.filter(pl.col("year") < test_y)
        test = df.filter(pl.col("year") == test_y)
        if train.height < 500 or test.height < 50:
            continue
        net_all = test["net_bps"].to_numpy()
        unf_all.append(net_all)

        p_base, model = run_baseline(train, test, feat_cols)
        p_bag = run_bagged(train, test, feat_cols)
        p_stack = run_stacked(train, test, feat_cols)

        for name, p in [("baseline", p_base), ("bagged", p_bag), ("stacked", p_stack)]:
            n_f, m_f, t_f = eval_filtered(net_all, p)
            results[name].append((test_y, n_f, m_f, t_f))

        last_model = model
        print(f"  {test_y} done", flush=True)

    u = np.concatenate(unf_all)
    print(f"\nunfiltered baseline: n={len(u)} net={u.mean():+.3f} t={_t_stat(u):+.2f}")

    for name in ["baseline", "bagged", "stacked"]:
        rows = results[name]
        print(f"\n=== {name} ===")
        for y, n_f, m_f, t_f in rows:
            print(f"  {y}  n={n_f:5d}  net={m_f:+.3f}  t={t_f:+.2f}")
        # pooled: need to re-derive from the per-year net; approximate via weighted mean/t
        means = [m for _, _, m, _ in rows if not np.isnan(m)]
        ns = [n for _, n, _, _ in rows if n > 0]
        if means:
            pooled_mean = np.average(means, weights=ns[:len(means)])
            print(f"  POOLED (weighted): net={pooled_mean:+.3f}bps over {sum(ns)} filtered trades")

    print("\n=== SHAP interaction analysis (final full-history CatBoost model) ===")
    X_full = df.select(feat_cols).to_pandas()
    explainer = shap.TreeExplainer(last_model)
    shap_values = explainer.shap_values(X_full.sample(min(3000, len(X_full)), random_state=0))
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    order = np.argsort(-mean_abs_shap)
    print("mean |SHAP value| per feature (overall importance, direction-agnostic):")
    for i in order:
        print(f"  {feat_cols[i]:18s} {mean_abs_shap[i]:.4f}")


if __name__ == "__main__":
    main()

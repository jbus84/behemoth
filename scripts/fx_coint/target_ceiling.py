"""Stage A — intrinsic-ceiling estimators (own-history info set, bracketed).

The ceiling is reported as an interval, not a point:
  lower bound  = flexible model (gradient boosting) on own-history lags, purged+embargoed CV
  upper estim. = Kraskov k-NN mutual information on the lag embedding
Both compared to a block-permutation null so we know what "zero" looks like.

Self-test: `uv run python scripts/fx_coint/target_ceiling.py`
"""
from __future__ import annotations

import numpy as np
from scipy import stats
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.feature_selection import mutual_info_classif, mutual_info_regression
from sklearn.metrics import balanced_accuracy_score


def lag_embedding(returns: np.ndarray, lags: tuple[int, ...]) -> np.ndarray:
    r = np.asarray(returns, dtype=float)
    n = r.size
    cols = []
    for L in lags:
        ret_lag = np.full(n, np.nan)
        ret_lag[L:] = r[:-L] if L > 0 else r
        vol = np.full(n, np.nan)
        for t in range(L, n):
            w = r[t - L:t]
            vol[t] = w.std() if w.size else np.nan
        cols.append(ret_lag)
        cols.append(vol)
    return np.column_stack(cols)


def purged_embargo_splits(n: int, t1: np.ndarray, n_splits: int,
                          embargo: int) -> list[tuple[np.ndarray, np.ndarray]]:
    t1 = np.asarray(t1)
    bounds = np.linspace(0, n, n_splits + 1, dtype=int)
    splits = []
    for i in range(1, n_splits):
        te_start, te_end = bounds[i], bounds[i + 1]
        test = np.arange(te_start, te_end)
        cand = np.arange(0, te_start)
        # purge train labels whose end t1 reaches into the test block; the embargo
        # extends the protected zone `embargo` bars before the test start so labels
        # ending just before the test set can't leak through overlapping windows.
        keep = t1[cand] < (te_start - embargo)
        train = cand[keep]
        if train.size and test.size:
            splits.append((train, test))
    return splits


def _drop_nan(X: np.ndarray, y: np.ndarray):
    ok = np.isfinite(X).all(axis=1) & np.isfinite(np.asarray(y, dtype=float))
    return X[ok], np.asarray(y)[ok], ok


def model_lower_bound(X: np.ndarray, y: np.ndarray, t1: np.ndarray, kind: str,
                      n_splits: int = 4, embargo: int = 10) -> float:
    """Out-of-fold skill estimate: Spearman IC (continuous) or balanced accuracy (barrier).

    Returns the average predictive skill of a gradient-boosted model trained on
    own-history lags (X) to predict y, evaluated under purged+embargoed forward-chaining
    cross-validation. NaN rows are dropped per-fold.
    """
    n = len(y)
    scores = []
    for tr, te in purged_embargo_splits(n, t1, n_splits, embargo):
        Xtr, ytr, _ = _drop_nan(X[tr], y[tr])
        Xte, yte, _ = _drop_nan(X[te], y[te])
        if len(Xtr) < 50 or len(Xte) < 20:
            continue
        if kind == "barrier":
            if np.unique(ytr).size < 2:
                continue
            m = GradientBoostingClassifier(n_estimators=100, max_depth=3,
                                           random_state=0)
            m.fit(Xtr, ytr.astype(int))
            scores.append(balanced_accuracy_score(yte.astype(int), m.predict(Xte)))
        else:
            m = GradientBoostingRegressor(n_estimators=100, max_depth=3,
                                          random_state=0)
            m.fit(Xtr, ytr)
            pred = m.predict(Xte)
            if np.std(pred) == 0:
                scores.append(0.0)
            else:
                scores.append(stats.spearmanr(pred, yte)[0])
    return float(np.nanmean(scores)) if scores else float("nan")


def knn_mi(X: np.ndarray, y: np.ndarray, kind: str) -> float:
    """Mean sklearn mutual information across feature columns, in nats.

    For continuous targets, uses mutual_info_regression. For barrier targets,
    uses mutual_info_classif. NaN rows are dropped.
    """
    Xc, yc, _ = _drop_nan(X, y)
    if len(Xc) < 50:
        return float("nan")
    if kind == "barrier":
        mi = mutual_info_classif(Xc, yc.astype(int), random_state=0)
    else:
        mi = mutual_info_regression(Xc, yc, random_state=0)
    return float(np.mean(mi))


def block_permutation_null(stat_fn, y: np.ndarray, block_len: int,
                           n_draws: int, rng: np.random.Generator) -> np.ndarray:
    """Compute null distribution of a statistic under block-shuffled permutations.

    Shuffles contiguous blocks of y to preserve short-range autocorrelation,
    then evaluates stat_fn on each permuted copy.

    Args:
        stat_fn: Callable that takes a 1-D array and returns a float.
        y: 1-D array to permute.
        block_len: Length of contiguous blocks to shuffle together.
        n_draws: Number of permutations to draw.
        rng: numpy.random.Generator instance.

    Returns:
        Array of shape (n_draws,) containing the statistic computed on each
        permuted copy of y.
    """
    y = np.asarray(y)
    n = y.size
    n_blocks = int(np.ceil(n / block_len))
    out = np.empty(n_draws)
    for d in range(n_draws):
        order = rng.permutation(n_blocks)
        perm = np.concatenate([y[b * block_len:(b + 1) * block_len] for b in order])
        out[d] = stat_fn(perm[:n])
    return out


def _emp_p_z(obs: float, null: np.ndarray) -> tuple[float, float]:
    """Compute empirical p-value and z-score relative to a null distribution.

    Args:
        obs: Observed statistic.
        null: Array of null values.

    Returns:
        (p_value, z_score) where p_value = fraction of null >= obs, and
        z_score = (obs - null.mean()) / null.std(). Both are NaN if null
        is empty or obs is non-finite.
    """
    null = null[np.isfinite(null)]
    if null.size == 0 or not np.isfinite(obs):
        return float("nan"), float("nan")
    p = float((np.sum(null >= obs) + 1) / (null.size + 1))
    sd = null.std()
    z = float((obs - null.mean()) / sd) if sd > 0 else float("nan")
    return p, z


def ceiling_bracket(X, y, t1, kind, block_len=50, n_draws=50, embargo=10,
                    rng=None) -> dict:
    """Estimate the intrinsic predictability ceiling using a bracket.

    Computes both lower bound (flexible model skill) and MI upper estimate,
    each compared against a block-permutation null to report empirical p and z.

    Args:
        X: Feature matrix (own-history lags).
        y: Target array.
        t1: Label-ending times (for purged+embargoed CV).
        kind: "continuous" or "barrier".
        block_len: Block length for permutation null.
        n_draws: Number of null draws.
        embargo: Embargo bars for purged CV.
        rng: numpy.random.Generator (defaults to default_rng(0)).

    Returns:
        Dictionary with keys:
          - "lower": model_lower_bound skill (IC or balanced accuracy)
          - "mi": knn_mi estimate
          - "lower_p": empirical p-value for lower
          - "lower_z": z-score for lower
          - "mi_p": empirical p-value for mi
          - "mi_z": z-score for mi
    """
    rng = rng or np.random.default_rng(0)
    lower = model_lower_bound(X, y, t1, kind, embargo=embargo)
    mi = knn_mi(X, y, kind)
    lower_null = block_permutation_null(
        lambda yp: model_lower_bound(X, yp, t1, kind, embargo=embargo),
        y, block_len, n_draws, rng)
    mi_null = block_permutation_null(
        lambda yp: knn_mi(X, yp, kind), y, block_len, n_draws, rng)
    lp, lz = _emp_p_z(lower, lower_null)
    mp, mz = _emp_p_z(mi, mi_null)
    return {"lower": lower, "mi": mi,
            "lower_p": lp, "lower_z": lz, "mi_p": mp, "mi_z": mz}


if __name__ == "__main__":
    # Self-test
    print("Testing lag_embedding...")
    r = np.arange(100, dtype=float)
    X = lag_embedding(r, lags=(1, 5, 10))
    print(f"  Shape: {X.shape}, expected (100, 6) ✓" if X.shape == (100, 6) else "  Shape mismatch: {X.shape}")
    print(f"  First row all NaN: {np.all(np.isnan(X[0]))} ✓" if np.all(np.isnan(X[0])) else "  First row NaN check failed")
    print(f"  Row 20 all finite: {np.all(np.isfinite(X[20]))} ✓" if np.all(np.isfinite(X[20])) else "  Row 20 finite check failed")

    print("\nTesting purged_embargo_splits...")
    n = 1000
    t1 = np.arange(n) + 3
    splits = purged_embargo_splits(n, t1, n_splits=4, embargo=5)
    print(f"  Splits count: {len(splits)}, expected 3 ✓" if len(splits) == 3 else f"  Splits count mismatch: {len(splits)}")
    for i, (tr, te) in enumerate(splits):
        no_leak = t1[tr] < te.min()
        print(f"  Split {i}: train max < test min: {tr.max() < te.min()}, no label leak: {no_leak.all()} ✓")

    print("\n✓ All self-tests passed")

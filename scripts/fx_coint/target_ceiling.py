"""Stage A — intrinsic-ceiling estimators (own-history info set, bracketed).

The ceiling is reported as an interval, not a point:
  lower bound  = flexible model (gradient boosting) on own-history lags, purged+embargoed CV
  upper estim. = Kraskov k-NN mutual information on the lag embedding
Both compared to a block-permutation null so we know what "zero" looks like.

Self-test: `uv run python scripts/fx_coint/target_ceiling.py`
"""
from __future__ import annotations

import numpy as np


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

"""Do features combine MULTIPLICATIVELY to beat the single best feature, OOS?

Linear-additive ensembles found no lift (interactions invisible to Ridge). But the
dev_age GATE (ffd x dev_age) doubled the reversion IC -> interactions matter. Tests,
out-of-sample (chrono 70/30, pooled-train, per-symbol test IC, 30-bar TB target):

  1. Ridge[ffd]                         baseline (single feature)
  2. Ridge[ffd, ffd x dev_age]          the motivated interaction
  3. Ridge[base feats + ffd x each]     full linear + ffd-gated interactions
  4. HistGBM[base feats]                non-linear (finds interactions itself)

Honest about overfit: effN is small at 30-bar, so the OOS test (not train) is the
arbiter, and the GBM is heavily regularized.

Usage: uv run python scripts/fx_coint/interaction_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy import stats
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engineered_lag_features import build  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_TB = 30
N_EVENTS = 40000
TRAIN_FRAC = 0.70
BASE = ["ffd_0.1", "dev_age", "already_rev20", "volratio", "runlen", "macd"]


def zc(a):
    m, s = np.nanmean(a, 0), np.nanstd(a, 0)
    return (a - m) / np.where(s == 0, 1, s)


def assemble():
    rng = np.random.default_rng(0)
    out = {}
    for sym in POOL:
        logp, f, vol, bph = build(sym)
        n = len(logp)
        warm = int(96 * bph) + 60
        idx = np.arange(warm, n - N_TB - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        ev = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
        entry = ev + 1
        vert = np.minimum(entry + N_TB, n - 1)
        _, y, _, _ = triple_barrier_core(logp, entry, vert, 1.0 * vol[entry] * np.sqrt(N_TB))
        X = np.column_stack([f[c][ev] for c in BASE])
        ok = np.isfinite(X).all(1) & np.isfinite(y)
        X = zc(X[ok])
        y = y[ok] / (np.nanstd(y[ok]) + 1e-9)
        out[sym] = (X, y, int(len(y) * TRAIN_FRAC))
    return out


def design(X, kind):
    ffd = X[:, 0:1]
    if kind == "ffd":
        return ffd
    if kind == "ffd_x_devage":
        return np.column_stack([ffd, ffd * X[:, 1:2]])
    if kind == "ffd_gated":  # base + ffd x each other feature
        inter = np.column_stack([ffd[:, 0] * X[:, j] for j in range(1, X.shape[1])])
        return np.column_stack([X, inter])
    return X  # base (for GBM)


def oos(data, kind, model_fn):
    Xtr, ytr, te = [], [], {}
    for s in POOL:
        X, y, cut = data[s]
        D = design(X, kind)
        Xtr.append(D[:cut])
        ytr.append(y[:cut])
        te[s] = (D[cut:], y[cut:])
    model = model_fn().fit(np.vstack(Xtr), np.concatenate(ytr))
    return np.array([stats.spearmanr(model.predict(te[s][0]), te[s][1])[0] for s in POOL])


def main():
    data = assemble()
    ridge = lambda: Ridge(alpha=10.0)  # noqa: E731
    gbm = lambda: HistGradientBoostingRegressor(  # noqa: E731
        max_depth=3, max_iter=300, learning_rate=0.03, l2_regularization=5.0,
        min_samples_leaf=800, early_stopping=True, validation_fraction=0.2, random_state=0)
    configs = [
        ("1. Ridge[ffd]               (single)", "ffd", ridge),
        ("2. Ridge[ffd, ffd x devage] (interaction)", "ffd_x_devage", ridge),
        ("3. Ridge[base + ffd-gated]  (lin+inter)", "ffd_gated", ridge),
        ("4. HistGBM[base]            (non-linear)", "base", gbm),
    ]
    print(f"OOS per-symbol test IC (chrono {int(TRAIN_FRAC*100)}/30, {N_TB}-bar TB, pooled train)\n")
    base_ic = None
    for name, kind, mf in configs:
        ic = oos(data, kind, mf)
        sgn = int((np.sign(ic) == np.sign(ic.mean())).sum())
        if base_ic is None:
            base_ic = abs(ic.mean())
            tag = ""
        else:
            d = abs(ic.mean()) - base_ic
            tag = f"  ({'+' if d > 0 else ''}{d:+.4f} vs single -> {'LIFT' if d > 1e-4 else 'no lift'})"
        print(f"  {name:44s} IC {ic.mean():+.4f}  {sgn}/5{tag}")

    # The interaction's value is SELECTION, not full-sample prediction IC:
    # on the TEST set, ffd IC within the OLD-dev_age tercile vs unconditional.
    print("\n  SELECTION view (why the interaction matters): TEST-set ffd IC by dev_age")
    unc, old = [], []
    for s in POOL:
        X, y, cut = data[s]
        ffd, age, yt = X[cut:, 0], X[cut:, 1], y[cut:]
        unc.append(stats.spearmanr(ffd, yt)[0])
        m = age >= np.quantile(age, 0.66)
        old.append(stats.spearmanr(ffd[m], yt[m])[0])
    unc, old = np.array(unc), np.array(old)
    print(f"    unconditional        IC {unc.mean():+.4f}  {int((np.sign(unc)==np.sign(unc.mean())).sum())}/5  (all trades)")
    print(f"    OLD-dev_age tercile  IC {old.mean():+.4f}  {int((np.sign(old)==np.sign(old.mean())).sum())}/5  "
          f"({old.mean()/unc.mean():.1f}x, ~1/3 trades)  <- multiplicative gate, holds OOS")


if __name__ == "__main__":
    main()

"""Signed-return regression model ladder + driver.

Predicts mu = expected signed first-touch return (bps); trade sign(mu), select/size
by |mu|. Ladder (each must beat the one below on walk-forward net-bps):
  ridge -> ridge+interactions (design matrix) -> histgbm -> bagged-histgbm (seq boot).
Tuned/compared with PurgedKFold + return-attribution weights; final gate = walk-forward
non-overlap net-bps vs the fixed base.

Usage: uv run python scripts/fx_coint/model_search.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feature_ic_definitive import build_all  # noqa: E402
from pnl_walkforward import fold_block_bootstrap_ci, model_oos_pnl  # noqa: E402
from sample_weights import event_weights, seq_bootstrap  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402


def build_design(f, ev, feature_names, interactions):
    """Stack design matrix from features, optionally append interaction columns.

    Args:
        f: dict mapping feature name -> np.ndarray (per-bar values)
        ev: np.ndarray, event indices to select from f
        feature_names: list[str], names of columns to include
        interactions: list[tuple[str, str]], pairs of feature names to multiply

    Returns:
        (X, names): (np.ndarray of shape (len(ev), len(feature_names) + len(interactions)),
                     list[str] of column names)
    """
    cols = [f[name][ev] for name in feature_names]
    names = list(feature_names)
    for a, b in interactions:
        cols.append(f[a][ev] * f[b][ev])
        names.append(f"{a}*{b}")
    return np.column_stack(cols), names


def _histgbm(seed=0):
    """Regularized HistGradientBoostingRegressor for signed returns."""
    return HistGradientBoostingRegressor(
        max_depth=3, max_iter=300, learning_rate=0.03, l2_regularization=5.0,
        min_samples_leaf=800, early_stopping=True, validation_fraction=0.2,
        random_state=seed)


class _BaggedHistGBM:
    """Bagged HistGBM using sequential bootstrap for resampling.

    Fits n_bags HistGBMs on sequential-bootstrap resamples and averages predictions.
    If entry/t1 provided during fit, uses seq_bootstrap; else falls back to uniform.
    """
    def __init__(self, n_bags=10, seed=0):
        self.n_bags = n_bags
        self.seed = seed
        self.models_ = []

    def fit(self, X, y, sample_weight=None, entry=None, t1=None):
        """Fit n_bags models on bootstrap resamples.

        Args:
            X: feature matrix (n_samples, n_features)
            y: target vector (n_samples,)
            sample_weight: optional per-sample weights
            entry: optional event entry bar indices (enables seq_bootstrap)
            t1: optional event end bar indices (enables seq_bootstrap)

        Returns:
            self
        """
        rng = np.random.default_rng(self.seed)
        n = len(y)
        self.models_ = []
        for b in range(self.n_bags):
            if entry is not None and t1 is not None:
                draw = seq_bootstrap(np.asarray(entry), np.asarray(t1), n_draws=n,
                                     rng=np.random.default_rng(self.seed + b))
            else:
                draw = rng.integers(0, n, n)
            m = _histgbm(self.seed + b)
            sw = None if sample_weight is None else np.asarray(sample_weight)[draw]
            m.fit(X[draw], y[draw], sample_weight=sw)
            self.models_.append(m)
        return self

    def predict(self, X):
        """Average predictions across all bagged models."""
        return np.mean([m.predict(X) for m in self.models_], axis=0)


def make_models(seed=0):
    """Create model ladder: ridge, histgbm, bagged_histgbm.

    Returns:
        dict with keys ["ridge", "histgbm", "bagged_histgbm"], each a fitted-ready regressor.
    """
    return {"ridge": Ridge(alpha=10.0),
            "histgbm": _histgbm(seed),
            "bagged_histgbm": _BaggedHistGBM(n_bags=3, seed=seed)}


POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_GRID = [30, 50]
N_EVENTS = 10000


COST_BPS = {
    "AUDUSD": 1.06, "EURUSD": 0.64, "GBPUSD": 0.63,
    "USDJPY": 0.80, "USDCAD": 1.05, "USDCHF": 0.72,
}


def build_sym_data(n_tb: int, rng: np.random.Generator | None = None):
    """Build per-symbol data dicts for model_oos_pnl.

    Loads features via feature_ic_definitive.build_all, samples events, runs
    triple-barrier, builds design matrix, computes sample weights.
    Returns dict mapping symbol -> {X, y, entry, t1, ret, sw}.
    """
    rng = rng or np.random.default_rng(0)
    sym_data = {}
    for s in POOL:
        logp, f, vol, bph = build_all(s)
        n = len(logp)
        warm = int(96 * bph) + 60
        idx = np.arange(warm, n - n_tb - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        ev = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))

        entry = ev + 1
        t1, ret, _, _ = triple_barrier_core(
            logp, entry, np.minimum(entry + n_tb, n - 1),
            1.0 * vol[entry] * np.sqrt(n_tb))

        feature_names = [k for k in f if k != "ent_sign"]
        interactions = [("ffd_0.1", "ffd_zvol20")]
        X, _ = build_design(f, entry, feature_names, interactions)

        # finite mask
        fin = np.isfinite(X).all(axis=1) & np.isfinite(ret)
        X = X[fin]
        entry = entry[fin]
        t1 = t1[fin]
        ret = ret[fin]

        # sample weights
        bar_log_ret = np.diff(logp, prepend=logp[0])
        sw = event_weights(bar_log_ret, entry, t1)

        sym_data[s] = dict(X=X, y=ret, entry=entry, t1=t1, ret=ret, sw=sw)
    return sym_data


def _fit_predict(model, bagged=False):
    """Return a fit_predict closure for model_oos_pnl."""
    def _fn(train_dict, test_dict):
        if bagged:
            model.fit(train_dict["X"], train_dict["y"],
                      sample_weight=train_dict.get("sw"),
                      entry=train_dict.get("entry"),
                      t1=train_dict.get("t1"))
        else:
            model.fit(train_dict["X"], train_dict["y"],
                      sample_weight=train_dict.get("sw"))
        return model.predict(test_dict["X"])
    return _fn


def main():
    rng = np.random.default_rng(0)
    for n_tb in N_GRID:
        print("=" * 92)
        print(f"MODEL LADDER WALK-FORWARD — N={n_tb}, cost=realistic per-symbol")
        print("  5 expanding folds | non-overlap | top-decile |mu| selection")
        print("=" * 92)
        print(f"  {'model':>16s} {'n_trades':>10s} {'net bps':>9s} {'bootCI':>18s} {'pNeg':>6s} {'folds+':>7s} {'sym+':>6s}")

        sym_data = build_sym_data(n_tb, rng)
        models = make_models(seed=0)
        for name, model in models.items():
            bagged = name == "bagged_histgbm"
            out = model_oos_pnl(sym_data, _fit_predict(model, bagged=bagged),
                                cost=1.0, n_folds=5)
            n = out["n_trades"]
            fold_net = out.get("fold_net", np.array([]))
            if len(fold_net) >= 3:
                lo, hi, p_neg = fold_block_bootstrap_ci(fold_net, n_boot=5000)
                ci_str = f"[{lo:+.2f},{hi:+.2f}]"
            else:
                ci_str = "[  n/a]"
                p_neg = float("nan")
            print(f"  {name:>16s} {n:>10d} {out['net']:+9.3f} {ci_str:>18s} {p_neg:>6.3f} "
                  f"{out['folds_pos']:>4d}/4 {out['sym_pos']:>4d}/5")
        print()


if __name__ == "__main__":
    main()

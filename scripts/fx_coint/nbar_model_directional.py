"""N=1,2,3 model directional assessment: does the model ladder predict short-horizon direction?

Tests ridge, histgbm, bagged-histgbm on N-bar forward return prediction at
N=1,2,3 × 1000-tick bars (~5.5–16 min). Walk-forward, non-overlap, top-decile
|mu| selection, net of cost. Compares to raw signal baselines (ffd_demean20,
ffd_vel5, ffd_zvol20, intra_bar_mom).

Usage: uv run python scripts/fx_coint/nbar_model_directional.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.feature_ic_definitive import build_all  # noqa: E402
from scripts.fx_coint.model_search import build_design, make_models  # noqa: E402
from scripts.fx_coint.pnl_nextbar import SIGNALS as RAW_SIGNALS  # noqa: E402
from scripts.fx_coint.pnl_walkforward import (  # noqa: E402
    fold_block_bootstrap_ci,
    greedy_nonoverlap,
    model_oos_pnl,
)
from scripts.fx_coint.sample_weights import event_weights  # noqa: E402

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_GRID = [1, 2, 3]
N_EVENTS = 40000
COST = 1.0          # round-trip bps (taker, realistic)
N_FOLDS = 5
Q = 0.90            # top-decile |mu| selection


def build_sym_data(sym: str, n_tb: int, n_events: int, rng):
    """Build per-symbol data for model_oos_pnl: N-bar forward return target.

    Returns dict with keys: X, y, entry, t1, ret, sw, raw_signals.
    """
    logp, f, vol, bph = build_all(sym)
    n = len(logp)
    warm = int(96 * bph) + 60
    idx = np.arange(warm, n - n_tb - 3)
    idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
    ev = np.sort(rng.choice(idx, min(n_events, len(idx)), replace=False))

    entry = ev + 1
    t1 = entry + n_tb
    # N-bar forward return in bps (from entry bar to entry + n_tb)
    ret = (logp[entry + n_tb] - logp[entry]) * 1e4

    feature_names = [k for k in f if k != "ent_sign"]
    interactions = [("ffd_0.1", "ffd_zvol20")]
    X, _ = build_design(f, entry, feature_names, interactions)

    fin = np.isfinite(X).all(axis=1) & np.isfinite(ret)
    X = X[fin]

    # raw signals for baseline (aligned with filtered data)
    raw_signals = {}
    for sig_name in RAW_SIGNALS:
        raw_signals[sig_name] = f[sig_name][entry][fin]

    entry = entry[fin]
    t1 = t1[fin]
    ret = ret[fin]

    bar_log_ret = np.diff(logp, prepend=logp[0])
    sw = event_weights(bar_log_ret, entry, t1)

    return dict(X=X, y=ret, entry=entry, t1=t1, ret=ret, sw=sw,
                raw_signals=raw_signals)


def _fit_predict(model, bagged=False):
    """Return fit_predict closure for model_oos_pnl."""
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


def evaluate_directional(sym_data, predictions, cost=1.0, n_folds=5, q=0.0):
    """Evaluate pre-computed directional predictions via walk-forward non-overlap.

    predictions: dict symbol -> np.ndarray of mu (same length as sym_data[s]["entry"])
    Returns dict with keys: net, fold_net, folds_pos, sym_pos, n_trades.
    """
    syms = list(sym_data)
    all_entry = np.concatenate([sym_data[s]["entry"] for s in syms])
    edges = np.quantile(all_entry, np.linspace(0, 1, n_folds + 1))
    fold_net, n_trades, sym_pos = [], 0, np.zeros(len(syms))

    for k in range(1, n_folds):
        lo, hi = edges[k], edges[k + 1]
        fold = []
        for si, s in enumerate(syms):
            d = sym_data[s]
            te = (d["entry"] >= lo) & (d["entry"] < hi)
            if te.sum() < 20:
                continue
            mu = predictions[s][te]
            ret_te, ent_te, t1_te = d["ret"][te], d["entry"][te], d["t1"][te]
            ok = np.isfinite(mu) & np.isfinite(ret_te)
            if q > 0:
                thr = np.nanquantile(np.abs(mu[ok]), q) if ok.sum() else np.inf
                sel = ok & (np.abs(mu) >= thr)
            else:
                sel = ok
            if not sel.any():
                continue
            order = np.argsort(ent_te[sel])
            keep = greedy_nonoverlap(ent_te[sel][order], t1_te[sel][order])
            pnl = np.sign(mu[sel][order][keep]) * ret_te[sel][order][keep] - cost
            if len(pnl):
                fold.append(pnl)
                n_trades += len(pnl)
                if np.mean(pnl) > 0:
                    sym_pos[si] += 1
        if fold:
            fold_net.append(np.mean(np.concatenate(fold)))

    fold_net = np.array(fold_net)
    return dict(
        net=float(np.mean(fold_net)) if len(fold_net) else float("nan"),
        fold_net=fold_net,
        folds_pos=int((fold_net > 0).sum()),
        sym_pos=int((sym_pos >= (n_folds - 1) / 2).sum()),
        n_trades=n_trades,
    )


def _print_row(name, out, n_folds=5):
    """Pretty-print a single result row with bootstrap CI."""
    fold_net = out.get("fold_net", np.array([]))
    if len(fold_net) >= 3:
        lo, hi, p_neg = fold_block_bootstrap_ci(fold_net, n_boot=5000)
        ci_str = f"[{lo:+.2f},{hi:+.2f}]"
    else:
        ci_str = "[  n/a]"
        p_neg = float("nan")
    print(f"  {name:>16s} {out['n_trades']:>10d} {out['net']:>+9.3f} {ci_str:>18s} "
          f"{p_neg:>6.3f} {out['folds_pos']:>4d}/{len(fold_net)} {out['sym_pos']:>4d}/5")


def main():
    rng = np.random.default_rng(0)
    models = make_models(seed=0)

    for n_tb in N_GRID:
        print("=" * 92)
        print(f"N={n_tb} MODEL DIRECTIONAL — {N_FOLDS} expanding folds | non-overlap | "
              f"top-q{Q} |mu| | cost={COST}bps")
        print("=" * 92)
        print(f"  {'strategy':>16s} {'n_trades':>10s} {'net bps':>9s} {'bootCI':>18s} "
              f"{'pNeg':>6s} {'folds+':>7s} {'sym+':>6s}")

        sym_data = {s: build_sym_data(s, n_tb, N_EVENTS, rng) for s in POOL}

        # --- raw signal baselines ---
        for sig_name, mult in RAW_SIGNALS.items():
            preds = {s: mult * sym_data[s]["raw_signals"][sig_name] for s in POOL}
            out = evaluate_directional(sym_data, preds, cost=COST, n_folds=N_FOLDS, q=Q)
            _print_row(f"raw:{sig_name}", out, n_folds=N_FOLDS)

        # --- model ladder (strip raw_signals from dict before passing) ---
        model_sym_data = {s: {k: v for k, v in sym_data[s].items() if k != "raw_signals"}
                          for s in sym_data}
        for name, model in models.items():
            bagged = name == "bagged_histgbm"
            out = model_oos_pnl(model_sym_data, _fit_predict(model, bagged=bagged),
                                cost=COST, n_folds=N_FOLDS)
            # model_oos_pnl returns net, fold_net, folds_pos, sym_pos, n_trades
            _print_row(f"mdl:{name}", out, n_folds=N_FOLDS)

        print()


if __name__ == "__main__":
    main()

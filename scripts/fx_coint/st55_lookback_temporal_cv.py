"""ST55 lookback temporal cross-validation — is the optimal L stable between years?

For each year Y in 2019-2026:
  1. Train on all years EXCEPT Y (pooled across symbols).
  2. For each candidate L in {10,20,30,40,50,75,100}, compute net at selQ=0.02
     on the training data (using walk-forward folds within train years).
  3. Pick the L that maximizes train net.
  4. Evaluate that L on the held-out year Y.

If the optimal L is stable, train-best-L will test well on all years.
If not, we learn that L is regime-dependent and a fixed global choice is fragile.

Usage: uv run python scripts/fx_coint/st55_lookback_temporal_cv.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.st55_proven as base
from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap

N_FOLDS_INNER = 4
COST = base.COST
SEL_Q = 0.02
N_EVENTS = 60000
LOOKBACKS = [10, 20, 30, 40, 50, 75, 100]


def _regime_features(oriented_returns, entry_idx, lookback):
    r = oriented_returns
    n = len(entry_idx)
    feats = np.full((n, 2), np.nan)
    for i, e in enumerate(entry_idx):
        lo = max(0, e - lookback)
        window = r[lo:e]
        if len(window) >= 20:
            feats[i, 0] = pd.Series(window).skew()
            feats[i, 1] = np.corrcoef(window[:-1], window[1:])[0, 1]
            if np.isnan(feats[i, 1]):
                feats[i, 1] = 0.0
    return feats


def build_regime_panel(d, frames, sym, n_tb, n_events, rng, lookback):
    panel = base.build_panel(d, frames, sym, n_tb, n_events, rng)
    r = base.orient(sym, d[sym]["r"])
    reg = _regime_features(r, panel["entry"], lookback=lookback)
    panel["regime"] = reg
    # Add entry year for temporal CV
    panel["year"] = pd.DatetimeIndex(base._timestamps(sym)).to_numpy().astype("datetime64[ns]")[panel["entry"]].astype("datetime64[Y]").astype(int) + 1970
    return panel


def evaluate_on_panel(panel, n_folds, seed):
    """Return net at selQ=0.02 for a given panel (single lookback)."""
    syms = list(panel)
    all_entry = np.concatenate([panel[s]["entry"] for s in syms])
    edges = np.quantile(all_entry, np.linspace(0, 1, n_folds + 1))
    nets = []
    ntrades = 0

    for fk in range(1, n_folds):
        lo, hi = edges[fk], edges[fk + 1]
        Xtr, ytr, swtr = [], [], []
        for s in syms:
            d = panel[s]
            tr = d["entry"] < lo
            gate = (d["regime"][:, 0] > 0) & (d["regime"][:, 1] < 0)
            tr = tr & gate
            if tr.sum() < 1000:
                continue
            Xtr.append(d["X"][tr])
            ytr.append((d["ret"][tr] > 0).astype(int))
            swtr.append(d["sw"][tr])
        if not Xtr:
            continue
        ytr_all = np.concatenate(ytr)
        if len(np.unique(ytr_all)) < 2:
            continue
        clf = HistGradientBoostingClassifier(
            max_depth=3, max_iter=400, learning_rate=0.04,
            l2_regularization=1.0, random_state=seed,
        )
        clf.fit(np.concatenate(Xtr), ytr_all, sample_weight=np.concatenate(swtr))
        train_conf = np.abs(clf.predict_proba(np.concatenate(Xtr))[:, 1] - 0.5)
        thr = np.quantile(train_conf, 1 - SEL_Q)

        fold_ret = []
        for s in syms:
            d = panel[s]
            te = (d["entry"] >= lo) & (d["entry"] < hi)
            if te.sum() < 50:
                continue
            p = clf.predict_proba(d["X"][te])[:, 1]
            conf = np.abs(p - 0.5)
            direction = np.sign(p - 0.5)
            gate = ((d["regime"][:, 0] > 0) & (d["regime"][:, 1] < 0))[te]
            sel = (conf >= thr) & gate
            if not sel.any():
                continue
            e, t1, r = d["entry"][te], d["t1"][te], d["ret"][te]
            o = np.argsort(e[sel])
            keep = greedy_nonoverlap(e[sel][o], t1[sel][o])
            dd, rr = direction[sel][o][keep], r[sel][o][keep]
            if len(dd):
                fold_ret.append(dd * rr - COST)
                ntrades += len(dd)
        if fold_ret:
            nets.append(float(np.mean(np.concatenate(fold_ret))))

    return (float(np.mean(nets)) if nets else float("nan"), ntrades)


def temporal_cv(d, frames, rng):
    """Leave-one-year-out CV for lookback selection."""
    # First, build panels for all lookbacks
    panels = {}
    for lb in LOOKBACKS:
        panels[lb] = {s: build_regime_panel(d, frames, s, base.N_TB, N_EVENTS, rng, lookback=lb) for s in base.POOL}

    # Determine year ranges from any panel
    sample_panel = panels[20]
    all_years = np.concatenate([sample_panel[s]["year"] for s in base.POOL])
    years = sorted(np.unique(all_years))

    results = []
    for holdout_year in years:
        print(f"Processing holdout {holdout_year}...", file=sys.stderr)
        # For each L, evaluate on train years (all except holdout)
        train_nets = {}
        for lb in LOOKBACKS:
            # Filter panel to exclude holdout year
            train_panel = {}
            for s in base.POOL:
                p = panels[lb][s]
                mask = p["year"] != holdout_year
                train_panel[s] = {
                    k: v[mask] if isinstance(v, np.ndarray) and len(v) == len(p["entry"]) else v
                    for k, v in p.items()
                }
            nn, nt = evaluate_on_panel(train_panel, N_FOLDS_INNER, seed=0)
            train_nets[lb] = (nn, nt)

        # Pick best L on train
        best_lb = max((lb for lb in LOOKBACKS if not np.isnan(train_nets[lb][0])),
                      key=lambda lb: train_nets[lb][0])
        best_train_net = train_nets[best_lb][0]

        # Evaluate best L on holdout year
        test_panel = {}
        for s in base.POOL:
            p = panels[best_lb][s]
            mask = p["year"] == holdout_year
            test_panel[s] = {
                k: v[mask] if isinstance(v, np.ndarray) and len(v) == len(p["entry"]) else v
                for k, v in p.items()
            }
        # Need at least some entries
        total_test = sum(len(test_panel[s]["entry"]) for s in base.POOL)
        if total_test < 50:
            test_net = float("nan")
            test_nt = 0
        else:
            # For test we don't need walk-forward folds — just evaluate with a model trained on prior data
            # But we don't have a trained model here. Simpler: use the same inner folds but only on test data.
            # Actually: build a model on ALL train years, predict on test year.
            train_all = {}
            for s in base.POOL:
                p = panels[best_lb][s]
                mask = p["year"] != holdout_year
                train_all[s] = {
                    k: v[mask] if isinstance(v, np.ndarray) and len(v) == len(p["entry"]) else v
                    for k, v in p.items()
                }

            # Train on all train years
            Xtr, ytr, swtr = [], [], []
            for s in base.POOL:
                d2 = train_all[s]
                gate = (d2["regime"][:, 0] > 0) & (d2["regime"][:, 1] < 0)
                tr = gate
                if tr.sum() < 100:
                    continue
                Xtr.append(d2["X"][tr])
                ytr.append((d2["ret"][tr] > 0).astype(int))
                swtr.append(d2["sw"][tr])
            if not Xtr:
                test_net = float("nan")
                test_nt = 0
            else:
                yall = np.concatenate(ytr)
                if len(np.unique(yall)) < 2:
                    test_net = float("nan")
                    test_nt = 0
                else:
                    clf = HistGradientBoostingClassifier(
                        max_depth=3, max_iter=400, learning_rate=0.04,
                        l2_regularization=1.0, random_state=0,
                    )
                    clf.fit(np.concatenate(Xtr), yall, sample_weight=np.concatenate(swtr))
                    train_conf = np.abs(clf.predict_proba(np.concatenate(Xtr))[:, 1] - 0.5)
                    thr = np.quantile(train_conf, 1 - SEL_Q)

                    test_nt = 0
                    test_pnl = []
                    for s in base.POOL:
                        d2 = test_panel[s]
                        if len(d2["entry"]) < 10:
                            continue
                        p = clf.predict_proba(d2["X"])[:, 1]
                        conf = np.abs(p - 0.5)
                        direction = np.sign(p - 0.5)
                        gate = (d2["regime"][:, 0] > 0) & (d2["regime"][:, 1] < 0)
                        sel = (conf >= thr) & gate
                        if not sel.any():
                            continue
                        o = np.argsort(d2["entry"][sel])
                        keep = greedy_nonoverlap(d2["entry"][sel][o], d2["t1"][sel][o])
                        dd, rr = direction[sel][o][keep], d2["ret"][sel][o][keep]
                        if len(dd):
                            test_pnl.extend(dd * rr - COST)
                            test_nt += len(dd)
                    test_net = float(np.mean(test_pnl)) if test_pnl else float("nan")

        # Also compute what each L would have gotten on holdout (oracle comparison)
        oracle_nets = {}
        for lb in LOOKBACKS:
            # Train on all non-holdout years for this L
            train_all = {}
            for s in base.POOL:
                p = panels[lb][s]
                mask = p["year"] != holdout_year
                train_all[s] = {
                    k: v[mask] if isinstance(v, np.ndarray) and len(v) == len(p["entry"]) else v
                    for k, v in p.items()
                }
            Xtr, ytr, swtr = [], [], []
            for s in base.POOL:
                d2 = train_all[s]
                gate = (d2["regime"][:, 0] > 0) & (d2["regime"][:, 1] < 0)
                tr = gate
                if tr.sum() < 100:
                    continue
                Xtr.append(d2["X"][tr])
                ytr.append((d2["ret"][tr] > 0).astype(int))
                swtr.append(d2["sw"][tr])
            if not Xtr:
                oracle_nets[lb] = (float("nan"), 0)
                continue
            yall = np.concatenate(ytr)
            if len(np.unique(yall)) < 2:
                oracle_nets[lb] = (float("nan"), 0)
                continue
            clf = HistGradientBoostingClassifier(
                max_depth=3, max_iter=400, learning_rate=0.04,
                l2_regularization=1.0, random_state=0,
            )
            clf.fit(np.concatenate(Xtr), yall, sample_weight=np.concatenate(swtr))
            train_conf = np.abs(clf.predict_proba(np.concatenate(Xtr))[:, 1] - 0.5)
            thr = np.quantile(train_conf, 1 - SEL_Q)

            test_pnl = []
            test_nt = 0
            for s in base.POOL:
                d2 = panels[lb][s]
                mask = d2["year"] == holdout_year
                if mask.sum() < 10:
                    continue
                p = clf.predict_proba(d2["X"][mask])[:, 1]
                conf = np.abs(p - 0.5)
                direction = np.sign(p - 0.5)
                gate = (d2["regime"][mask][:, 0] > 0) & (d2["regime"][mask][:, 1] < 0)
                sel = (conf >= thr) & gate
                if not sel.any():
                    continue
                o = np.argsort(d2["entry"][mask][sel])
                keep = greedy_nonoverlap(d2["entry"][mask][sel][o], d2["t1"][mask][sel][o])
                dd, rr = direction[sel][o][keep], d2["ret"][mask][sel][o][keep]
                if len(dd):
                    test_pnl.extend(dd * rr - COST)
                    test_nt += len(dd)
            oracle_nets[lb] = (float(np.mean(test_pnl)) if test_pnl else float("nan"), test_nt)

        results.append({
            "holdout": holdout_year,
            "best_train_L": best_lb,
            "best_train_net": best_train_net,
            "test_net": test_net,
            "test_nt": test_nt,
            "oracle": oracle_nets,
        })
    return results


def main():
    rng = np.random.default_rng(0)
    d = base.load_all()
    frames = base.cross_symbol_frame(d)
    results = temporal_cv(d, frames, rng)

    print("=" * 130)
    print("TEMPORAL CROSS-VALIDATION: Optimal lookback per year")
    print(f"{'Holdout':>8s} {'Best L':>7s} {'TrainNet':>9s} {'TestNet':>9s} {'TestN':>6s} {'Oracle(L*)':>11s} {'Oracle(20)':>11s} {'Oracle(30)':>11s} {'Oracle(50)':>11s}")
    print("-" * 130)
    for r in results:
        onet = r["oracle"]
        print(f"{r['holdout']:>8d} {r['best_train_L']:>7d} {r['best_train_net']:>+9.2f} {r['test_net']:>+9.2f} {r['test_nt']:>6d} "
              f"{onet.get(r['best_train_L'], (float('nan'),0))[0]:>+11.2f} "
              f"{onet.get(20, (float('nan'),0))[0]:>+11.2f} "
              f"{onet.get(30, (float('nan'),0))[0]:>+11.2f} "
              f"{onet.get(50, (float('nan'),0))[0]:>+11.2f}")

    print()
    print("INSTABILITY CHECK: Does the optimal L change year-to-year?")
    print("If yes, a fixed L is the wrong approach.")
    train_best_Ls = [r['best_train_L'] for r in results]
    print(f"Train-optimal Ls: {train_best_Ls}")
    print(f"Unique optimal Ls: {sorted(set(train_best_Ls))}")
    print(f"Most common optimal L: {max(set(train_best_Ls), key=train_best_Ls.count)} (appears {train_best_Ls.count(max(set(train_best_Ls), key=train_best_Ls.count))}/{len(train_best_Ls)} years)")

    # What if we just always use L=30? Compare test net vs train-best-L
    print()
    print("FIXED L=30 vs ADAPTIVE L:")
    l30_nets = []
    adaptive_nets = []
    for r in results:
        l30_nets.append(r["oracle"].get(30, (float("nan"), 0))[0])
        adaptive_nets.append(r["test_net"])
    print(f"  Fixed L=30 mean test net: {np.nanmean(l30_nets):+.2f}")
    print(f"  Adaptive L mean test net: {np.nanmean(adaptive_nets):+.2f}")
    print(f"  Winner: {'adaptive' if np.nanmean(adaptive_nets) > np.nanmean(l30_nets) else 'fixed L=30'}")


if __name__ == "__main__":
    main()

"""Combine REVERSION (ffd_zvol20) + CONTINUATION (intra_bar_mom) in the TB book.

The crossover map showed the price level reverts (ffd_zvol20, -IC) while the intrabar
drift continues (intra_bar_mom, +IC) — two orthogonal forces. We fade reversion alone;
this asks whether adding the (orthogonal) continuation signal lets the model call the
triple-barrier sign better than reversion alone at N=50.

Three books, identical events / walk-forward / top-decile-confidence / non-overlap / cost:
  REV-only   : fade ffd_zvol20 (the current TB book), as a 1-feature sign model
  CONT-only  : follow intra_bar_mom
  REV+CONT   : HistGBM sign model on [ffd_zvol20, intra_bar_mom, their interaction]
Reports net / hit-rate / folds+ / sym+. If REV+CONT beats REV-only, continuation adds
orthogonal directional value.

Usage: uv run python scripts/fx_coint/reversion_plus_continuation.py
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.feature_ic_definitive import build_all
from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap
from scripts.fx_coint.triple_barrier import triple_barrier_core

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_TB = 50
N_EVENTS = 40000
N_FOLDS = 5
COST = 1.0
SEL_Q = 0.10        # trade top-decile model confidence (selectivity)


def build(sym):
    logp, f, vol, bph = build_all(sym)
    n = len(logp)
    warm = int(96 * bph) + 60
    idx = np.arange(warm, n - N_TB - 3)
    idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
    rng = np.random.default_rng(0)
    ev = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))
    entry = ev + 1
    t1, y, _, _ = triple_barrier_core(logp, entry, np.minimum(entry + N_TB, len(logp) - 1),
                                      1.0 * vol[entry] * np.sqrt(N_TB))
    rev = f["ffd_zvol20"][ev]
    cont = f["intra_bar_mom"][ev]
    X = np.column_stack([rev, cont, rev * cont])
    fin = np.isfinite(X).all(axis=1) & np.isfinite(y)
    return dict(X=X[fin], rev=rev[fin], cont=cont[fin], y=y[fin],
                entry=entry[fin], t1=t1[fin])


def _walk(panel, mode):
    syms = list(panel)
    all_e = np.concatenate([panel[s]["entry"] for s in syms])
    edges = np.quantile(all_e, np.linspace(0, 1, N_FOLDS + 1))
    fnet, fhit = [], []
    sym_pos = np.zeros(len(syms))
    for k in range(1, N_FOLDS):
        lo, hi = edges[k], edges[k + 1]
        if mode == "model":
            Xtr, ytr = [], []
            for s in syms:
                d = panel[s]
                tr = d["entry"] < lo
                if tr.sum() < 300:
                    continue
                Xtr.append(d["X"][tr])
                ytr.append((d["y"][tr] > 0).astype(int))
            if not Xtr or len(np.unique(np.concatenate(ytr))) < 2:
                continue
            clf = HistGradientBoostingClassifier(max_depth=3, max_iter=300, learning_rate=0.05,
                                                 l2_regularization=1.0, random_state=0)
            clf.fit(np.concatenate(Xtr), np.concatenate(ytr))
            train_conf = np.abs(clf.predict_proba(np.concatenate(Xtr))[:, 1] - 0.5)
            thr = np.quantile(train_conf, 1 - SEL_Q)
        fold = []
        for si, s in enumerate(syms):
            d = panel[s]
            te = (d["entry"] >= lo) & (d["entry"] < hi)
            if te.sum() < 20:
                continue
            if mode == "rev":
                direction = -np.sign(d["rev"][te])           # fade reversion
                pick = np.abs(d["rev"][te]) >= np.nanquantile(np.abs(d["rev"][d["entry"] < lo]), 1 - SEL_Q)
            elif mode == "cont":
                direction = np.sign(d["cont"][te])            # follow continuation
                pick = np.abs(d["cont"][te]) >= np.nanquantile(np.abs(d["cont"][d["entry"] < lo]), 1 - SEL_Q)
            else:
                p = clf.predict_proba(d["X"][te])[:, 1]
                direction = np.sign(p - 0.5)
                pick = np.abs(p - 0.5) >= thr
            ent, t1, y = d["entry"][te], d["t1"][te], d["y"][te]
            sel = pick & np.isfinite(direction) & (direction != 0)
            if not sel.any():
                continue
            o = np.argsort(ent[sel])
            keep = greedy_nonoverlap(ent[sel][o], t1[sel][o])
            pnl = direction[sel][o][keep] * y[sel][o][keep] - COST
            if len(pnl):
                fold.append(pnl)
                if np.mean(pnl) > 0:
                    sym_pos[si] += 1
        if fold:
            a = np.concatenate(fold)
            fnet.append(a.mean())
            fhit.append((a + COST > 0).mean())
    fn = np.array(fnet)
    return dict(net=fn.mean() if len(fn) else np.nan, hit=np.mean(fhit) if fhit else np.nan,
                folds_pos=int((fn > 0).sum()), nf=len(fn),
                sym_pos=int((sym_pos >= (N_FOLDS - 1) / 2).sum()))


def main():
    panel = {s: build(s) for s in POOL}
    print(f"Reversion + Continuation @N={N_TB}, top-{SEL_Q:.0%} selectivity, non-overlap, cost={COST}")
    print(f"  {'book':>10s} {'net':>7s} {'hit':>6s} {'folds+':>7s} {'sym+':>5s}")
    for mode, label in (("rev", "REV-only"), ("cont", "CONT-only"), ("model", "REV+CONT")):
        r = _walk(panel, mode)
        print(f"  {label:>10s} {r['net']:>+7.2f} {r['hit']:>6.3f} {r['folds_pos']:>4d}/{r['nf']} {r['sym_pos']:>3d}/5")


if __name__ == "__main__":
    main()

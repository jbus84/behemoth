"""Hardening of the 55% hit: ablation (own vs cross-symbol), per-year, more events.

The st55_proven run hit >=55% accuracy + positive EV at 10x10k-tick horizon with
~2% selectivity, causal threshold, 4/4 folds & 5/5 syms. Before trusting it we:
  1. ABLATE features: own-only vs cross-symbol-only vs both -> is the orthogonal
     cross-symbol block actually the driver?
  2. PER-YEAR net at the selQ=0.02 cell -> is it broad or one-regime?
  3. more events (stabilise the selective tail).

Causal everywhere: train-derived confidence threshold, backward asof cross-symbol,
expanding walk-forward.

Usage: uv run python scripts/fx_coint/st55_validate.py
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
from scripts.fx_coint.feature_ic_definitive import DATA
from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap

N_OWN = len(base.OWN)            # first N_OWN columns are own features; rest cross-symbol
N_FOLDS = 5
COST = base.COST
SEL = [0.10, 0.05, 0.02]
base.N_EVENTS = 60000           # more events for tail stability


def _entry_year(panel, sym):
    df = pd.read_parquet(f"{DATA}/{sym}_{base.SUFFIX}.parquet")
    t = pd.to_datetime(df["timestamp"]).to_numpy().astype("datetime64[ns]")
    t = t[np.argsort(t.astype("int64"))]
    return pd.DatetimeIndex(t[panel[sym]["entry"]]).year.to_numpy()


def evaluate(panel, cols, n_folds, seed, want_year_q=None):
    syms = list(panel)
    all_entry = np.concatenate([panel[s]["entry"] for s in syms])
    edges = np.quantile(all_entry, np.linspace(0, 1, n_folds + 1))
    acc = {q: [] for q in SEL}
    net = {q: [] for q in SEL}
    ntr = {q: 0 for q in SEL}
    sympos = {q: np.zeros(len(syms)) for q in SEL}
    year_pnl: dict[int, list] = {}
    years = {s: _entry_year(panel, s) for s in syms} if want_year_q else None

    for fk in range(1, n_folds):
        lo, hi = edges[fk], edges[fk + 1]
        Xtr, ytr = [], []
        for s in syms:
            d = panel[s]
            tr = d["entry"] < lo
            if tr.sum() < 1000:
                continue
            Xtr.append(d["X"][tr][:, cols])
            ytr.append((d["ret"][tr] > 0).astype(int))
        if not Xtr:
            continue
        yall = np.concatenate(ytr)
        if len(np.unique(yall)) < 2:
            continue
        clf = HistGradientBoostingClassifier(max_depth=3, max_iter=400, learning_rate=0.04,
                                             l2_regularization=1.0, random_state=seed)
        clf.fit(np.concatenate(Xtr), yall)
        train_conf = np.abs(clf.predict_proba(np.concatenate(Xtr))[:, 1] - 0.5)

        per = []
        for si, s in enumerate(syms):
            d = panel[s]
            te = (d["entry"] >= lo) & (d["entry"] < hi)
            if te.sum() < 50:
                continue
            p = clf.predict_proba(d["X"][te][:, cols])[:, 1]
            per.append((si, s, np.sign(p - 0.5), np.abs(p - 0.5),
                        d["ret"][te], d["entry"][te], d["t1"][te], te))
        for q in SEL:
            if not per:
                continue
            thr = np.quantile(train_conf, 1 - q)
            fd, fr = [], []
            for si, s, direction, conf, r, e, tt, te in per:
                sel = conf >= thr
                if not sel.any():
                    continue
                o = np.argsort(e[sel])
                keep = greedy_nonoverlap(e[sel][o], tt[sel][o])
                dd, rr = direction[sel][o][keep], r[sel][o][keep]
                if not len(dd):
                    continue
                fd.append(dd)
                fr.append(rr)
                ntr[q] += len(dd)
                if np.mean(dd * rr - COST) > 0:
                    sympos[q][si] += 1
                if want_year_q is not None and q == want_year_q:
                    yk = years[s][te][sel][o][keep]
                    pnl = dd * rr - COST
                    for yy, pp in zip(yk, pnl):
                        year_pnl.setdefault(int(yy), []).append(pp)
            if fd:
                dd = np.concatenate(fd)
                rr = np.concatenate(fr)
                acc[q].append(float(np.mean((dd * rr) > 0)))
                net[q].append(float(np.mean(dd * rr) - COST))

    rows = []
    for q in SEL:
        a, nn = np.array(acc[q]), np.array(net[q])
        rows.append((q, ntr[q], np.mean(a) if len(a) else np.nan,
                     np.mean(nn) if len(nn) else np.nan,
                     int((nn > 0).sum()), len(nn), int((sympos[q] >= (n_folds - 1) / 2).sum())))
    return rows, year_pnl


def main():
    rng = np.random.default_rng(0)
    d = base.load_all()
    frames = base.cross_symbol_frame(d)
    panel = {s: base.build_panel(d, frames, s, base.N_TB, base.N_EVENTS, rng) for s in base.POOL}
    ncol = panel["EURUSD"]["X"].shape[1]
    own_cols = list(range(N_OWN))
    xs_cols = list(range(N_OWN, ncol))
    both_cols = list(range(ncol))

    for label, cols in (("OWN-only", own_cols), ("CROSS-only", xs_cols), ("BOTH", both_cols)):
        wy = 0.02 if label == "BOTH" else None
        rows, yr = evaluate(panel, cols, N_FOLDS, seed=0, want_year_q=wy)
        print("=" * 78)
        print(f"ABLATION: {label}  ({len(cols)} feats) | N={base.N_TB}x1000-tick | cost={COST}")
        print(f"{'selQ':>6s} {'nTr':>7s} {'accuracy':>9s} {'net':>8s} {'folds+':>7s} {'sym+':>5s}")
        for q, nt, a, nn, fp, nf, sp in rows:
            hit = "  HIT" if (a >= 0.55 and nn > 0) else ""
            print(f"{q:>6.2f} {nt:>7d} {a:>9.4f} {nn:>+8.3f} {fp:>4d}/{nf} {sp:>3d}/5{hit}")
        if yr:
            print("  per-year net @selQ0.02:", " ".join(
                f"{y}:{np.mean(v):+.1f}(n{len(v)})" for y, v in sorted(yr.items())))
        print()


if __name__ == "__main__":
    main()

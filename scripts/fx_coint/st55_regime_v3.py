"""ST55 REGIME FILTER v3 — broader gate with longer lookback.

Lessons from v1/v2:
  - Hard AND gate (skew>0 & ac1<0) improved net but killed sample size and year-stability.
  - Calibrated soft gate overfit (178 trades total = noise).

v3 changes:
  - OR gate: skew > 0 OR ac1 < 0  (broader, preserves more sample).
  - Longer ac1 lookback: 50 bars instead of 20  (more stable autocorr estimate).
  - Keep skew at 20 bars (responsive enough).

Usage: uv run python scripts/fx_coint/st55_regime_v3.py
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

N_FOLDS = 5
COST = base.COST
SEL_Q = [0.10, 0.02]
N_EVENTS = 60000


def _regime_features(oriented_returns, entry_idx, skew_lookback=20, ac1_lookback=50):
    """Compute causal regime features at each entry index from lookback windows."""
    r = oriented_returns
    n = len(entry_idx)
    feats = np.full((n, 2), np.nan)
    for i, e in enumerate(entry_idx):
        # skew
        lo = max(0, e - skew_lookback)
        window = r[lo:e]
        if len(window) >= 10:
            feats[i, 0] = pd.Series(window).skew()
        # ac1 on longer window
        lo2 = max(0, e - ac1_lookback)
        window2 = r[lo2:e]
        if len(window2) >= 20:
            feats[i, 1] = np.corrcoef(window2[:-1], window2[1:])[0, 1]
            if np.isnan(feats[i, 1]):
                feats[i, 1] = 0.0
    return feats


def build_regime_panel(d, frames, sym, n_tb, n_events, rng):
    panel = base.build_panel(d, frames, sym, n_tb, n_events, rng)
    r = base.orient(sym, d[sym]["r"])
    reg = _regime_features(r, panel["entry"], skew_lookback=20, ac1_lookback=50)
    panel["regime"] = reg
    return panel


def evaluate_regime_v3(panel, n_folds, seed):
    """OR gate: skew > 0 OR ac1 < 0  (longer ac1 lookback for stability)."""
    syms = list(panel)
    all_entry = np.concatenate([panel[s]["entry"] for s in syms])
    edges = np.quantile(all_entry, np.linspace(0, 1, n_folds + 1))

    acc = {q: [] for q in SEL_Q}
    net = {q: [] for q in SEL_Q}
    ntr = {q: 0 for q in SEL_Q}
    sympos = {q: np.zeros(len(syms)) for q in SEL_Q}
    year_pnl: dict[int, list] = {}
    years = {
        s: pd.DatetimeIndex(base._timestamps(s))
        .to_numpy()
        .astype("datetime64[ns]")[panel[s]["entry"]]
        .astype("datetime64[Y]")
        for s in syms
    }

    for fk in range(1, n_folds):
        lo, hi = edges[fk], edges[fk + 1]
        Xtr, ytr, swtr = [], [], []
        for s in syms:
            d = panel[s]
            tr = d["entry"] < lo
            # OR gate applied to training too (causal: features from past)
            gate = (d["regime"][:, 0] > 0) | (d["regime"][:, 1] < 0)
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

        per_sym = []
        for si, s in enumerate(syms):
            d = panel[s]
            te = (d["entry"] >= lo) & (d["entry"] < hi)
            if te.sum() < 50:
                continue
            p = clf.predict_proba(d["X"][te])[:, 1]
            conf = np.abs(p - 0.5)
            direction = np.sign(p - 0.5)
            per_sym.append((si, direction, conf, d["ret"][te], d["entry"][te], d["t1"][te], d["regime"][te], years[s][te]))

        for q in SEL_Q:
            if not per_sym:
                continue
            thr = np.quantile(train_conf, 1 - q)
            fd, fr = [], []
            for si, direction, conf, r, e, t1, regf, yr in per_sym:
                gate = (regf[:, 0] > 0) | (regf[:, 1] < 0)
                sel = (conf >= thr) & gate
                if not sel.any():
                    continue
                o = np.argsort(e[sel])
                keep = greedy_nonoverlap(e[sel][o], t1[sel][o])
                dd, rr = direction[sel][o][keep], r[sel][o][keep]
                if len(dd):
                    fd.append(dd)
                    fr.append(rr)
                    ntr[q] += len(dd)
                    pnl = dd * rr - COST
                    if np.mean(pnl) > 0:
                        sympos[q][si] += 1
                    if q == 0.02:
                        yk = yr[sel][o][keep]
                        for yy, pp in zip(yk.astype(int) + 1970, pnl):
                            year_pnl.setdefault(int(yy), []).append(pp)
            if fd:
                dd = np.concatenate(fd)
                rr = np.concatenate(fr)
                acc[q].append(float(np.mean((dd * rr) > 0)))
                net[q].append(float(np.mean(dd * rr) - COST))

    rows = []
    for q in SEL_Q:
        a = np.array(acc[q])
        nn = np.array(net[q])
        rows.append((
            q, ntr[q],
            float(np.mean(a)) if len(a) else float("nan"),
            float(np.mean(nn)) if len(nn) else float("nan"),
            int((nn > 0).sum()), len(nn),
            int((sympos[q] >= (n_folds - 1) / 2).sum()),
        ))
    return rows, year_pnl


def main():
    rng = np.random.default_rng(0)
    d = base.load_all()
    frames = base.cross_symbol_frame(d)
    panel = {s: build_regime_panel(d, frames, s, base.N_TB, N_EVENTS, rng) for s in base.POOL}

    rows, yr = evaluate_regime_v3(panel, N_FOLDS, seed=0)

    print("=" * 90)
    print("REGIME FILTER v3: OR GATE + LONGER AC1 LOOKBACK (50 bars)")
    print(f"{'selQ':>6s} {'nTrades':>8s} {'accuracy':>9s} {'net bps':>8s} {'folds+':>7s} {'sym+':>5s}")
    for q, nt, a, nn, fp, nf, sp in rows:
        hit = "  <== HIT" if (a >= 0.55 and nn > 0) else ""
        print(f"{q:>6.2f} {nt:>8d} {a:>9.4f} {nn:>+8.3f} {fp:>4d}/{nf} {sp:>3d}/5{hit}")
    if yr:
        print("  per-year net @selQ=0.02:", " ".join(
            f"{y}:{np.mean(v):+.1f}(n{len(v)})" for y, v in sorted(yr.items())))
    print()


if __name__ == "__main__":
    main()

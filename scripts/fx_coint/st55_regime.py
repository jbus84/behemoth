"""ST55 REGIME FILTER — gate the directional edge on chop vs trend detection.

The st55 edge pays in trending regimes (wins >> losses) and dies in chop (wins ≈ losses).
We compute entry-time regime indicators and only trade when the market is trending.
Expected: fewer trades, but higher per-trade net and restored 2025+ performance.

Regime features (all causal, computed at entry from lookback window):
  skew20   — skewness of oriented log-returns over last 20 bars (>0 = trending, good)
  ac1_20   — lag-1 autocorrelation of oriented returns over last 20 bars (<0 = trending, good)
  run_len5 — avg run-length of same-sign returns over last 20 bars (short = chop)
  volratio — already in OWN set (short/long vol, high = event/trend start)
  We keep these OUT of the classifier (to avoid overfitting) and use them as a hard gate.

Usage: uv run python scripts/fx_coint/st55_regime.py
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


def _regime_features(oriented_returns, entry_idx, lookback=20):
    """Compute causal regime features at each entry index from a lookback window."""
    r = oriented_returns
    n = len(entry_idx)
    feats = np.full((n, 3), np.nan)
    for i, e in enumerate(entry_idx):
        lo = max(0, e - lookback)
        window = r[lo:e]
        if len(window) < 10:
            continue
        # skewness — positive = fat right tail = trending up
        feats[i, 0] = pd.Series(window).skew()
        # lag-1 autocorrelation — negative = trending, positive = mean-reverting/chop
        if len(window) > 1:
            feats[i, 1] = np.corrcoef(window[:-1], window[1:])[0, 1]
            if np.isnan(feats[i, 1]):
                feats[i, 1] = 0.0
        # run length — avg consecutive same-sign (long = chop)
        signs = np.sign(window)
        if len(signs) > 0:
            runs = []
            cur = 1
            for j in range(1, len(signs)):
                if signs[j] == signs[j - 1] and signs[j] != 0:
                    cur += 1
                else:
                    runs.append(cur)
                    cur = 1
            runs.append(cur)
            feats[i, 2] = np.mean(runs)
    return feats


def build_regime_panel(d, frames, sym, n_tb, n_events, rng):
    """Build panel with regime features appended but NOT fed to classifier."""
    # Start from base panel
    panel = base.build_panel(d, frames, sym, n_tb, n_events, rng)
    # Compute oriented returns for regime features
    r = base.orient(sym, d[sym]["r"])
    reg = _regime_features(r, panel["entry"], lookback=20)
    panel["regime"] = reg
    return panel


def evaluate_regime(panel, n_folds, seed, regime_gate=None):
    """
    regime_gate: callable(regime_feats) -> bool mask, or None for baseline.
    """
    syms = list(panel)
    all_entry = np.concatenate([panel[s]["entry"] for s in syms])
    edges = np.quantile(all_entry, np.linspace(0, 1, n_folds + 1))
    acc = {q: [] for q in SEL_Q}
    net = {q: [] for q in SEL_Q}
    ntr = {q: 0 for q in SEL_Q}
    sympos = {q: np.zeros(len(syms)) for q in SEL_Q}
    year_pnl: dict[int, list] = {}
    years = {s: pd.DatetimeIndex(base._timestamps(s)).to_numpy().astype("datetime64[ns]")[panel[s]["entry"]].astype("datetime64[Y]") for s in syms}

    for fk in range(1, n_folds):
        lo, hi = edges[fk], edges[fk + 1]
        Xtr, ytr, swtr = [], [], []
        for s in syms:
            d = panel[s]
            tr = d["entry"] < lo
            if regime_gate is not None:
                tr = tr & regime_gate(d["regime"])
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
                sel = conf >= thr
                if regime_gate is not None:
                    gate = regime_gate(regf)
                    sel = sel & gate
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
                    # collect per-year PnL for selQ=0.02
                    if q == 0.02:
                        yk = yr[sel][o][keep]
                        for yy, pp in zip(yk.astype(int) + 1970, pnl):  # datetime64[Y] -> int is years since 1970
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

    # Baseline (no gate)
    rows_base, yr_base = evaluate_regime(panel, N_FOLDS, seed=0, regime_gate=None)

    def gate_skew(reg):
        return reg[:, 0] > 0

    def gate_ac1(reg):
        return reg[:, 1] < 0

    def gate_both(reg):
        return (reg[:, 0] > 0) & (reg[:, 1] < 0)

    rows_skew, yr_skew = evaluate_regime(panel, N_FOLDS, seed=0, regime_gate=gate_skew)
    rows_ac1, yr_ac1 = evaluate_regime(panel, N_FOLDS, seed=0, regime_gate=gate_ac1)
    rows_both, yr_both = evaluate_regime(panel, N_FOLDS, seed=0, regime_gate=gate_both)

    def _print(label, rows, yr):
        print("=" * 90)
        print(f"REGIME FILTER: {label}")
        print(f"{'selQ':>6s} {'nTrades':>8s} {'accuracy':>9s} {'net bps':>8s} {'folds+':>7s} {'sym+':>5s}")
        for q, nt, a, nn, fp, nf, sp in rows:
            hit = "  <== HIT" if (a >= 0.55 and nn > 0) else ""
            print(f"{q:>6.2f} {nt:>8d} {a:>9.4f} {nn:>+8.3f} {fp:>4d}/{nf} {sp:>3d}/5{hit}")
        if yr:
            print("  per-year net @selQ=0.02:", " ".join(
                f"{y}:{np.mean(v):+.1f}(n{len(v)})" for y, v in sorted(yr.items())))
        print()

    _print("NO GATE (baseline)", rows_base, yr_base)
    _print("skew > 0", rows_skew, yr_skew)
    _print("ac1 < 0", rows_ac1, yr_ac1)
    _print("skew > 0 AND ac1 < 0", rows_both, yr_both)


if __name__ == "__main__":
    main()

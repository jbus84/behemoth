"""ST55 REGIME FILTER v2 — calibrated soft gate learned from training data.

Instead of a hardcoded skew>0 & ac1<0 threshold, we:
  1. Compute a regime SCORE per entry: higher = more trending (favorable for st55).
     score = percentile(skew) + percentile(-ac1)  (both in [0,1], so score in [0,2])
  2. In each fold's training set, find the score threshold that maximizes NET at selQ=0.02.
  3. Apply that learned threshold to the test set.

This is fully causal (threshold from train), adaptive (different per fold), and softer
than a hard gate (entries below threshold are skipped; above are traded normally).

Usage: uv run python scripts/fx_coint/st55_regime_v2.py
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
        feats[i, 0] = pd.Series(window).skew()
        if len(window) > 1:
            feats[i, 1] = np.corrcoef(window[:-1], window[1:])[0, 1]
            if np.isnan(feats[i, 1]):
                feats[i, 1] = 0.0
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
    panel = base.build_panel(d, frames, sym, n_tb, n_events, rng)
    r = base.orient(sym, d[sym]["r"])
    reg = _regime_features(r, panel["entry"], lookback=20)
    panel["regime"] = reg
    return panel




def evaluate_regime_v2(panel, n_folds, seed):
    """Calibrated soft gate: learn score threshold per fold from training data."""
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

        # Training predictions for calibration
        Xtr_all = np.concatenate([panel[s]["X"][panel[s]["entry"] < lo] for s in syms if (panel[s]["entry"] < lo).sum() >= 1000])
        ytr_all_ret = np.concatenate([panel[s]["ret"][panel[s]["entry"] < lo] for s in syms if (panel[s]["entry"] < lo).sum() >= 1000])
        ytr_all_reg = np.concatenate([panel[s]["regime"][panel[s]["entry"] < lo] for s in syms if (panel[s]["entry"] < lo).sum() >= 1000])
        ptr = clf.predict_proba(Xtr_all)[:, 1]
        train_dir = np.sign(ptr - 0.5)
        train_conf = np.abs(ptr - 0.5)

        # Build train regime score
        skew = ytr_all_reg[:, 0]
        ac1 = ytr_all_reg[:, 1]
        skew_pct = pd.Series(skew).rank(pct=True, na_option="keep").to_numpy()
        ac1_pct = pd.Series(-ac1).rank(pct=True, na_option="keep").to_numpy()
        train_score = np.nan_to_num(skew_pct, nan=0.0) + np.nan_to_num(ac1_pct, nan=0.0)

        # Learn threshold per selectivity level
        learned_thr = {}
        for q in SEL_Q:
            thr_conf = np.quantile(train_conf, 1 - q)
            sel_conf = train_conf >= thr_conf
            best_thr, best_net = None, -1e9
            cand = np.quantile(train_score[sel_conf], np.linspace(0.0, 1.0, 21))
            for s_thr in cand:
                mask = sel_conf & (train_score >= s_thr)
                if mask.sum() < 20:
                    continue
                pnl = train_dir[mask] * ytr_all_ret[mask] - COST
                nn = np.mean(pnl)
                if nn > best_net:
                    best_net = nn
                    best_thr = s_thr
            learned_thr[q] = best_thr

        # Test fold
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
            thr_conf = np.quantile(train_conf, 1 - q)
            # Compute test scores
            fold_dir, fold_ret = [], []
            for si, direction, conf, r, e, t1, regf, yr in per_sym:
                sel = conf >= thr_conf
                if not sel.any():
                    continue
                # Regime score for test
                skew_t = regf[:, 0]
                ac1_t = regf[:, 1]
                # Use train percentiles for score (causal)
                skew_pct_t = np.searchsorted(np.sort(skew[np.isfinite(skew)]), skew_t) / np.sum(np.isfinite(skew))
                ac1_pct_t = np.searchsorted(np.sort(-ac1[np.isfinite(ac1)]), -ac1_t) / np.sum(np.isfinite(ac1))
                test_score = np.nan_to_num(skew_pct_t, nan=0.0) + np.nan_to_num(ac1_pct_t, nan=0.0)
                gate = test_score >= learned_thr[q] if learned_thr[q] is not None else np.ones(len(test_score), dtype=bool)
                sel = sel & gate
                if not sel.any():
                    continue
                o = np.argsort(e[sel])
                keep = greedy_nonoverlap(e[sel][o], t1[sel][o])
                dd, rr = direction[sel][o][keep], r[sel][o][keep]
                if len(dd):
                    fold_dir.append(dd)
                    fold_ret.append(rr)
                    ntr[q] += len(dd)
                    pnl = dd * rr - COST
                    if np.mean(pnl) > 0:
                        sympos[q][si] += 1
                    if q == 0.02:
                        yk = yr[sel][o][keep]
                        for yy, pp in zip(yk.astype(int) + 1970, pnl):
                            year_pnl.setdefault(int(yy), []).append(pp)
            if fold_dir:
                dd = np.concatenate(fold_dir)
                rr = np.concatenate(fold_ret)
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

    rows, yr = evaluate_regime_v2(panel, N_FOLDS, seed=0)

    print("=" * 90)
    print("REGIME FILTER v2: CALIBRATED SOFT GATE (threshold learned per-fold from training)")
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

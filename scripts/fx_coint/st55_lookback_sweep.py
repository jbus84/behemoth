"""ST55 regime-filter lookback sweep — systematically find the stable bar count.

We test lookback L in {10, 20, 30, 40, 50, 75, 100} bars for BOTH skew and ac1.
For each L we run the AND gate and report:
  - Aggregate accuracy, net, folds+, sym+ at selQ=0.02
  - Trades per year (sample sufficiency)
  - Year-stability: fraction of years positive, min year net, std of year nets
  - Regime-score distribution (are we gating out most entries or selecting a tail?)

The "best" L is the one that maximizes a utility = net - lambda * year_std,
penalizing volatile year-to-year performance. We report the Pareto frontier.

Usage: uv run python scripts/fx_coint/st55_lookback_sweep.py
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
SEL_Q = [0.02]
N_EVENTS = 60000
LOOKBACKS = [10, 20, 30, 40, 50, 75, 100]


def _regime_features(oriented_returns, entry_idx, lookback):
    """Compute causal regime features at each entry index from a lookback window."""
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
    return panel


def evaluate_lookback(panel, n_folds, seed):
    """AND gate with given lookback. Returns rows + per-year PnL."""
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
                gate = (regf[:, 0] > 0) & (regf[:, 1] < 0)
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

    results = []
    for lb in LOOKBACKS:
        panel = {s: build_regime_panel(d, frames, s, base.N_TB, N_EVENTS, rng, lookback=lb) for s in base.POOL}
        rows, yr = evaluate_lookback(panel, N_FOLDS, seed=0)
        # Compute year-stability metrics
        if yr:
            year_nets = {y: float(np.mean(v)) for y, v in sorted(yr.items())}
            n_years = len(year_nets)
            pos_years = sum(1 for v in year_nets.values() if v > 0)
            year_mean = float(np.mean(list(year_nets.values())))
            year_std = float(np.std(list(year_nets.values()))) if n_years > 1 else 0.0
            min_year = min(year_nets.values())
            max_year = max(year_nets.values())
        else:
            year_nets, n_years, pos_years, year_mean, year_std, min_year, max_year = {}, 0, 0, 0.0, 0.0, 0.0, 0.0

        q, nt, a, nn, fp, nf, sp = rows[0]
        utility = nn - 2.0 * year_std if not np.isnan(nn) else float("-inf")
        results.append({
            "lookback": lb,
            "trades": nt,
            "accuracy": a,
            "net": nn,
            "folds+": f"{fp}/{nf}",
            "sym+": f"{sp}/5",
            "n_years": n_years,
            "pos_years": pos_years,
            "year_mean": year_mean,
            "year_std": year_std,
            "min_year": min_year,
            "max_year": max_year,
            "utility": utility,
            "per_year": year_nets,
        })

    print("=" * 130)
    print("LOOKBACK SWEEP: AND gate (skew>0 & ac1<0), selQ=0.02")
    print(f"{'L':>4s} {'trades':>7s} {'acc':>6s} {'net':>7s} {'folds+':>6s} {'sym+':>5s} {'years':>5s} {'pos_yr':>6s} {'yr_mean':>8s} {'yr_std':>7s} {'min_yr':>7s} {'max_yr':>7s} {'utility':>8s}")
    print("-" * 130)
    for r in results:
        print(f"{r['lookback']:>4d} {r['trades']:>7d} {r['accuracy']:>6.3f} {r['net']:>+7.2f} {r['folds+']:>6s} {r['sym+']:>5s} {r['n_years']:>5d} {r['pos_years']:>6d} {r['year_mean']:>+8.2f} {r['year_std']:>7.2f} {r['min_year']:>+7.2f} {r['max_year']:>+7.2f} {r['utility']:>+8.2f}")
    print()

    # Per-year detail for top 3 by utility
    top3 = sorted(results, key=lambda x: x["utility"], reverse=True)[:3]
    for r in top3:
        print(f"Top by utility (L={r['lookback']}, utility={r['utility']:+.2f}):")
        print("  per-year:", " ".join(f"{y}:{v:+.1f}" for y, v in sorted(r["per_year"].items())))
        print()


if __name__ == "__main__":
    main()

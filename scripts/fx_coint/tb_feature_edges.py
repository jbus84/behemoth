"""Revisit ALL features (not just ffd_zvol20) as standalone TB edges at N=50.

The TB book uses only ffd_zvol20, but the feature assessment found 11-15 BH-significant
features at short N — including a non-FFD, POSITIVE-IC intrabar-continuation block
(intra_bar_mom, hl_pos_frac, low/high_pos_tick). Those were only ever judged at the dead
N=1..5 horizon. Here we judge every feature at the horizon where edges monetize (N=50,
triple-barrier first-touch payoff), causal walk-forward:

  per feature:
    OOS IC   = pooled Spearman(feature, first-touch ret), mean / t / sign-stability / BH-FDR
    netbps   = standalone TB book: direction learned from TRAIN IC sign (fade if IC<0,
               follow if IC>0), top-decile |feature|, non-overlap, real cost; folds+/sym+
    corrFFD  = daily-PnL correlation of that standalone book vs the ffd_zvol20 book
               (low + positive net = a genuine NEW diversifying edge)

Usage: uv run python scripts/fx_coint/tb_feature_edges.py [N_TB]
"""
# ruff: noqa: E402
from __future__ import annotations

import sys
from math import erf, sqrt
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.feature_ic_definitive import DATA, SUFFIX, build_all
from scripts.fx_coint.multiplicity import bh_reject
from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap
from scripts.fx_coint.triple_barrier import triple_barrier_core

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_TB = int(sys.argv[1]) if len(sys.argv) > 1 else 50
N_EVENTS = 40000
N_FOLDS = 5
COST = 1.0
Q_MAG = 0.90
REF = "ffd_zvol20"
SKIP = {"ent_sign"}


def _timestamps(sym):
    import polars as pl
    df = pl.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet")
    t = pd.to_datetime(df["timestamp"].to_numpy()).tz_localize(None).to_numpy().astype("datetime64[ns]")
    return t[np.argsort(t.astype("int64"))]


def build():
    cache, ts = {}, {}
    feats = None
    for s in POOL:
        logp, f, vol, bph = build_all(s)
        ts[s] = _timestamps(s)
        n = len(logp)
        warm = int(96 * bph) + 60
        ev = np.arange(warm, n - N_TB - 3)
        ev = ev[np.isfinite(vol[ev + 1]) & (vol[ev + 1] > 0)]
        rng = np.random.default_rng(0)
        ev = np.sort(rng.choice(ev, min(N_EVENTS, len(ev)), replace=False))
        entry = ev + 1
        t1, y, _, _ = triple_barrier_core(
            logp, entry, np.minimum(entry + N_TB, len(logp) - 1),
            1.0 * vol[entry] * np.sqrt(N_TB))
        if feats is None:
            feats = [k for k in f if k not in SKIP]
        cache[s] = dict(entry=entry, t1=t1, y=y, feat={k: f[k][ev] for k in feats}, ts=ts[s])
    return cache, feats


def assess(cache, feats):
    all_entry = np.concatenate([cache[s]["entry"] for s in POOL])
    fold_edges = np.quantile(all_entry, np.linspace(0, 1, N_FOLDS + 1))

    results = {}
    daily = {}            # feature -> daily pnl Series (for correlation)
    for feat in feats:
        ic_units, fold_net = [], []
        sym_pos = np.zeros(len(POOL))
        recs = []
        for k in range(1, N_FOLDS):
            lo, hi = fold_edges[k], fold_edges[k + 1]
            # train IC sign (causal direction)
            tr_sig, tr_y = [], []
            for s in POOL:
                d = cache[s]
                tr = d["entry"] < lo
                tr_sig.append(d["feat"][feat][tr])
                tr_y.append(d["y"][tr])
            tsig, ty = np.concatenate(tr_sig), np.concatenate(tr_y)
            m = np.isfinite(tsig) & np.isfinite(ty)
            if m.sum() < 200:
                continue
            ic_tr, _ = spearmanr(tsig[m], ty[m])
            direction = np.sign(ic_tr) if np.isfinite(ic_tr) and ic_tr != 0 else 1.0
            thr = np.nanquantile(np.abs(tsig[m]), Q_MAG)

            fold_pnls = []
            for si, s in enumerate(POOL):
                d = cache[s]
                te = (d["entry"] >= lo) & (d["entry"] < hi)
                sig, y = d["feat"][feat], d["y"]
                ok = te & np.isfinite(sig) & np.isfinite(y)
                if ok.sum() < 20:
                    continue
                ic, _ = spearmanr(sig[ok], y[ok])
                if np.isfinite(ic):
                    ic_units.append(ic)
                sel = ok & (np.abs(sig) >= thr)
                if not sel.any():
                    continue
                o = np.argsort(d["entry"][sel])
                e_s, t_s = d["entry"][sel][o], d["t1"][sel][o]
                # trade WITH the train IC sign: pnl = direction * sign(sig) * y - cost
                p_s = (direction * np.sign(sig[sel]) * y[sel])[o]
                ko = greedy_nonoverlap(e_s, t_s)
                pnl = p_s[ko] - COST
                if len(pnl):
                    fold_pnls.append(pnl)
                    if np.mean(pnl) > 0:
                        sym_pos[si] += 1
                    for idx, pp in zip(e_s[ko], pnl):
                        recs.append((pd.Timestamp(d["ts"][idx]).normalize(), float(pp)))
            if fold_pnls:
                fold_net.append(float(np.mean(np.concatenate(fold_pnls))))

        if not fold_net:
            continue
        ic_arr = np.array(ic_units)
        mean_ic = ic_arr.mean() if len(ic_arr) else np.nan
        t = mean_ic / (ic_arr.std(ddof=1) / np.sqrt(len(ic_arr)) + 1e-12) if len(ic_arr) > 2 else 0.0
        pval = 2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2))))
        fn = np.array(fold_net)
        results[feat] = dict(ic=mean_ic, t=t, pval=pval,
                             signstab=float(np.mean(np.sign(ic_arr) == np.sign(mean_ic))) if len(ic_arr) else np.nan,
                             net=float(fn.mean()), folds_pos=int((fn > 0).sum()), nf=len(fn),
                             sym_pos=int((sym_pos >= (N_FOLDS - 1) / 2).sum()))
        if recs:
            df = pd.DataFrame(recs, columns=["date", "pnl"])
            daily[feat] = df.groupby("date")["pnl"].sum()
    return results, daily


def main():
    cache, feats = build()
    results, daily = assess(cache, feats)
    pvals = [results[f]["pval"] for f in results]
    names = list(results)
    rej = dict(zip(names, bh_reject(pvals, 0.05)))
    ref_daily = daily.get(REF)

    order = sorted(results, key=lambda f: -results[f]["net"])
    print(f"TB feature-edge revisit @N={N_TB} (triple-barrier first-touch, top-decile, non-overlap, cost={COST})")
    print(f"{'feature':>18s} {'IC':>8s} {'t':>6s} {'signStab':>8s} {'BH':>3s} "
          f"{'net':>7s} {'folds+':>7s} {'sym+':>5s} {'corrFFD':>8s}")
    for f in order:
        r = results[f]
        corr = ""
        if ref_daily is not None and f in daily and f != REF:
            j = pd.concat([daily[f].rename("a"), ref_daily.rename("b")], axis=1).dropna()
            if len(j) > 30:
                corr = f"{j['a'].corr(j['b']):+.2f}"
        star = "*" if rej.get(f) else " "
        print(f"{f:>18s} {r['ic']:>+8.4f} {r['t']:>+6.1f} {r['signstab']:>8.2f} {star:>3s} "
              f"{r['net']:>+7.2f} {r['folds_pos']:>4d}/{r['nf']} {r['sym_pos']:>3d}/5 {corr:>8s}")


if __name__ == "__main__":
    main()

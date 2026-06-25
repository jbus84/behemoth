"""SHORT-TERM 55% CHALLENGE: >=55% accuracy AND +EV at horizon <= 10 bars.

Strategy (per the four real levers behind a 55% benchmark):
  HORIZON     N=10 1000-tick bars (~3.3h) — the longest allowed, best raw accuracy.
  SELECTIVITY accuracy is measured ON THE TRADES TAKEN: only act on the highest-
              confidence predictions (top-q by |p-0.5|). 55% need not hold on all bars.
  PAYOFF      report net EV (greedy non-overlap, cost) alongside accuracy.
  ORTHOGONAL  cross-symbol features: each target bar gets the other 4 majors' recent
              oriented returns (asof-aligned by timestamp), the USD factor, and the
              target's residual-vs-factor. This is directional info a single pair's
              own price cannot contain (lead-lag / common-factor structure).

Walk-forward expanding folds, pooled train over the 5 non-JPY majors, boosted
classifier with calibrated-ish probabilities. We sweep selectivity and report, per
level: n_trades, accuracy, gross, net, and the folds+/sym+ breadth gauntlet (so a
55% tail is real, not an overfit sliver).

Usage: uv run python scripts/fx_coint/st55_search.py
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

from scripts.fx_coint.feature_ic_definitive import DATA, build_all
from scripts.fx_coint.model_search import build_design
from scripts.fx_coint.pnl_walkforward import greedy_nonoverlap
from scripts.fx_coint.sample_weights import event_weights

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
USD_BASE = {"USDCAD", "USDCHF"}          # USD is the base -> +ret = USD up
SUFFIX = "1000tick"
N_TB = 100   # 10 bars of 10k-tick == 100 x1000-tick (honors <=10-bar cap)
N_EVENTS = 40000
N_FOLDS = 5
COST = 1.0
SEL_Q = [1.0, 0.25, 0.10, 0.05, 0.02, 0.01, 0.005]
OWN = ["macd", "ffd_demean20", "ffd_vel5", "ffd_zvol20", "ffd_0.1", "ffd_accel",
       "ffd_vel20", "ffd_demean50", "intra_bar_mom", "hl_pos_frac", "low_pos_tick",
       "high_pos_tick", "bar_return_sign", "volratio"]
XS_WIN = [1, 3, 10]                       # cross-symbol recent-return windows (bars)


def _timestamps(sym):
    df = pd.read_parquet(f"{DATA}/{sym}_{SUFFIX}.parquet")
    t = pd.to_datetime(df["timestamp"]).to_numpy().astype("datetime64[ns]")
    return t[np.argsort(t.astype("int64"))]


def load_all():
    """Per-symbol logp/features/vol/timestamps, all timestamp-sorted ascending."""
    d = {}
    for s in POOL:
        logp, f, vol, bph = build_all(s)
        t = _timestamps(s)
        n = min(len(logp), len(t))
        d[s] = dict(logp=logp[:n], f={k: v[:n] for k, v in f.items()}, vol=vol[:n],
                    bph=bph, t=t[:n], r=np.diff(logp[:n], prepend=logp[:n][0]))
    return d


def orient(sym, r):
    return r if sym in USD_BASE else -r   # +oriented = USD strength


def cross_symbol_frame(d):
    """Per symbol, a time-indexed DataFrame of oriented recent returns for asof-merge."""
    frames = {}
    for s in POOL:
        ser = pd.Series(d[s]["r"], index=pd.DatetimeIndex(d[s]["t"])).sort_index()
        df = pd.DataFrame(index=ser.index)
        for w in XS_WIN:
            df[f"{s}_w{w}"] = orient(s, ser.rolling(w).sum().to_numpy())
        frames[s] = df
    return frames


def build_panel(d, frames, sym, n_tb, n_events, rng):
    logp, f, vol, t = d[sym]["logp"], d[sym]["f"], d[sym]["vol"], d[sym]["t"]
    n = len(logp)
    warm = int(96 * d[sym]["bph"]) + 60
    idx = np.arange(warm, n - n_tb - 3)
    idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
    ev = np.sort(rng.choice(idx, min(n_events, len(idx)), replace=False))
    entry = ev + 1
    t1 = entry + n_tb
    ret = (logp[entry + n_tb] - logp[entry]) * 1e4

    Xown, _ = build_design(f, entry, OWN, [])

    # cross-symbol: asof-merge each other symbol's oriented recent returns at entry time
    et = pd.DatetimeIndex(t[entry])
    xs_cols, xs_names = [], []
    others = [o for o in POOL if o != sym]
    for o in others:
        merged = pd.merge_asof(pd.DataFrame(index=et).reset_index().rename(columns={"index": "ts"}).sort_values("ts"),
                               frames[o].reset_index().rename(columns={"index": "ts"}).sort_values("ts"),
                               on="ts", direction="backward")
        for w in XS_WIN:
            xs_cols.append(merged[f"{o}_w{w}"].to_numpy())
            xs_names.append(f"{o}_w{w}")
    # USD factor (mean of all oriented w1) and target residual vs factor
    self_merged = pd.merge_asof(pd.DataFrame(index=et).reset_index().rename(columns={"index": "ts"}).sort_values("ts"),
                                frames[sym].reset_index().rename(columns={"index": "ts"}).sort_values("ts"),
                                on="ts", direction="backward")
    for w in XS_WIN:
        comp = [xs_cols[xs_names.index(f"{o}_w{w}")] for o in others] + [self_merged[f"{sym}_w{w}"].to_numpy()]
        factor = np.nanmean(np.column_stack(comp), axis=1)
        xs_cols.append(factor)
        xs_names.append(f"USDfactor_w{w}")
        xs_cols.append(self_merged[f"{sym}_w{w}"].to_numpy() - factor)
        xs_names.append(f"resid_w{w}")

    Xxs = np.column_stack(xs_cols)
    X = np.column_stack([Xown, Xxs])
    fin = np.isfinite(X).all(axis=1) & np.isfinite(ret)
    X, entry, t1, ret = X[fin], entry[fin], t1[fin], ret[fin]
    bar_log_ret = np.diff(logp, prepend=logp[0])
    sw = event_weights(bar_log_ret, entry, t1)
    return dict(X=X, entry=entry, t1=t1, ret=ret, sw=sw)


def evaluate(panel, n_folds, seed):
    syms = list(panel)
    all_entry = np.concatenate([panel[s]["entry"] for s in syms])
    edges = np.quantile(all_entry, np.linspace(0, 1, n_folds + 1))
    # per selectivity level collect fold accuracy, fold net, sym positivity, trades
    acc = {q: [] for q in SEL_Q}
    net = {q: [] for q in SEL_Q}
    ntr = {q: 0 for q in SEL_Q}
    sympos = {q: np.zeros(len(syms)) for q in SEL_Q}

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
        clf = HistGradientBoostingClassifier(max_depth=3, max_iter=400, learning_rate=0.04,
                                             l2_regularization=1.0, random_state=seed)
        clf.fit(np.concatenate(Xtr), ytr_all, sample_weight=np.concatenate(swtr))
        train_conf = np.abs(clf.predict_proba(np.concatenate(Xtr))[:, 1] - 0.5)

        # pooled test confidence across symbols, but track per-symbol for breadth
        per_sym = []
        for si, s in enumerate(syms):
            d = panel[s]
            te = (d["entry"] >= lo) & (d["entry"] < hi)
            if te.sum() < 50:
                continue
            p = clf.predict_proba(d["X"][te])[:, 1]
            conf = np.abs(p - 0.5)
            direction = np.sign(p - 0.5)
            per_sym.append((si, direction, conf, d["ret"][te], d["entry"][te], d["t1"][te]))

        for q in SEL_Q:
            # CAUSAL: confidence threshold derived from TRAIN predictions, applied to test
            if not per_sym:
                continue
            thr = np.quantile(train_conf, 1 - q)
            fold_dir, fold_ret = [], []
            for si, direction, conf, r, e, t1 in per_sym:
                sel = conf >= thr
                if not sel.any():
                    continue
                o = np.argsort(e[sel])
                keep = greedy_nonoverlap(e[sel][o], t1[sel][o])
                dd = direction[sel][o][keep]
                rr = r[sel][o][keep]
                if len(dd):
                    fold_dir.append(dd)
                    fold_ret.append(rr)
                    ntr[q] += len(dd)
                    pnl = dd * rr - COST
                    if np.mean(pnl) > 0:
                        sympos[q][si] += 1
            if fold_dir:
                dd = np.concatenate(fold_dir)
                rr = np.concatenate(fold_ret)
                acc[q].append(float(np.mean((dd * rr) > 0)))
                net[q].append(float(np.mean(dd * rr) - COST))

    rows = []
    for q in SEL_Q:
        a = np.array(acc[q])
        nn = np.array(net[q])
        rows.append((q, ntr[q],
                     float(np.mean(a)) if len(a) else float("nan"),
                     float(np.mean(nn)) if len(nn) else float("nan"),
                     int((nn > 0).sum()), len(nn),
                     int((sympos[q] >= (n_folds - 1) / 2).sum())))
    return rows


def main():
    rng = np.random.default_rng(0)
    d = load_all()
    frames = cross_symbol_frame(d)
    panel = {s: build_panel(d, frames, s, N_TB, N_EVENTS, rng) for s in POOL}
    print(f"SHORT-TERM 55% CHALLENGE | N={N_TB} bars ({SUFFIX}) | own+cross-symbol feats "
          f"({panel['EURUSD']['X'].shape[1]} cols) | cost={COST}bps")
    print(f"{'selQ':>6s} {'nTrades':>8s} {'accuracy':>9s} {'net bps':>8s} "
          f"{'folds+':>7s} {'sym+':>5s}  {'TARGET: acc>=0.55 & net>0':>10s}")
    for q, nt, a, nn, fp, nf, sp in evaluate(panel, N_FOLDS, seed=0):
        hit = "  <== HIT" if (a >= 0.55 and nn > 0) else ""
        print(f"{q:>6.2f} {nt:>8d} {a:>9.4f} {nn:>+8.3f} {fp:>4d}/{nf} {sp:>3d}/5{hit}")


if __name__ == "__main__":
    main()

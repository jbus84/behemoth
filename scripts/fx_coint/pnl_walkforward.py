"""Decisive tradeability gate: NON-OVERLAPPING trades + WALK-FORWARD.

pnl_assessment showed gated+top_mag net-positive after cost on a single chrono
split, but on overlapping trades. This is the mirage-killer: it (1) selects only
NON-OVERLAPPING trades (next entry >= previous trade's first-touch exit, so every
P&L draw is independent), and (2) evaluates over EXPANDING walk-forward folds with
selection thresholds fit only on data before each fold.

Strategy unchanged: fade ffd_zvol20, payoff = triple-barrier first-touch return.
Reports per (N, isolation): independent trade count, mean net bps/trade at real
cost, fraction of walk-forward folds positive, fraction of symbols positive.

Usage: uv run python scripts/fx_coint/pnl_walkforward.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
from scipy.stats import rankdata

try:  # noqa: SIM105
    matplotlib.use("Agg")
except RuntimeError:
    pass
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feature_ic_definitive import build_all  # noqa: E402
from triple_barrier import triple_barrier_core  # noqa: E402

POOL = ["AUDUSD", "EURUSD", "GBPUSD", "USDCAD", "USDCHF"]
N_GRID = [10, 20, 30, 50]
N_EVENTS = 40000
SIGNAL = "ffd_zvol20"
COST = 1.0          # round-trip bps (realistic Razor-type)
N_FOLDS = 5
ISOLATIONS = ["top_mag", "gated+top_mag"]
OUT = Path("reports/pnl_walkforward")


def greedy_nonoverlap(entry: np.ndarray, t1: np.ndarray) -> np.ndarray:
    """Keep trades whose entry is at/after the previous kept trade's exit (t1).
    entry/t1 are time-sorted index arrays; returns a boolean keep-mask."""
    keep = np.zeros(len(entry), dtype=bool)
    last_exit = -1
    for i in range(len(entry)):
        if entry[i] >= last_exit:
            keep[i] = True
            last_exit = t1[i]
    return keep



def _fade_pnl(logp, vol, ev, n_tb):
    entry = ev + 1
    t1, ret, _, _ = triple_barrier_core(
        logp, entry, np.minimum(entry + n_tb, len(logp) - 1),
        1.0 * vol[entry] * np.sqrt(n_tb))
    return entry, t1, ret


def _rank(a):
    out = np.full(len(a), np.nan)
    ok = np.isfinite(a)
    out[ok] = rankdata(a[ok]) / ok.sum()
    return out


def train_relative_topdecile(
    sel_abs: np.ndarray,
    feat_abs: np.ndarray,
    tr_mask: np.ndarray,
    q: float = 0.90,
) -> np.ndarray:
    """Return boolean mask (all rows) of top-decile combined score, calibrated on
    train rows only.  Test rows receive train-relative percentiles via searchsorted
    so no future data leaks into the selection threshold."""
    tr_sel = np.sort(sel_abs[tr_mask & np.isfinite(sel_abs)])
    tr_feat = np.sort(feat_abs[tr_mask & np.isfinite(feat_abs)])
    n_tr_sel = len(tr_sel)
    n_tr_feat = len(tr_feat)
    pct_sel = np.searchsorted(tr_sel, sel_abs, side="right") / n_tr_sel if n_tr_sel else np.zeros(len(sel_abs))
    pct_feat = np.searchsorted(tr_feat, feat_abs, side="right") / n_tr_feat if n_tr_feat else np.zeros(len(feat_abs))
    comb = (pct_sel + pct_feat) / 2.0
    # threshold from train rows only
    tr_comb = comb[tr_mask]
    thr = np.nanquantile(tr_comb, q) if len(tr_comb) else 1.0
    return comb >= thr


def model_oos_pnl(sym_data, fit_predict, cost=1.0, n_folds=5) -> dict:
    """Walk-forward OOS net-bps of a model-mu strategy: sign(mu) side, top-decile
    |mu| selection, non-overlap. `sym_data[s]` carries pre-built X,y,entry,t1,ret,sw;
    `fit_predict(train_dict, test_dict) -> mu_test` fits on train (modelling lives in
    the caller) and returns mu for the test rows."""
    syms = list(sym_data)
    all_entry = np.concatenate([sym_data[s]["entry"] for s in syms])
    edges = np.quantile(all_entry, np.linspace(0, 1, n_folds + 1))
    fold_net, n_trades, sym_pos = [], 0, np.zeros(len(syms))
    for k in range(1, n_folds):
        lo, hi = edges[k], edges[k + 1]
        fold = []
        for si, s in enumerate(syms):
            d = sym_data[s]
            tr = d["entry"] < lo
            te = (d["entry"] >= lo) & (d["entry"] < hi)
            if tr.sum() < 200 or te.sum() < 20:
                continue
            mu = np.asarray(fit_predict({kk: vv[tr] for kk, vv in d.items()},
                                        {kk: vv[te] for kk, vv in d.items()}), dtype=float)
            ret_te, ent_te, t1_te = d["ret"][te], d["entry"][te], d["t1"][te]
            ok = np.isfinite(mu) & np.isfinite(ret_te)
            thr = np.nanquantile(np.abs(mu[ok]), 0.90) if ok.sum() else np.inf
            sel = ok & (np.abs(mu) >= thr)
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
    return dict(net=float(np.mean(fold_net)) if len(fold_net) else float("nan"),
                folds_pos=int((fold_net > 0).sum()),
                sym_pos=int((sym_pos >= (n_folds - 1) / 2).sum()),
                n_trades=n_trades)


def marginal_lift(
    cache, evset, n_tb, feature, role, cost=1.0, n_folds=5, orient: float = 1.0
) -> dict:
    """Walk-forward non-overlap net-bps lift of `feature` (in `role`) over the
    fixed base (fade ffd_zvol20 x top-decile |ffd_zvol20|).

    orient: multiply feature before taking sign in direction role (pass -1 for
    anti-correlated features to align with the fade direction)."""
    sym_d = {}
    for s in POOL:
        logp, f, vol, bph = cache[s]
        ev = evset[s]
        entry, t1, ret = _fade_pnl(logp, vol, ev, n_tb)
        pnl = -np.sign(f[SIGNAL][ev]) * ret
        sym_d[s] = dict(entry=entry, t1=t1, pnl=pnl,
                        sel=f[SIGNAL][ev], feat=f[feature][ev])
    all_entry = np.concatenate([sym_d[s]["entry"] for s in POOL])
    edges = np.quantile(all_entry, np.linspace(0, 1, n_folds + 1))

    def fold_net(select_fn):
        nets = []
        total_trades = 0
        for k in range(1, n_folds):
            lo, hi = edges[k], edges[k + 1]
            fold = []
            for s in POOL:
                d = sym_d[s]
                tr = d["entry"] < lo
                te = (d["entry"] >= lo) & (d["entry"] < hi)
                if tr.sum() < 200 or te.sum() < 20:
                    continue
                sel = select_fn(d, tr, te)
                order = np.argsort(d["entry"][sel])
                ko = greedy_nonoverlap(d["entry"][sel][order], d["t1"][sel][order])
                p = d["pnl"][sel][order][ko] - cost
                if len(p):
                    fold.append(p)
                    total_trades += len(p)
            if fold:
                nets.append(np.mean(np.concatenate(fold)))
        return np.array(nets), total_trades

    def base_select(d, tr, te):
        thr = np.nanquantile(np.abs(d["sel"][tr]), 0.90)
        return te & (np.abs(d["sel"]) >= thr) & np.isfinite(d["pnl"])

    def cand_select(d, tr, te):
        base = base_select(d, tr, te)
        if role == "magnitude":
            return te & train_relative_topdecile(np.abs(d["sel"]), np.abs(d["feat"]), tr) & np.isfinite(d["pnl"])
        if role == "direction":
            feat = orient * d["feat"]
            fade_dir = -np.sign(d["sel"])
            return base & (np.sign(feat) == fade_dir)
        # conditioner: restrict to best-train-net-bps tercile of feature
        q1, q2 = np.nanquantile(d["feat"][tr], [1 / 3, 2 / 3])
        terc_masks = [d["feat"] <= q1, (d["feat"] > q1) & (d["feat"] <= q2), d["feat"] > q2]
        # pick tercile by train net-bps
        best, best_net = None, -1e9
        btr = base_select(d, tr, tr)
        for ti, m in enumerate(terc_masks):
            mm = btr & m
            if mm.sum() > 20:
                net = np.nanmean(d["pnl"][mm]) - cost
                if net > best_net:
                    best, best_net = ti, net
        if best is None:
            return np.zeros(len(te), dtype=bool)
        return base & terc_masks[best]

    base_net, base_trades = fold_net(base_select)
    cand_net, cand_trades = fold_net(cand_select)
    return dict(base_net=float(np.mean(base_net)) if len(base_net) else float("nan"),
                cand_net=float(np.mean(cand_net)) if len(cand_net) else float("nan"),
                lift=float(np.mean(cand_net) - np.mean(base_net)) if len(cand_net) and len(base_net) else float("nan"),
                folds_pos=int((cand_net > 0).sum()),
                n_trades=int(cand_trades))


def _select(iso, sig, age, adf, thr):
    keep = np.isfinite(sig)
    if "top_mag" in iso:
        keep &= np.abs(sig) >= thr["mag"]
    if "gated" in iso:
        keep &= (age >= thr["age_hi"]) & (adf <= thr["adf_lo"])
    return keep


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    cache = {s: build_all(s) for s in POOL}
    evset = {}
    for s in POOL:
        logp, f, vol, bph = cache[s]
        n = len(logp)
        warm = int(96 * bph) + 60
        idx = np.arange(warm, n - max(N_GRID) - 3)
        idx = idx[np.isfinite(vol[idx + 1]) & (vol[idx + 1] > 0)]
        evset[s] = np.sort(rng.choice(idx, min(N_EVENTS, len(idx)), replace=False))

    fold_curves = {}    # (N, iso) -> array of per-fold pooled net bps
    for n_tb in N_GRID:
        print("=" * 92)
        print(f"WALK-FORWARD NON-OVERLAP NET-P&L — fade {SIGNAL}, N={n_tb}, cost={COST}bps round-trip")
        print(f"  {N_FOLDS} expanding folds | independent trades only | pooled 5 majors")
        print("=" * 92)
        print(f"  {'isolation':16s} {'indep_trades':>12s} {'net bps':>9s} {'folds+':>7s} {'sym+':>6s}")
        for iso in ISOLATIONS:
            # gather per-symbol selected, non-overlapping trades with timestamps
            sym_trades = {}
            for s in POOL:
                logp, f, vol, bph = cache[s]
                ev = evset[s]
                entry = ev + 1
                t1arr, y, _, _ = triple_barrier_core(
                    logp, entry, np.minimum(entry + n_tb, len(logp) - 1),
                    1.0 * vol[entry] * np.sqrt(n_tb))
                sig, age, adf = f[SIGNAL][ev], f["dev_age"][ev], f["adf_sup"][ev]
                # thresholds fit on first 40% (pre-walk-forward burn-in); refit per fold below
                pnl = -np.sign(sig) * y
                sym_trades[s] = dict(entry=entry, t1=t1arr, sig=sig, age=age, adf=adf, pnl=pnl)

            # expanding walk-forward over the time axis (shared bar-index folds)
            all_entry = np.concatenate([sym_trades[s]["entry"] for s in POOL])
            edges = np.quantile(all_entry, np.linspace(0, 1, N_FOLDS + 1))
            fold_net, n_indep, sym_pos = [], 0, np.zeros(len(POOL))
            for k in range(1, N_FOLDS):
                lo, hi = edges[k], edges[k + 1]
                fold_pnls = []
                for si, s in enumerate(POOL):
                    d = sym_trades[s]
                    tr = d["entry"] < lo            # train = everything before fold
                    te = (d["entry"] >= lo) & (d["entry"] < hi)
                    if tr.sum() < 200 or te.sum() < 20:
                        continue
                    thr = dict(
                        mag=np.nanquantile(np.abs(d["sig"][tr]), 0.90),
                        age_hi=np.nanquantile(d["age"][tr], 0.66),
                        adf_lo=np.nanquantile(d["adf"][tr], 0.34))
                    sel = _select(iso, d["sig"], d["age"], d["adf"], thr) & te & np.isfinite(d["pnl"])
                    order = np.argsort(d["entry"][sel])
                    e_sel, t_sel, p_sel = d["entry"][sel][order], d["t1"][sel][order], d["pnl"][sel][order]
                    ko = greedy_nonoverlap(e_sel, t_sel)
                    p = p_sel[ko] - COST
                    if len(p):
                        fold_pnls.append(p)
                        n_indep += len(p)
                        if np.mean(p) > 0:
                            sym_pos[si] += 1
                if fold_pnls:
                    fold_net.append(np.mean(np.concatenate(fold_pnls)))
            fold_net = np.array(fold_net)
            fold_curves[(n_tb, iso)] = fold_net
            folds_pos = int((fold_net > 0).sum())
            # a symbol counts as + if positive in a majority of folds it appeared
            sym_plus = int((sym_pos >= (N_FOLDS - 1) / 2).sum())
            print(f"  {iso:16s} {n_indep:>12d} {np.mean(fold_net):+9.3f} "
                  f"{folds_pos:>4d}/{len(fold_net)} {sym_plus:>4d}/5")
        print()

    # plot: per-fold net bps (walk-forward stability) for gated+top_mag
    fig, ax = plt.subplots(figsize=(9, 5))
    for n_tb in N_GRID:
        fc = fold_curves.get((n_tb, "gated+top_mag"))
        if fc is not None and len(fc):
            ax.plot(range(1, len(fc) + 1), fc, marker="o", label=f"N={n_tb}", linewidth=1.7)
    ax.axhline(0, color="k", linewidth=1)
    ax.set_xlabel("walk-forward fold (chronological)")
    ax.set_ylabel(f"net bps/trade (cost={COST})")
    ax.set_title("Walk-forward non-overlap net P&L — gated+top_mag (fade ffd_zvol20)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "walkforward_net_pnl.png", dpi=110)
    plt.close(fig)
    print(f"plot -> {OUT / 'walkforward_net_pnl.png'}")


if __name__ == "__main__":
    main()

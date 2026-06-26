"""ST55 L=30 regime filter — trades per year, win rate, and payoff structure.

Runs the confirmed-best config (L=30 AND gate, selQ=0.02) and reports:
  - Trades per year, per symbol
  - Win rate (accuracy) per year
  - Avg gross move, win/loss size, skew per year
  - Fold-level breakdown

Usage: uv run python scripts/fx_coint/st55_l30_report.py
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
SEL_Q = 0.02
N_EVENTS = 60000
LOOKBACK = 30


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


def build_regime_panel(d, frames, sym, n_tb, n_events, rng):
    panel = base.build_panel(d, frames, sym, n_tb, n_events, rng)
    r = base.orient(sym, d[sym]["r"])
    reg = _regime_features(r, panel["entry"], lookback=LOOKBACK)
    panel["regime"] = reg
    # Add entry year
    t = pd.DatetimeIndex(base._timestamps(sym)).to_numpy().astype("datetime64[ns]")
    panel["year"] = t[panel["entry"]].astype("datetime64[Y]").astype(int) + 1970
    return panel


def evaluate_l30(panel, n_folds, seed):
    syms = list(panel)
    all_entry = np.concatenate([panel[s]["entry"] for s in syms])
    edges = np.quantile(all_entry, np.linspace(0, 1, n_folds + 1))

    year_rows = []
    per_sym_rows = []

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

        for _si, s in enumerate(syms):
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
            o = np.argsort(d["entry"][te][sel])
            keep = greedy_nonoverlap(d["entry"][te][sel][o], d["t1"][te][sel][o])
            dd, rr = direction[sel][o][keep], d["ret"][te][sel][o][keep]
            yy = d["year"][te][sel][o][keep]
            if len(dd):
                pnl = dd * rr - COST
                wins = dd * rr > 0
                for y in np.unique(yy):
                    mask = yy == y
                    year_rows.append({
                        "fold": fk,
                        "sym": s,
                        "year": int(y),
                        "n": int(mask.sum()),
                        "acc": float(np.mean(wins[mask])),
                        "net": float(np.mean(pnl[mask])),
                        "gross": float(np.mean(dd[mask] * rr[mask])),
                        "win_avg": float(np.mean((dd * rr)[mask & wins])) if wins[mask].any() else 0.0,
                        "loss_avg": float(np.mean((dd * rr)[mask & ~wins])) if (~wins[mask]).any() else 0.0,
                    })
                per_sym_rows.append({
                    "fold": fk, "sym": s,
                    "n": len(dd), "acc": float(np.mean(wins)),
                    "net": float(np.mean(pnl)), "gross": float(np.mean(dd * rr)),
                    "win_avg": float(np.mean((dd * rr)[wins])) if wins.any() else 0.0,
                    "loss_avg": float(np.mean((dd * rr)[~wins])) if (~wins).any() else 0.0,
                })

    return year_rows, per_sym_rows


def main():
    rng = np.random.default_rng(0)
    d = base.load_all()
    frames = base.cross_symbol_frame(d)
    panel = {s: build_regime_panel(d, frames, s, base.N_TB, N_EVENTS, rng) for s in base.POOL}

    year_rows, sym_rows = evaluate_l30(panel, N_FOLDS, seed=0)

    # Aggregate per year
    yr_df = pd.DataFrame(year_rows)
    yr_agg = yr_df.groupby("year").agg(
        n_trades=("n", "sum"),
        n_syms=("sym", "nunique"),
        accuracy=("acc", lambda x: np.average(x, weights=yr_df.loc[x.index, "n"])),
        net=("net", lambda x: np.average(x, weights=yr_df.loc[x.index, "n"])),
        gross=("gross", lambda x: np.average(x, weights=yr_df.loc[x.index, "n"])),
        win_avg=("win_avg", lambda x: np.average(x, weights=yr_df.loc[x.index, "n"])),
        loss_avg=("loss_avg", lambda x: np.average(x, weights=yr_df.loc[x.index, "n"])),
    ).reset_index()

    print("=" * 110)
    print(f"ST55 L={LOOKBACK} REGIME FILTER — PER-YEAR BREAKDOWN")
    print(f"{'Year':>6s} {'Trades':>7s} {'Syms':>5s} {'Accuracy':>9s} {'Net(bps)':>9s} {'Gross':>7s} {'WinAvg':>7s} {'LossAvg':>8s} {'W/L':>5s}")
    print("-" * 110)
    total_n = 0
    for _, r in yr_agg.iterrows():
        wl = r["win_avg"] / abs(r["loss_avg"]) if r["loss_avg"] != 0 else float("inf")
        print(f"{int(r['year']):>6d} {int(r['n_trades']):>7d} {int(r['n_syms']):>5d} {r['accuracy']:>9.4f} {r['net']:>+9.2f} {r['gross']:>+7.2f} {r['win_avg']:>+7.2f} {r['loss_avg']:>+8.2f} {wl:>5.2f}")
        total_n += int(r["n_trades"])
    print("-" * 110)

    # Overall — use sym_rows
    sym_df = pd.DataFrame(sym_rows)
    all_n = int(sym_df["n"].sum())
    weighted_acc = np.average(sym_df["acc"], weights=sym_df["n"])
    weighted_net = np.average(sym_df["net"], weights=sym_df["n"])
    weighted_gross = np.average(sym_df["gross"], weights=sym_df["n"])
    weighted_win = np.average(sym_df["win_avg"], weights=sym_df["n"])
    weighted_loss = np.average(sym_df["loss_avg"], weights=sym_df["n"])
    n_years = yr_agg["year"].nunique()
    trades_per_year = total_n / n_years if n_years > 0 else 0

    print(f"OVERALL: {all_n} trades across {n_years} years = ~{trades_per_year:.0f} trades/year")
    print(f"  Accuracy: {weighted_acc:.4f}  |  Net: {weighted_net:+.2f} bps  |  Gross: {weighted_gross:+.2f} bps")
    print(f"  Win avg: {weighted_win:+.2f} bps  |  Loss avg: {weighted_loss:+.2f} bps  |  W/L: {weighted_win/abs(weighted_loss):.2f}")
    print()

    # Per-symbol
    print("=" * 90)
    print("PER-SYMBOL AGGREGATE (across all folds)")
    print(f"{'Sym':>7s} {'Trades':>7s} {'Accuracy':>9s} {'Net(bps)':>9s} {'Gross':>7s} {'WinAvg':>7s} {'LossAvg':>8s}")
    print("-" * 90)
    sym_agg = sym_df.groupby("sym").agg(
        n=("n", "sum"),
        acc=("acc", lambda x: np.average(x, weights=sym_df.loc[x.index, "n"])),
        net=("net", lambda x: np.average(x, weights=sym_df.loc[x.index, "n"])),
        gross=("gross", lambda x: np.average(x, weights=sym_df.loc[x.index, "n"])),
        win_avg=("win_avg", lambda x: np.average(x, weights=sym_df.loc[x.index, "n"])),
        loss_avg=("loss_avg", lambda x: np.average(x, weights=sym_df.loc[x.index, "n"])),
    ).reset_index()
    for _, r in sym_agg.iterrows():
        print(f"{r['sym']:>7s} {int(r['n']):>7d} {r['acc']:>9.4f} {r['net']:>+9.2f} {r['gross']:>+7.2f} {r['win_avg']:>+7.2f} {r['loss_avg']:>+8.2f}")


if __name__ == "__main__":
    main()

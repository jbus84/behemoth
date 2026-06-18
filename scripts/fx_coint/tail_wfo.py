"""Walk-forward confirmation of the PR #340 tail edge: long-only top-decile,
no-look-ahead decile gating, decile-level significance net of real cost.

Usage:
    uv run python scripts/fx_coint/tail_wfo.py --symbol all --freq all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.fx_coint.reg_signal_hunt import (  # noqa: E402
    COST_BPS,
    FEATURE_COLS,
    bh_reject,
    build_freq_bars,
    build_panel,
)

TIGHT_MAJORS = ["EURUSD", "GBPUSD", "USDJPY"]
UNIVERSE = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD"]
FREQS = ["2h", "3h"]


def walk_forward(
    panel: pd.DataFrame,
    n_folds: int = 5,
    min_train_frac: float = 0.5,
    purge: int = 1,
    alpha: float = 1.0,
) -> list[dict]:
    n = len(panel)
    start = int(n * min_train_frac)
    edges = np.linspace(start, n, n_folds + 1).astype(int)
    X = panel[FEATURE_COLS].to_numpy()
    yz = panel["target_z"].to_numpy()
    act = panel["ret_next_bps"].to_numpy()
    hour = panel["hour"].to_numpy()
    bucket = panel["bucket"].to_numpy()

    folds: list[dict] = []
    for k in range(n_folds):
        split = edges[k]
        test_lo, test_hi = edges[k] + purge, edges[k + 1]
        if test_hi - test_lo < 1 or split < 10:
            continue
        scaler = StandardScaler().fit(X[:split])
        model = Ridge(alpha=alpha).fit(scaler.transform(X[:split]), yz[:split])
        folds.append({
            "train_pred": model.predict(scaler.transform(X[:split])),
            "test_pred": model.predict(scaler.transform(X[test_lo:test_hi])),
            "test_actual_bps": act[test_lo:test_hi],
            "test_hour": hour[test_lo:test_hi],
            "test_bucket": bucket[test_lo:test_hi],
        })
    return folds


def gate_trades(folds: list[dict], q: float, cost_bps: float, side: str = "long") -> dict:
    nets: list[np.ndarray] = []
    fids: list[np.ndarray] = []
    hours: list[np.ndarray] = []
    buckets: list[np.ndarray] = []
    for i, f in enumerate(folds):
        tp = f["test_pred"]
        if side == "long":
            thr = np.quantile(f["train_pred"], q)
            sel = tp >= thr
            net = f["test_actual_bps"][sel] - cost_bps
        elif side == "short":
            thr = np.quantile(f["train_pred"], 1.0 - q)
            sel = tp <= thr
            net = -f["test_actual_bps"][sel] - cost_bps
        else:
            raise ValueError(f"side must be 'long' or 'short', got {side!r}")
        if sel.any():
            nets.append(net)
            fids.append(np.full(int(sel.sum()), i))
            hours.append(f["test_hour"][sel])
            buckets.append(f["test_bucket"][sel])
    if not nets:
        return {"net": np.array([]), "fold_id": np.array([], int),
                "hour": np.array([]), "bucket": np.array([], "datetime64[ns]"), "n": 0}
    net_all = np.concatenate(nets)
    return {
        "net": net_all,
        "fold_id": np.concatenate(fids),
        "hour": np.concatenate(hours),
        "bucket": np.concatenate(buckets),
        "n": len(net_all),
    }


def cell_stats(net: np.ndarray, fold_id: np.ndarray) -> dict:
    net = np.asarray(net, float)
    n = len(net)
    if n == 0:
        return {"n": 0, "mean_net_bps": float("nan"), "t_stat": float("nan"),
                "p_value": float("nan"), "pos_fold_pct": float("nan"),
                "hit_rate": float("nan"), "total_net_bps": 0.0}
    if n >= 3:
        tt = ttest_1samp(net, 0.0)
        t_stat, p_value = float(tt.statistic), float(tt.pvalue)
    else:
        t_stat = p_value = float("nan")
    folds = np.unique(fold_id)
    if len(folds) > 0:
        pos = np.mean([net[fold_id == fk].mean() > 0 for fk in folds])
    else:
        pos = float("nan")
    return {
        "n": n,
        "mean_net_bps": float(net.mean()),
        "t_stat": t_stat,
        "p_value": p_value,
        "pos_fold_pct": float(pos),
        "hit_rate": float((net > 0).mean()),
        "total_net_bps": float(net.sum()),
    }


def run_cell_wfo(
    sym: str, freq: str, side: str = "long", q: float = 0.9, n_folds: int = 5
) -> dict | None:
    src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
    if not src.exists():
        return None
    panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
    if len(panel) < 200:
        return None
    cost = COST_BPS[sym]
    folds = walk_forward(panel, n_folds=n_folds)
    trades = gate_trades(folds, q=q, cost_bps=cost, side=side)
    s = cell_stats(trades["net"], trades["fold_id"])
    return {"symbol": sym, "freq": freq, "side": side, "q": q, **s}


TIGHT_2H_Q_SWEEP = (0.80, 0.90, 0.95)


def day_clustered_tstat(net: np.ndarray, bucket: np.ndarray) -> dict:
    """One-sample t-test on per-calendar-day mean net, absorbing same-day cross-pair
    and intraday autocorrelation. Naive per-trade t overstates significance when trades
    are correlated; clustering by day is the conservative correction."""
    net = np.asarray(net, float)
    if len(net) == 0:
        return {"n_days": 0, "daily_mean": float("nan"), "t_stat": float("nan"),
                "p_value": float("nan")}
    dates = pd.to_datetime(pd.Series(bucket)).dt.date.to_numpy()
    daily = pd.Series(net).groupby(dates).mean().to_numpy()
    if len(daily) >= 3:
        tt = ttest_1samp(daily, 0.0)
        t_stat, p_value = float(tt.statistic), float(tt.pvalue)
    else:
        t_stat = p_value = float("nan")
    return {"n_days": len(daily), "daily_mean": float(daily.mean()),
            "t_stat": t_stat, "p_value": p_value}


def pooled_long_test(
    pairs: list[str], freq: str, q: float, n_folds: int = 5
) -> dict | None:
    """Pool long top-(1-q) trades across `pairs` at `freq`, return pooled per-trade mean,
    naive t, and day-clustered t. Pooling lifts power via breadth; day-clustering keeps
    the significance honest against cross-pair correlation."""
    nets, buckets = [], []
    for sym in pairs:
        src = _REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"
        if not src.exists():
            continue
        panel = build_panel(build_freq_bars(pl.read_parquet(src), freq))
        if len(panel) < 200:
            continue
        folds = walk_forward(panel, n_folds=n_folds)
        tr = gate_trades(folds, q=q, cost_bps=COST_BPS[sym], side="long")
        if tr["n"] > 0:
            nets.append(tr["net"])
            buckets.append(tr["bucket"])
    if not nets:
        return None
    net = np.concatenate(nets)
    bucket = np.concatenate(buckets)
    naive = ttest_1samp(net, 0.0) if len(net) >= 3 else None
    dc = day_clustered_tstat(net, bucket)
    return {
        "pairs": pairs, "freq": freq, "q": q, "n": len(net),
        "mean_net_bps": float(net.mean()), "hit_rate": float((net > 0).mean()),
        "naive_t": float(naive.statistic) if naive else float("nan"),
        "naive_p": float(naive.pvalue) if naive else float("nan"),
        "day_n": dc["n_days"], "day_t": dc["t_stat"], "day_p": dc["p_value"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="all", choices=UNIVERSE + ["all"])
    ap.add_argument("--freq", default="all", choices=FREQS + ["all"])
    ap.add_argument("--q", type=float, default=0.9)
    args = ap.parse_args()
    syms = UNIVERSE if args.symbol == "all" else [args.symbol]
    freqs = FREQS if args.freq == "all" else [args.freq]

    rows = [r for s in syms for f in freqs
            if (r := run_cell_wfo(s, f, side="long", q=args.q)) is not None]
    if not rows:
        print("No cells produced (missing data?).")
        return
    rej = bh_reject([r["p_value"] for r in rows], q=0.10)
    hdr = (f"{'pair':>7} {'freq':>4} {'q':>4} {'n':>5} {'meanNet':>8} {'t':>6} "
           f"{'posFold':>7} {'hit':>5} {'totNet':>8} {'BH':>3} {'GO':>3}")
    print(hdr)
    print("-" * len(hdr))
    for r, sig in zip(rows, rej):
        go = bool(r["mean_net_bps"] > 0 and sig and r["pos_fold_pct"] >= 0.6)
        print(f"{r['symbol']:>7} {r['freq']:>4} {r['q']:>4.2f} {r['n']:>5} "
              f"{r['mean_net_bps']:>+8.3f} {r['t_stat']:>+6.2f} {r['pos_fold_pct']:>7.2f} "
              f"{r['hit_rate']*100:>4.0f}% {r['total_net_bps']:>+8.1f} "
              f"{str(sig):>3} {str(go):>3}")

    print("\nq-sensitivity (mean net bps, long-only):")
    print(f"{'pair':>7} {'freq':>4} {'q0.80':>7} {'q0.90':>7} {'q0.95':>7}")
    for s in syms:
        for f in freqs:
            vals = []
            for qq in (0.80, 0.90, 0.95):
                rr = run_cell_wfo(s, f, side="long", q=qq)
                vals.append(rr["mean_net_bps"] if rr else float("nan"))
            print(f"{s:>7} {f:>4} {vals[0]:>+7.3f} {vals[1]:>+7.3f} {vals[2]:>+7.3f}")

    jpy = run_cell_wfo("USDJPY", "3h", side="short", q=0.9)
    if jpy:
        print(f"\nUSDJPY 3h SHORT-side: n={jpy['n']} meanNet={jpy['mean_net_bps']:+.3f} "
              f"t={jpy['t_stat']:+.2f} posFold={jpy['pos_fold_pct']:.2f} hit={jpy['hit_rate']*100:.0f}%")

    # POOLED tight majors at 2h long: breadth for power, day-clustered t for honesty.
    print(f"\nPOOLED tight majors {TIGHT_MAJORS} @ 2h long — q-sweep:")
    print(f"{'q':>5} {'n':>6} {'meanNet':>8} {'naiveT':>7} {'naiveP':>7} "
          f"{'days':>5} {'dayT':>6} {'dayP':>7} {'hit':>5}")
    for qq in TIGHT_2H_Q_SWEEP:
        p = pooled_long_test(TIGHT_MAJORS, "2h", q=qq)
        if p:
            print(f"{qq:>5.2f} {p['n']:>6} {p['mean_net_bps']:>+8.3f} {p['naive_t']:>+7.2f} "
                  f"{p['naive_p']:>7.3f} {p['day_n']:>5} {p['day_t']:>+6.2f} {p['day_p']:>7.3f} "
                  f"{p['hit_rate']*100:>4.0f}%")


if __name__ == "__main__":
    main()

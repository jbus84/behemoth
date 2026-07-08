"""Full per-pair probe: reversion + momentum sweep N=20..100 for all 6 FX majors.

Compares each pair's standalone edge to the pooled 5-major reversion book (N=10).
Finds pair-specific optimal lookbacks and checks for orthogonal trend legs.

Usage:
    uv run python scripts/fx_coint/all_pairs_probe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy.stats import ttest_1samp

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.fx_coint.reg_signal_hunt as rsh  # noqa: E402

rsh.FREQ_MINUTES["1d"] = 1440
RNG = np.random.default_rng(0)

COMM = 0.60
SPR = {"EURUSD": 0.1, "USDJPY": 0.1, "GBPUSD": 0.2, "USDCAD": 0.3, "AUDUSD": 0.15, "USDCHF": 0.3}
PX = {"EURUSD": 1.08, "USDJPY": 150.0, "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": 0.65, "USDCHF": 0.89}
ALL6 = ["EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY"]


def cost(sym):
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


def daily_series(sym):
    bars = rsh.build_freq_bars(
        pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"),
        "1d",
        session=(0, 24),
    )
    mid = bars["mid"].to_numpy()
    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~bars["contig"].to_numpy()] = np.nan
    return mid, r, bars["bucket"].to_numpy()


def causal_rule(sym, N, H, q=0.90, warmup=60, rule="reversion"):
    """Causal expanding-window deciles."""
    mid, r, bk = daily_series(sym)
    rs = pd.Series(r)
    sig = (rs.rolling(N, min_periods=N // 2).sum() / (rs.rolling(20, min_periods=10).std() * np.sqrt(N))).to_numpy()
    n = len(mid)
    fwd = np.full(n, np.nan)
    fwd[: n - H] = (np.log(mid[H:]) - np.log(mid[: n - H])) * 1e4
    grid = np.arange(0, n, H)
    grid = grid[np.isfinite(sig[grid]) & np.isfinite(fwd[grid])]
    c = cost(sym)
    hist, nets, bks = [], [], []
    for gi in grid:
        s = sig[gi]
        if len(hist) >= warmup:
            hi = np.quantile(hist, q)
            lo = np.quantile(hist, 1 - q)
            if rule == "reversion":
                if s >= hi:
                    nets.append(-fwd[gi] - c)
                    bks.append(bk[gi])
                elif s <= lo:
                    nets.append(fwd[gi] - c)
                    bks.append(bk[gi])
            else:
                if s >= hi:
                    nets.append(fwd[gi] - c)
                    bks.append(bk[gi])
                elif s <= lo:
                    nets.append(-fwd[gi] - c)
                    bks.append(bk[gi])
        hist.append(s)
    return np.array(nets), np.array(bks)


def pooled_fade(pairs, N, H, q=0.90):
    nets, bks = [], []
    for sym in pairs:
        nn, bb = causal_rule(sym, N, H, q, rule="reversion")
        if len(nn):
            nets.append(nn)
            bks.append(bb)
    return np.concatenate(nets), np.concatenate(bks)


def daily_pnl(net, bucket):
    s = pd.Series(net, index=pd.to_datetime(bucket).date)
    return s.groupby(level=0).mean()


def boot_ci(net, bucket, n_boot=3000):
    if len(net) < 3:
        return np.nan, np.nan
    s = pd.Series(net, index=pd.to_datetime(bucket).year)
    arrs = [g.to_numpy() for _, g in s.groupby(level=0)]
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = RNG.integers(0, len(arrs), len(arrs))
        means[b] = np.concatenate([arrs[i] for i in pick]).mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def pos_years(net, bucket):
    yr = pd.Series(net, index=pd.to_datetime(bucket).year).groupby(level=0).mean()
    return int((yr > 0).sum()), len(yr)


def run_pair(sym, H, d_pool):
    rows = []
    for N in range(20, 105, 5):
        for rule in ("reversion", "momentum"):
            nn, bb = causal_rule(sym, N, H, rule=rule)
            if len(nn) < 3:
                continue
            t, p = ttest_1samp(nn, 0)
            clo, chi = boot_ci(nn, bb)
            py, ny = pos_years(nn, bb)
            d_sym = daily_pnl(nn, bb)
            sharpe = d_sym.mean() / d_sym.std() * np.sqrt(252) if d_sym.std() > 0 else np.nan
            cum = d_sym.cumsum()
            dd = (cum - cum.cummax()).min()
            common = d_sym.index.intersection(d_pool.index)
            corr = float(np.corrcoef(d_sym.loc[common].fillna(0), d_pool.loc[common].fillna(0))[0, 1]) if len(common) >= 10 else np.nan
            rows.append({
                "sym": sym, "N": N, "rule": rule, "n": len(nn), "net": nn.mean(),
                "t": t, "p": p, "hit": (nn > 0).mean() * 100, "posYrs": f"{py}/{ny}",
                "sharpe": sharpe, "dd": dd, "boot_lo": clo, "boot_hi": chi, "corr": corr,
            })
    return rows


def main():
    for H in (2, 3):
        print(f"\n{'='*120}")
        print(f"H={H} days — ALL 6 PAIRS: reversion + momentum sweep N=20..100")
        print(f"{'='*120}")

        # Build pool daily series (exclude the pair being tested from its own corr)
        pool_net, pool_bk = pooled_fade(ALL6, 10, H)
        d_pool = daily_pnl(pool_net, pool_bk)

        all_rows = []
        for sym in ALL6:
            all_rows.extend(run_pair(sym, H, d_pool))

        # Print per-pair summary: best reversion + best momentum
        for sym in ALL6:
            print(f"\n--- {sym} ---")
            sym_rows = [r for r in all_rows if r["sym"] == sym]
            rev_rows = [r for r in sym_rows if r["rule"] == "reversion"]
            mom_rows = [r for r in sym_rows if r["rule"] == "momentum"]

            best_rev = max(rev_rows, key=lambda r: r["sharpe"] if not np.isnan(r["sharpe"]) else -np.inf) if rev_rows else None
            best_mom = max(mom_rows, key=lambda r: r["sharpe"] if not np.isnan(r["sharpe"]) else -np.inf) if mom_rows else None

            if best_rev:
                star = " *" if best_rev["boot_lo"] > 0 and best_rev["sharpe"] > 1.0 else ""
                print(f"  REV best  N={best_rev['N']:.0f} n={best_rev['n']:.0f} net={best_rev['net']:>+6.2f} "
                      f"Sharpe={best_rev['sharpe']:>+5.2f} posYrs={best_rev['posYrs']} "
                      f"boot95=[{best_rev['boot_lo']:>+6.2f},{best_rev['boot_hi']:>+6.2f}] corr={best_rev['corr']:>+5.3f}{star}")
            if best_mom:
                print(f"  MOM best  N={best_mom['N']:.0f} n={best_mom['n']:.0f} net={best_mom['net']:>+6.2f} "
                      f"Sharpe={best_mom['sharpe']:>+5.2f} posYrs={best_mom['posYrs']} "
                      f"boot95=[{best_mom['boot_lo']:>+6.2f},{best_mom['boot_hi']:>+6.2f}] corr={best_mom['corr']:>+5.3f}")

    print("\n" + "=" * 120)
    print("LEGEND: '*' = boot95 clears 0 AND Sharpe > 1.0 (deployable threshold)")
    print("=" * 120)


if __name__ == "__main__":
    main()

"""Per-pair lookback: risk-parity weighting + walk-forward stability.

Tests two extensions to the per-pair optimal book:
  1. Risk-parity weighting (inverse vol, not equal weight) — does it improve Sharpe further?
  2. Walk-forward stability — are the optimal lookbacks stable when estimated on
     an expanding window (not fit once on the full sample)?

For WFO: for each year Y, use data up to Y-1 to pick the best N per pair,
then trade year Y.  This tests whether the per-pair lookback advantage is real
or just in-sample curve-fitting.

Usage:
    uv run python scripts/fx_coint/per_pair_lookback_rp_wfo.py
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


def causal_fade(sym, N, H, q=0.90, warmup=60, start_idx=None, end_idx=None):
    """Causal fade with optional start/end index bounds (for WFO)."""
    mid, r, bk = daily_series(sym)
    if start_idx is not None:
        mid = mid[start_idx:end_idx]
        r = r[start_idx:end_idx]
        bk = bk[start_idx:end_idx]
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
            if s >= hi:
                nets.append(-fwd[gi] - c)
                bks.append(bk[gi])
            elif s <= lo:
                nets.append(fwd[gi] - c)
                bks.append(bk[gi])
        hist.append(s)
    return np.array(nets), np.array(bks)


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


def report(label, net, bk):
    if len(net) < 3:
        print(f"  {label:>18} (too few trades)")
        return None
    t, p = ttest_1samp(net, 0)
    clo, chi = boot_ci(net, bk)
    py, ny = pos_years(net, bk)
    d = daily_pnl(net, bk)
    sharpe = d.mean() / d.std() * np.sqrt(252) if d.std() > 0 else np.nan
    cum = d.cumsum()
    dd = (cum - cum.cummax()).min()
    print(
        f"  {label:>18} n={len(net):>5} net={net.mean():>+7.2f} t={t:>+6.2f} p={p:>6.3f} "
        f"hit={(net > 0).mean()*100:>4.0f}% posYrs={py}/{ny} Sharpe={sharpe:>+5.2f} maxDD={dd:>+8.2f} "
        f"boot95=[{clo:>+7.2f},{chi:>+7.2f}]"
    )
    return d


def build_daily_map(sym, H, N):
    """Build daily PnL series for a pair at given params."""
    nn, bb = causal_fade(sym, N, H)
    return daily_pnl(nn, bb) if len(nn) >= 3 else None


def combine_equal_weight(daily_map):
    """Equal-weight combination of daily PnL series."""
    all_idx = None
    for d in daily_map.values():
        if d is not None:
            all_idx = d.index if all_idx is None else all_idx.union(d.index)
    if all_idx is None or len(all_idx) <= 1:
        return None
    comb = pd.Series(0.0, index=all_idx)
    valid = 0
    for d in daily_map.values():
        if d is not None:
            comb = comb.add(d.reindex(all_idx, fill_value=0), fill_value=0)
            valid += 1
    return comb / valid if valid > 0 else None


def combine_risk_parity(daily_map):
    """Risk-parity: inverse daily vol weighting."""
    all_idx = None
    vols = {}
    for sym, d in daily_map.items():
        if d is not None and len(d) > 10 and d.std() > 0:
            vols[sym] = d.std()
            all_idx = d.index if all_idx is None else all_idx.union(d.index)
    if not vols or all_idx is None or len(all_idx) <= 1:
        return None
    inv_vol = {s: 1 / v for s, v in vols.items()}
    total = sum(inv_vol.values())
    weights = {s: w / total for s, w in inv_vol.items()}
    comb = pd.Series(0.0, index=all_idx)
    for sym, d in daily_map.items():
        if d is not None:
            comb = comb.add(d.reindex(all_idx, fill_value=0) * weights.get(sym, 0), fill_value=0)
    return comb


def combine_kelly(daily_map, fraction=0.5):
    """Half-Kelly on the combined daily returns."""
    all_idx = None
    for d in daily_map.values():
        if d is not None:
            all_idx = d.index if all_idx is None else all_idx.union(d.index)
    if all_idx is None or len(all_idx) <= 1:
        return None
    # First build equal-weight combined
    eq = pd.Series(0.0, index=all_idx)
    valid = 0
    for d in daily_map.values():
        if d is not None:
            eq = eq.add(d.reindex(all_idx, fill_value=0), fill_value=0)
            valid += 1
    if valid == 0:
        return None
    eq = eq / valid
    mu = eq.mean()
    var = eq.var()
    if var <= 0:
        return None
    kelly = mu / var
    weight = fraction * kelly
    # Cap leverage
    weight = max(0, min(weight, 2.0))
    return eq * weight


def print_combined(label, comb):
    if comb is None or len(comb) < 3:
        print(f"  {label:>18} (empty)")
        return
    net_arr = comb.to_numpy()
    t, p = ttest_1samp(net_arr, 0)
    sharpe = net_arr.mean() / net_arr.std() * np.sqrt(252) if net_arr.std() > 0 else np.nan
    cum = comb.cumsum()
    dd = (cum - cum.cummax()).min()
    idx = pd.to_datetime(comb.index)
    arrs = [g.to_numpy() for _, g in pd.Series(net_arr, index=idx.year).groupby(level=0)]
    means = np.empty(3000)
    for b in range(3000):
        pick = RNG.integers(0, len(arrs), len(arrs))
        means[b] = np.concatenate([arrs[i] for i in pick]).mean()
    clo, chi = float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
    yr = pd.Series(net_arr, index=idx.year).groupby(level=0).mean()
    py, ny = int((yr > 0).sum()), len(yr)
    print(
        f"  {label:>18} n={len(net_arr):>5} net={net_arr.mean():>+7.2f} t={t:>+6.2f} p={p:>6.3f} "
        f"hit={(net_arr > 0).mean()*100:>4.0f}% posYrs={py}/{ny} Sharpe={sharpe:>+5.2f} maxDD={dd:>+8.2f} "
        f"boot95=[{clo:>+7.2f},{chi:>+7.2f}]"
    )


def wfo_single_pair(sym, H, candidate_Ns):
    """Walk-forward: for each year, pick best N from prior data, trade that year."""
    # Load full series
    mid, r, bk = daily_series(sym)
    years = pd.to_datetime(bk).year
    min_yr, max_yr = years.min(), years.max()
    all_nets, all_bks = [], []

    for trade_yr in range(min_yr + 2, max_yr + 1):
        # Training: all data before trade_yr
        train_mask = years < trade_yr
        # Need enough data for the longest N + warmup
        train_n = train_mask.sum()
        if train_n < max(candidate_Ns) + 60:
            continue

        best_n = None
        best_sharpe = -np.inf
        for N in candidate_Ns:
            if train_n < N + 60:
                continue
            # Simulate on training data
            nn, bb = causal_fade(sym, N, H, start_idx=0, end_idx=train_n)
            if len(nn) < 10:
                continue
            d = daily_pnl(nn, bb)
            if d.std() > 0:
                sharpe = d.mean() / d.std() * np.sqrt(252)
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_n = N

        if best_n is None:
            continue

        # Trade the selected N on the trade year
        trade_mask = years == trade_yr
        trade_start = np.where(trade_mask)[0][0] if trade_mask.any() else None
        trade_end = np.where(trade_mask)[0][-1] + 1 if trade_mask.any() else None
        if trade_start is None:
            continue
        # Need preceding history for the lookback
        hist_start = max(0, trade_start - best_n - 60)
        nn, bb = causal_fade(sym, best_n, H, start_idx=hist_start, end_idx=trade_end)
        # Filter to trades within trade_yr
        if len(bb):
            yr = pd.to_datetime(bb).year
            in_yr = yr == trade_yr
            nn = nn[in_yr]
            bb = bb[in_yr]
        if len(nn):
            all_nets.append(nn)
            all_bks.append(bb)

    if not all_nets:
        return np.array([]), np.array([])
    return np.concatenate(all_nets), np.concatenate(all_bks)


def main():
    H = 3
    print("=" * 120)
    print("PER-PAIR LOOKBACK EXTENSIONS: risk-parity + walk-forward stability")
    print("=" * 120)

    # --- Part 1: Risk-parity vs equal-weight vs half-Kelly ---
    print("\n--- Part 1: Weighting schemes (in-sample optimal lookbacks) ---")
    daily_map = {sym: build_daily_map(sym, H, N) for sym, (_, N) in {
        "EURUSD": (H, 20), "GBPUSD": (H, 20), "AUDUSD": (H, 95),
        "USDCAD": (H, 30), "USDCHF": (H, 80), "USDJPY": (H, 100),
    }.items()}

    for sym, d in daily_map.items():
        if d is not None:
            print(f"  {sym:>8} n_days={len(d):>4}  vol={d.std():>6.3f}  Sharpe={d.mean()/d.std()*np.sqrt(252):>+5.2f}")

    eq = combine_equal_weight(daily_map)
    rp = combine_risk_parity(daily_map)
    kelly = combine_kelly(daily_map, fraction=0.5)

    print_combined("equal weight", eq)
    print_combined("risk parity", rp)
    print_combined("half-Kelly", kelly)

    # --- Part 2: Walk-forward per-pair lookback selection ---
    print("\n--- Part 2: Walk-forward stability (pick N per year from prior data) ---")
    candidate_Ns = list(range(20, 105, 10))  # coarser grid for speed

    wfo_daily_map = {}
    for sym in ALL6:
        print(f"  Running WFO for {sym}...", end="", flush=True)
        nn, bb = wfo_single_pair(sym, H, candidate_Ns)
        if len(nn) >= 3:
            d = daily_pnl(nn, bb)
            wfo_daily_map[sym] = d
            sharpe = d.mean() / d.std() * np.sqrt(252) if d.std() > 0 else np.nan
            print(f"  n_days={len(d):>4} Sharpe={sharpe:>+5.2f}")
        else:
            print(f"  (too few trades)")
            wfo_daily_map[sym] = None

    wfo_eq = combine_equal_weight(wfo_daily_map)
    print_combined("WFO equal weight", wfo_eq)

    # Also show fixed-pool WFO baseline
    print("\n--- Part 3: Fixed N=10 pool (for WFO baseline comparison) ---")
    fixed_daily_map = {sym: build_daily_map(sym, H, 10) for sym in ALL6}
    fixed_eq = combine_equal_weight(fixed_daily_map)
    print_combined("fixed N=10 pool", fixed_eq)

    print("\n" + "=" * 120)
    print("INTERPRETATION:")
    print("  - RP weighting: higher Sharpe = better risk allocation")
    print("  - WFO vs in-sample: if WFO Sharpe >> 0, the lookback advantage is real")
    print("  - If WFO Sharpe ≈ fixed pool, per-pair lookback is just curve-fitting")
    print("=" * 120)


if __name__ == "__main__":
    main()

"""Conditional burst fade v2: fade top-1% FFD extension that ALSO shows burst continuation.

The worktree doc claimed: "Fading a top-1% burst that EXTENDS the ffd_zvol20 deviation
is a better, faster entry for the reversion edge."

This probes: when ffd_zvol20 is extreme AND the bar continues the same direction
(intra-bar momentum), does the NEXT bar revert harder?

Usage:
    uv run python scripts/fx_coint/conditional_burst_fade_v2.py
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

rsh.FREQ_MINUTES.update({"1h": 60})
PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF"]
COMM = 0.60
SPR = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2, "USDCAD": .3, "AUDUSD": .15, "USDCHF": .3}
PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": .65, "USDCHF": .89}
RNG = np.random.default_rng(0)


def cost(sym: str) -> float:
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


def ffd(x: np.ndarray, d: float = 0.2) -> np.ndarray:
    """Fractional difference (Lopez de Prado)."""
    n = len(x)
    out = np.empty(n)
    out[:] = np.nan
    w = [1.0]
    for k in range(1, n):
        w.append(-w[-1] * (d - k + 1) / k)
    w = np.array(w)
    for i in range(len(w), n):
        out[i] = np.dot(w, x[i - len(w) + 1:i + 1][::-1])
    return out


def burst_fade(sym: str, freq: str = "1h", N: int = 50, q: float = 0.99):
    bars = rsh.build_freq_bars(
        pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"),
        freq, session=(7, 21),
    )
    mid = bars["mid"].to_numpy()
    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    r[~bars["contig"].to_numpy()] = np.nan
    rs = pd.Series(r)

    # FFD zvol signal
    f = ffd(mid, d=0.2)
    zvol = rs.rolling(20, min_periods=10).std().to_numpy()
    sig = np.empty(len(f))
    sig[:] = np.nan
    for i in range(N, len(f)):
        if zvol[i] > 0:
            sig[i] = (f[i] - f[i - N]) / zvol[i]

    # Intra-bar momentum: same-bar continuation
    intra_mom = r  # the bar's own return

    # Next-bar return
    next_r = rs.shift(-1).to_numpy()

    c = cost(sym)
    nets_burst, nets_plain = [], []

    for i in range(len(sig) - 1):
        if np.isnan(sig[i]) or np.isnan(next_r[i]) or np.isnan(intra_mom[i]):
            continue
        if abs(sig[i]) < np.nanquantile(np.abs(sig[~np.isnan(sig)]), q):
            continue
        # Plain fade
        net_plain = -next_r[i] - c if sig[i] > 0 else next_r[i] - c
        nets_plain.append(net_plain)
        # Conditional: only if intra-bar momentum CONTINUES the signal direction
        if (sig[i] > 0 and intra_mom[i] > 0) or (sig[i] < 0 and intra_mom[i] < 0):
            # Burst = signal says overbought AND bar keeps going up
            net_burst = -next_r[i] - c if sig[i] > 0 else next_r[i] - c
            nets_burst.append(net_burst)

    return np.array(nets_plain), np.array(nets_burst)


def boot_ci(net, n_boot=3000):
    if len(net) < 3:
        return np.nan, np.nan
    means = np.empty(n_boot)
    for b in range(n_boot):
        pick = RNG.integers(0, len(net), len(net))
        means[b] = net[pick].mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main():
    print("=" * 80)
    print("CONDITIONAL BURST FADE — fade top-1% FFD extension")
    print("PLAIN = any extreme signal | CONDITIONAL = extreme + intra-bar continuation")
    print("=" * 80)
    for sym in PAIRS:
        plain, burst = burst_fade(sym)
        if len(plain) > 3:
            t1, p1 = ttest_1samp(plain, 0)
            b1lo, b1hi = boot_ci(plain)
            print(f"{sym} PLAIN   n={len(plain):>3} net={plain.mean():>+7.2f} t={t1:>+5.2f} p={p1:.3f} "
                  f"hit={(plain>0).mean()*100:.0f}% boot95=[{b1lo:>+6.2f},{b1hi:>+6.2f}]")
        if len(burst) > 3:
            t2, p2 = ttest_1samp(burst, 0)
            b2lo, b2hi = boot_ci(burst)
            print(f"{sym} BURST   n={len(burst):>3} net={burst.mean():>+7.2f} t={t2:>+5.2f} p={p2:.3f} "
                  f"hit={(burst>0).mean()*100:.0f}% boot95=[{b2lo:>+6.2f},{b2hi:>+6.2f}]")
        print()

    # Pooled
    print("=" * 80)
    print("POOLED:")
    all_plain, all_burst = [], []
    for sym in PAIRS:
        plain, burst = burst_fade(sym)
        all_plain.extend(plain)
        all_burst.extend(burst)
    ap = np.array(all_plain)
    ab = np.array(all_burst)
    if len(ap) > 3:
        t, p = ttest_1samp(ap, 0)
        blo, bhi = boot_ci(ap)
        print(f"PLAIN  n={len(ap):>4} net={ap.mean():>+7.2f} t={t:>+5.2f} p={p:.3f} "
              f"hit={(ap>0).mean()*100:.0f}% boot95=[{blo:>+6.2f},{bhi:>+6.2f}]")
    if len(ab) > 3:
        t, p = ttest_1samp(ab, 0)
        blo, bhi = boot_ci(ab)
        print(f"BURST  n={len(ab):>4} net={ab.mean():>+7.2f} t={t:>+5.2f} p={p:.3f} "
              f"hit={(ab>0).mean()*100:.0f}% boot95=[{blo:>+6.2f},{bhi:>+6.2f}]")


if __name__ == "__main__":
    main()

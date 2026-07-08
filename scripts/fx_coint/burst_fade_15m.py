"""Burst fade on 15m bars: fade top-5% FFD extension with intra-bar continuation.

Less restrictive than hourly — more signals, testable.

Usage:
    uv run python scripts/fx_coint/burst_fade_15m.py
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

rsh.FREQ_MINUTES.update({"15m": 15})
PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF"]
COMM = 0.60
SPR = {"EURUSD": .1, "USDJPY": .1, "GBPUSD": .2, "USDCAD": .3, "AUDUSD": .15, "USDCHF": .3}
PX = {"EURUSD": 1.08, "USDJPY": 150., "GBPUSD": 1.27, "USDCAD": 1.36, "AUDUSD": .65, "USDCHF": .89}
RNG = np.random.default_rng(0)


def cost(sym: str) -> float:
    pip = 0.01 if sym.endswith("JPY") else 0.0001
    return COMM + (SPR[sym] * pip / PX[sym]) * 1e4


def ffd(x: np.ndarray, d: float = 0.2) -> np.ndarray:
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


def burst_fade(sym: str, freq: str = "15m", N: int = 50, q: float = 0.95):
    bars = rsh.build_freq_bars(
        pl.read_parquet(_REPO_ROOT / f"data/tick_bars/{sym}_1m_flow.parquet"),
        freq, session=(7, 21),
    )
    mid = bars["mid"].to_numpy()
    r = np.empty(len(mid))
    r[0] = np.nan
    r[1:] = (np.log(mid[1:]) - np.log(mid[:-1])) * 1e4
    contig = bars["contig"].to_numpy()
    r[~contig] = np.nan
    rs = pd.Series(r)

    f = ffd(mid, d=0.2)
    zvol = rs.rolling(20, min_periods=10).std().to_numpy()
    sig = np.empty(len(f))
    sig[:] = np.nan
    for i in range(N, len(f)):
        if zvol[i] > 0:
            sig[i] = (f[i] - f[i - N]) / zvol[i]

    # Next-bar return
    next_r = rs.shift(-1).to_numpy()
    c = cost(sym)

    valid = ~np.isnan(sig) & ~np.isnan(next_r) & ~np.isnan(r)
    s_valid = sig[valid]
    if len(s_valid) == 0:
        return np.array([]), np.array([]), np.array([])
    thr = np.quantile(np.abs(s_valid), q)

    nets_plain, nets_burst, nets_anti = [], [], []
    idx = np.where(valid)[0]
    for i in idx:
        if abs(sig[i]) < thr:
            continue
        # Plain fade
        net_plain = -next_r[i] - c if sig[i] > 0 else next_r[i] - c
        nets_plain.append(net_plain)
        # Conditional: same-bar momentum CONTINUES the signal direction
        if (sig[i] > 0 and r[i] > 0) or (sig[i] < 0 and r[i] < 0):
            net_burst = -next_r[i] - c if sig[i] > 0 else next_r[i] - c
            nets_burst.append(net_burst)
        # Anti-conditional: bar REVERTS (opposite direction)
        if (sig[i] > 0 and r[i] < 0) or (sig[i] < 0 and r[i] > 0):
            net_anti = -next_r[i] - c if sig[i] > 0 else next_r[i] - c
            nets_anti.append(net_anti)

    return np.array(nets_plain), np.array(nets_burst), np.array(nets_anti)


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
    print("BURST FADE 15m — fade top-5% FFD extension")
    print("PLAIN=any | BURST=extreme+continuation | ANTI=extreme+reversal")
    print("=" * 80)
    for sym in PAIRS:
        plain, burst, anti = burst_fade(sym)
        for label, arr in [("PLAIN", plain), ("BURST", burst), ("ANTI", anti)]:
            if len(arr) > 3:
                t, p = ttest_1samp(arr, 0)
                blo, bhi = boot_ci(arr)
                print(f"{sym} {label:>6} n={len(arr):>3} net={arr.mean():>+7.2f} t={t:>+5.2f} p={p:.3f} "
                      f"hit={(arr>0).mean()*100:.0f}% boot95=[{blo:>+6.2f},{bhi:>+6.2f}]")
        print()

    print("=" * 80)
    print("POOLED:")
    for label in ["PLAIN", "BURST", "ANTI"]:
        all_nets = []
        for sym in PAIRS:
            plain, burst, anti = burst_fade(sym)
            if label == "PLAIN":
                all_nets.extend(plain)
            elif label == "BURST":
                all_nets.extend(burst)
            else:
                all_nets.extend(anti)
        arr = np.array(all_nets)
        if len(arr) > 3:
            t, p = ttest_1samp(arr, 0)
            blo, bhi = boot_ci(arr)
            print(f"{label:>6} n={len(arr):>4} net={arr.mean():>+7.2f} t={t:>+5.2f} p={p:.3f} "
                  f"hit={(arr>0).mean()*100:.0f}% boot95=[{blo:>+6.2f},{bhi:>+6.2f}]")


if __name__ == "__main__":
    main()

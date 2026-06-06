"""Canonical intraday cross-sectional basket seeds (causal, np-only).

Each program defines score(ctx) -> (n_bars, n_sym). Windows use cumulative sums so a
row at index t depends only on rows <= t (passes the basket causality probe)."""
from __future__ import annotations

# Cross-sectional reversal: fade recent relative winners (short strong, long weak).
REVERSAL = """
def score(ctx):
    r = ctx.r
    n, m = r.shape
    out = np.full((n, m), np.nan)
    c = np.cumsum(np.nan_to_num(r), axis=0)
    w = 5
    for t in range(n):
        lo = t - w + 1
        if lo < 0:
            continue
        s = c[t] - (c[lo - 1] if lo > 0 else 0.0)
        out[t] = -s
    return out
"""

# Relative momentum: ride recent relative winners (long strong, short weak).
MOMENTUM = """
def score(ctx):
    r = ctx.r
    n, m = r.shape
    out = np.full((n, m), np.nan)
    c = np.cumsum(np.nan_to_num(r), axis=0)
    w = 10
    for t in range(n):
        lo = t - w + 1
        if lo < 0:
            continue
        out[t] = c[t] - (c[lo - 1] if lo > 0 else 0.0)
    return out
"""

# Lead-lag: laggards catch up to the basket's prior-bar move (Hasbrouck-style).
# score = (basket mean move at t-1) - (own move at t-1): long under-reactors.
LEAD_LAG = """
def score(ctx):
    r = ctx.r
    n, m = r.shape
    out = np.full((n, m), np.nan)
    prev = np.nan_to_num(r)
    for t in range(1, n):
        lead = prev[t - 1].mean()
        out[t] = lead - prev[t - 1]
    return out
"""

BASKET_SEED_PROGRAMS = {
    "reversal": REVERSAL,
    "momentum": MOMENTUM,
    "lead_lag": LEAD_LAG,
}

BASKET_RESEARCH_IDEAS = [
    "Cross-sectional reversal over a short lookback: rank pairs by recent USD-aligned "
    "return and fade the extremes (long laggards, short leaders).",
    "Relative momentum over a longer lookback: ride the persistent relative winners.",
    "Lead-lag: predict each pair's move from the basket's prior-bar move; go long "
    "under-reactors and short over-reactors.",
    "Dispersion-conditioned reversal: only express the ranking when cross-sectional "
    "dispersion is elevated (more relative-value to harvest).",
]

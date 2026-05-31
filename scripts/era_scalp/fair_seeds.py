"""Fair-price (mispricing) seeds — predict (fair - mid) in pips, level-free, causal.

Streams: efficient-price denoising (Hasbrouck), bid-ask bounce (Roll 1984), micro-price
imbalance (Stoikov 2018), trailing anchor / mean reversion, OFI tilt (Cont-Kukanov-Stoikov;
Sirignano-Cont). Programs use the return series (vel_pips_h1) + microstructure only — never an
absolute price — so the predicted deviation is a stationary pip quantity.
"""

FAIR_SEED_PROGRAMS: dict[str, str] = {
    "ewma_denoise_dev": (
        "def fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; a = 0.05\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    return ew - p\n"
    ),
    "bounce_reversal_dev": (
        "def fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1')\n"
        "    return -1.0 * np.where(np.isfinite(r), r, 0.0)\n"
    ),
    "microprice_imbalance_dev": (
        "def fair(ctx):\n"
        "    imb = ctx.col('hl_pos_delta_tick'); sgn = ctx.col('bar_return_sign')\n"
        "    x = np.where(np.isfinite(imb), imb, 0.0)\n"
        "    s = np.where(np.isfinite(sgn), sgn, 0.0)\n"
        "    return x * np.abs(s)\n"
    ),
    "trailing_anchor_dev": (
        "def fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; W = 60\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    ms = np.where(m > 0, m, 1.0)\n"
        "    cp = np.concatenate(([0.0], np.cumsum(p)))\n"
        "    anchor = (cp[k] - cp[lo]) / ms\n"
        "    out = anchor - p\n"
        "    out[m < 20] = np.nan\n"
        "    return out\n"
    ),
    "ofi_adjusted_dev": (
        "def fair(ctx):\n"
        "    sgn = ctx.col('bar_return_sign'); vol = ctx.col('tick_volume')\n"
        "    n = sgn.shape[0]; a = 0.1\n"
        "    flow = np.where(np.isfinite(sgn) & np.isfinite(vol), sgn * np.sqrt(np.abs(vol)), 0.0)\n"
        "    ew = np.empty(n); acc = 0.0\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * flow[i]; ew[i] = acc\n"
        "    return ew\n"
    ),
}

BASELINE_SEED_NAMES = ("ewma_denoise_dev", "bounce_reversal_dev",
                       "microprice_imbalance_dev", "trailing_anchor_dev")

RESEARCH_IDEAS: list[str] = [
    "Efficient price denoising (Hasbrouck): the observed mid = efficient price (martingale) + "
    "transient noise; estimate fair by low-pass filtering the relative return path (EWMA) and "
    "predict dev = smoothed - path.",
    "Bid-ask bounce (Roll 1984): a move smaller than the spread is mostly transient bounce; the "
    "fair price lags the last print, so dev reverses the recent return.",
    "Micro-price (Stoikov 2018): fair sits toward the heavier side of flow; tilt the deviation by "
    "tick-position / order imbalance (hl_pos_delta_tick, bar_return_sign, tick_volume).",
    "Trailing anchor / mean reversion: fair as a causal trailing mean of the price path; dev = "
    "anchor - path.",
    "Order flow (Cont-Kukanov-Stoikov; Sirignano-Cont): persistent signed flow means fair has "
    "moved (mid lags); transient flow means overshoot (mid leads) - separate the two.",
    "Combine: blend an EWMA-denoised fair with a micro-price imbalance tilt and a bounce "
    "correction; the best estimator mixes denoising, imbalance, and reversal.",
]

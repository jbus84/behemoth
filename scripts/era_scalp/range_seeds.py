"""Range-harvest deploy seeds (causal, numpy-only). deploy(ctx)->non-directional score.

Four literature streams fused by PUCT recombination:
realized-range/vol (Parkinson; Yang-Zhang; HAR-RV Corsi 2009),
mean-reversion regime (variance ratio Lo-MacKinlay 1988; OU half-life),
flow-toxicity veto (VPIN Easley-Lopez de Prado-O'Hara; OFI Cont-Kukanov-Stoikov),
Hawkes burst veto (Bacry-Mastromatteo-Muzy), spread-harvest (Avellaneda-Stoikov).
"""

DEPLOY_SEED_PROGRAMS: dict[str, str] = {
    "range_vol_deploy": (
        "def deploy(ctx):\n"
        "    rng = ctx.col('bar_range_pips'); n = rng.shape[0]; W = 120\n"
        "    x = np.where(np.isfinite(rng), rng, 0.0)\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    ms = np.where(m > 0, m, 1.0)\n"
        "    c = np.concatenate(([0.0], np.cumsum(x)))\n"
        "    avg = (c[k] - c[lo]) / ms\n"
        "    out = x / (avg + 1e-9)\n"
        "    out[m < 20] = np.nan\n"
        "    return out\n"
    ),
    "meanrev_regime_deploy": (
        "def deploy(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; W = 120\n"
        "    x = np.where(np.isfinite(r), r, 0.0); xp = np.concatenate(([0.0], x[:-1]))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    ms = np.where(m > 0, m, 1.0)\n"
        "    cxx = np.concatenate(([0.0], np.cumsum(x * x)))\n"
        "    cxy = np.concatenate(([0.0], np.cumsum(x * xp)))\n"
        "    sxx = cxx[k] - cxx[lo]; sxy = cxy[k] - cxy[lo]\n"
        "    rho = sxy / (sxx + 1e-9)\n"
        "    out = np.maximum(0.0, -rho)\n"
        "    out[m < 20] = np.nan\n"
        "    return out\n"
    ),
    "toxicity_gate_deploy": (
        "def deploy(ctx):\n"
        "    rng = ctx.col('bar_range_pips'); sgn = ctx.col('bar_return_sign')\n"
        "    vol = ctx.col('tick_volume'); n = rng.shape[0]; a = 0.1\n"
        "    flow = np.where(np.isfinite(sgn) & np.isfinite(vol), sgn * vol, 0.0)\n"
        "    acc = 0.0; ewma = np.empty(n)\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * flow[i]; ewma[i] = acc\n"
        "    vbar = np.where(np.isfinite(vol), np.abs(vol), 0.0) + 1.0\n"
        "    tox = np.abs(ewma) / (vbar + 1e-9)\n"
        "    base = np.where(np.isfinite(rng), rng, 0.0)\n"
        "    csum = np.cumsum(tox); k = np.arange(n)\n"
        "    exp_mean = csum / (k + 1.0)  # causal expanding mean of tox (O(n))\n"
        "    out = np.where(tox <= exp_mean, base, np.nan)  # deploy when flow benign\n"
        "    return out\n"
    ),
    "burst_veto_deploy": (
        "def deploy(ctx):\n"
        "    inten = ctx.col('tick_burst_score'); rng = ctx.col('bar_range_pips')\n"
        "    n = inten.shape[0]; a = 0.2; acc = 0.0; ew = np.empty(n)\n"
        "    for i in range(n):\n"
        "        xi = inten[i] if np.isfinite(inten[i]) else 0.0\n"
        "        acc = (1 - a) * acc + a * max(xi, 0.0); ew[i] = acc\n"
        "    base = np.where(np.isfinite(rng), rng, 0.0)\n"
        "    return np.where(ew < 1.0, base, np.nan)\n"
    ),
    "spread_harvest_deploy": (
        "def deploy(ctx):\n"
        "    spz = ctx.col('spread_z'); sp = ctx.col('spread_pips')\n"
        "    base = np.where(np.isfinite(sp), np.maximum(sp, 0.0), np.nan)\n"
        "    wide = np.isfinite(spz) & (spz > 0.0)\n"
        "    return np.where(wide, base, np.nan)\n"
    ),
}

# Canonical baselines the rediscovery tracer must regenerate when removed.
BASELINE_SEED_NAMES = ("range_vol_deploy", "meanrev_regime_deploy",
                       "toxicity_gate_deploy", "spread_harvest_deploy")

RESEARCH_IDEAS: list[str] = [
    "Realized range / volatility (Parkinson 1980; Yang-Zhang; HAR-RV Corsi 2009): deploy "
    "when the trailing realized range (bar_range_pips) or multi-scale realized vol is large "
    "vs cost - the band must be wide enough to harvest.",
    "Mean-reversion regime (variance ratio, Lo-MacKinlay 1988; Hurst; OU half-life): deploy "
    "when a causal trailing variance-ratio < 1 or lag-1 return autocorrelation is negative - "
    "price reverts from extremes rather than trending.",
    "Flow-toxicity veto (VPIN, Easley-Lopez de Prado-O'Hara; OFI, Cont-Kukanov-Stoikov): do "
    "NOT deploy when signed order-flow imbalance is high - one-sided flow breaks the range.",
    "Hawkes self-exciting bursts (Bacry-Mastromatteo-Muzy): veto deploy when EWMA tick "
    "intensity spikes - clustering precedes breakouts.",
    "Spread harvest (Avellaneda-Stoikov; Stoikov micro-price): deploy when the spread is wide "
    "AND flow is balanced - the wide-spread-benign-flow sweet spot, since maker entry earns "
    "the spread.",
    "Combine: gate any wide-range/vol deploy signal by BOTH a mean-reversion-regime test and "
    "a flow-toxicity (and burst) veto - the best detector is the intersection, not any single "
    "stream.",
]

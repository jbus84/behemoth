"""Modern microstructure scalping seeds (causal, numpy-only). signal(ctx)->array.

Families: order-flow imbalance (Cont-Kukanov-Stoikov; Kolm-Turiel-Westray),
OU mean-reversion (Avellaneda-Lee s-score; Leung-Li; Bertram), Hawkes
self-exciting bursts (Bacry-Mastromatteo-Muzy), with a tradeable-spread regime gate.
"""

SEED_PROGRAMS: dict[str, str] = {
    # --- Order-flow imbalance / price impact ---
    "ofi_flow": (
        "def signal(ctx):\n"
        "    sgn = ctx.col('bar_return_sign'); vol = ctx.col('tick_volume')\n"
        "    flow = np.where(np.isfinite(sgn) & np.isfinite(vol), sgn * vol, 0.0)\n"
        "    n = flow.shape[0]; a = 0.1; out = np.empty(n); acc = 0.0\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * flow[i]\n"
        "        out[i] = acc\n"
        "    return out  # OFI continuation: positive flow -> expect up\n"
    ),
    "ofi_multihorizon": (
        "def signal(ctx):\n"
        "    zs = [ctx.col('vel_z_h1'), ctx.col('vel_z_h2'), ctx.col('vel_z_h5'),\n"
        "          ctx.col('vel_z_h10')]\n"
        "    w = [0.4, 0.3, 0.2, 0.1]; out = np.zeros(ctx.n_bars)\n"
        "    for wi, z in zip(w, zs):\n"
        "        out = out + wi * np.where(np.isfinite(z), z, 0.0)\n"
        "    return out  # multi-horizon momentum (Kolm-Turiel-Westray)\n"
    ),
    # --- OU mean-reversion (Avellaneda-Lee s-score over a trailing equilibrium) ---
    "ou_sscore": (
        "def signal(ctx):\n"
        "    ret = ctx.col('vel_pips_h1'); n = ret.shape[0]; W = 120\n"
        "    x = np.cumsum(np.where(np.isfinite(ret), ret, 0.0))  # detrended price proxy\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    ms = np.where(m > 0, m, 1.0)\n"
        "    cx = np.concatenate(([0.0], np.cumsum(x)))\n"
        "    cxx = np.concatenate(([0.0], np.cumsum(x * x)))\n"
        "    sx = cx[k] - cx[lo]; sxx = cxx[k] - cxx[lo]\n"
        "    mu = sx / ms; var = sxx / ms - mu * mu\n"
        "    sd = np.sqrt(np.clip(var, 1e-12, None))\n"
        "    s = (x - mu) / sd\n"
        "    out = -s  # fade deviation from trailing OU equilibrium\n"
        "    out[m < 20] = np.nan\n"
        "    return out\n"
    ),
    "roll_bounce_fade": (
        "def signal(ctx):\n"
        "    v = ctx.col('vel_pips_h1'); sp = ctx.col('spread_pips')\n"
        "    small = np.isfinite(v) & np.isfinite(sp) & (np.abs(v) < 1.0 * sp)\n"
        "    return np.where(small, -np.sign(v), np.nan)  # fade sub-spread bounce (Roll)\n"
    ),
    # --- Hawkes self-exciting burst continuation ---
    "hawkes_cont": (
        "def signal(ctx):\n"
        "    inten = ctx.col('tick_burst_score'); move = ctx.col('vel_pips_h1')\n"
        "    n = inten.shape[0]; a = 0.2; out = np.full(n, np.nan); acc = 0.0\n"
        "    for i in range(n):\n"
        "        xi = inten[i] if np.isfinite(inten[i]) else 0.0\n"
        "        acc = (1 - a) * acc + a * max(xi, 0.0)\n"
        "        if acc > 0.5 and np.isfinite(move[i]):\n"
        "            out[i] = np.sign(move[i]) * acc  # continuation when bursts cluster\n"
        "    return out\n"
    ),
    # --- regime gate ---
    "spread_gated_flow": (
        "def signal(ctx):\n"
        "    spz = ctx.col('spread_z'); base = ctx.col('vel_z_h1')\n"
        "    base = np.where(np.isfinite(base), base, np.nan)\n"
        "    return np.where(np.isfinite(spz) & (spz <= 0.0), base, np.nan)\n"
    ),
}

# Canonical baselines the rediscovery tracer must regenerate when removed.
BASELINE_SEED_NAMES = ("ofi_flow", "ou_sscore", "hawkes_cont", "ofi_multihorizon")

RESEARCH_IDEAS: list[str] = [
    "Order flow imbalance (Cont-Kukanov-Stoikov): signed flow (bar_return_sign x "
    "tick_volume, or hl_pos_delta_tick) predicts the next-bar move in the SAME "
    "direction (price impact); smooth it causally and trade side=sign(flow).",
    "Multi-horizon OFI alpha (Kolm-Turiel-Westray): stack backward returns/imbalance "
    "at several horizons (vel_z_h1/h2/h5/h10) with weights and combine for direction.",
    "Ornstein-Uhlenbeck mean-reversion (Avellaneda-Lee s-score): model the short-window "
    "price deviation as OU, estimate the reversion speed / half-life on a TRAILING "
    "window, emit the s-score and fade it when it breaches a band (Leung-Li bands).",
    "Bid-ask bounce reversion (Roll): a move smaller than the spread is mostly bounce; "
    "fade it.",
    "Hawkes self-exciting bursts (Bacry-Mastromatteo-Muzy): tick arrivals cluster; use a "
    "causal EWMA of tick intensity (tick_rate_z/tick_burst) and trade continuation only "
    "when intensity is elevated.",
    "Regime gate: only trade when spread_z is low (tradeable) and/or a vol regime is "
    "favorable, to keep net-of-cost edge positive.",
]

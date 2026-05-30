"""Baseline dispersion programs (seeds) + research-idea summaries."""

SEED_PROGRAMS: dict[str, str] = {
    # all6 z (the diluted baseline)
    "all6_z": (
        "def residual(ctx):\n"
        "    r = ctx.r\n"
        "    mu = r.mean(axis=1, keepdims=True)\n"
        "    sd = r.std(axis=1, keepdims=True) + 1e-9\n"
        "    z = (r - mu) / sd\n"
        "    return z[:, ctx.target_idx]\n"
    ),
    # leave-one-out basket z
    "loo_z": (
        "def residual(ctx):\n"
        "    t = ctx.target_col(); p = ctx.peers()\n"
        "    return (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)\n"
    ),
    # robust median/MAD over all 6
    "robust_z": (
        "def residual(ctx):\n"
        "    r = ctx.r\n"
        "    med = np.median(r, axis=1)\n"
        "    mad = np.median(np.abs(r - med[:, None]), axis=1) + 1e-9\n"
        "    return (ctx.target_col() - med) / (1.4826 * mad)\n"
    ),
    # fixed-cluster graph-laplacian residual (EUR/GBP/AUD vs JPY/CHF/CAD by name)
    "graph_laplacian": (
        "def residual(ctx):\n"
        "    cl = {'EURUSD':0,'GBPUSD':0,'AUDUSD':0,'USDJPY':1,'USDCHF':1,'USDCAD':1}\n"
        "    g = np.array([cl.get(n, 0) for n in ctx.names])\n"
        "    ti = ctx.target_idx; same = (g == g[ti])\n"
        "    same[ti] = False\n"
        "    if same.sum() == 0:\n"
        "        nb = ctx.peers().mean(axis=1)\n"
        "    else:\n"
        "        nb = ctx.r[:, same].mean(axis=1)\n"
        "    return ctx.target_col() - nb\n"
    ),
    # ordinal dispersion rank (k=2): +/- by extremity of cross-sectional rank
    "dispersion_rank": (
        "def residual(ctx):\n"
        "    r = ctx.r; n, m = r.shape\n"
        "    order = np.argsort(-r, axis=1, kind='stable')\n"
        "    ranks = np.empty_like(order)\n"
        "    rows = np.arange(n)[:, None]\n"
        "    ranks[rows, order] = np.broadcast_to(np.arange(1, m + 1), order.shape)\n"
        "    tr = ranks[:, ctx.target_idx].astype(float)\n"
        "    mid = (m + 1) / 2.0\n"
        "    return mid - tr  # >0 near top rank, <0 near bottom\n"
    ),
    # leave-one-out basket z gated to asia session (UTC hour 0-5)
    "loo_z_asia": (
        "def residual(ctx):\n"
        "    t = ctx.target_col(); p = ctx.peers()\n"
        "    z = (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)\n"
        "    if ctx.hour is not None:\n"
        "        z = np.where(ctx.hour <= 5, z, np.nan)\n"
        "    return z\n"
    ),
    # leave-one-out basket z gated to high-dispersion bars (causal expanding mean)
    "loo_z_highdisp": (
        "def residual(ctx):\n"
        "    t = ctx.target_col(); p = ctx.peers()\n"
        "    z = (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)\n"
        "    d = ctx.dispersion()\n"
        "    csum = np.cumsum(d)\n"
        "    expanding_mean = csum / np.arange(1, len(d) + 1)\n"
        "    return np.where(d >= expanding_mean, z, np.nan)\n"
    ),
    # median target-vs-peer spread (ADR pairwise_median)
    "pairwise_median": (
        "def residual(ctx):\n"
        "    t = ctx.target_col()[:, None]; p = ctx.peers()\n"
        "    return np.median(t - p, axis=1)\n"
    ),
    # correlation-weighted peer-network residual (ADR weighted graph_laplacian).
    # Vectorised: trailing-window Pearson weights via cumsum (O(n)); cx[k]-cx[lo]
    # only reads cumulative sums at indices <= k, so it stays causal.
    "corr_weighted_graph": (
        "def residual(ctx):\n"
        "    r = ctx.r; n = r.shape[0]; ti = ctx.target_idx; W = 250\n"
        "    pidx = ctx.peer_idx\n"
        "    x = r[:, ti]; P = r[:, pidx]\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    ms = np.where(m > 0, m, 1.0)[:, None]\n"
        "    z = np.zeros((1, P.shape[1]))\n"
        "    cx = np.concatenate(([0.0], np.cumsum(x)))\n"
        "    cxx = np.concatenate(([0.0], np.cumsum(x * x)))\n"
        "    cP = np.vstack((z, np.cumsum(P, axis=0)))\n"
        "    cPP = np.vstack((z, np.cumsum(P * P, axis=0)))\n"
        "    cXP = np.vstack((z, np.cumsum(P * x[:, None], axis=0)))\n"
        "    sx = (cx[k] - cx[lo])[:, None]; sxx = (cxx[k] - cxx[lo])[:, None]\n"
        "    sP = cP[k] - cP[lo]; sPP = cPP[k] - cPP[lo]; sXP = cXP[k] - cXP[lo]\n"
        "    Sxx = sxx - sx * sx / ms\n"
        "    Spp = sPP - sP * sP / ms\n"
        "    Sxp = sXP - sx * sP / ms\n"
        "    denom = np.sqrt(np.clip(Sxx * Spp, 0.0, None))\n"
        "    w = np.where(denom > 1e-12, Sxp / denom, 0.0)\n"
        "    sw = np.abs(w).sum(axis=1, keepdims=True)\n"
        "    w = np.where(sw > 1e-9, w / sw, 0.0)\n"
        "    out = x - (w * P).sum(axis=1)\n"
        "    out[(m < 20) | (sw[:, 0] <= 1e-9)] = np.nan\n"
        "    return out\n"
    ),
    # market-factor (USD basket) residual via causal rolling OLS beta
    # (ADR Avellaneda-Lee factor-residual transfer). Vectorised: trailing-window
    # beta = Sxy/Sxx via cumsum (O(n)); only reads cumsum at indices <= k.
    "factor_resid": (
        "def residual(ctx):\n"
        "    r = ctx.r; n = r.shape[0]; ti = ctx.target_idx; W = 250\n"
        "    basket = r.mean(axis=1); y = r[:, ti]\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    ms = np.where(m > 0, m, 1.0)\n"
        "    cx = np.concatenate(([0.0], np.cumsum(basket)))\n"
        "    cy = np.concatenate(([0.0], np.cumsum(y)))\n"
        "    cxx = np.concatenate(([0.0], np.cumsum(basket * basket)))\n"
        "    cxy = np.concatenate(([0.0], np.cumsum(basket * y)))\n"
        "    sx = cx[k] - cx[lo]; sy = cy[k] - cy[lo]\n"
        "    sxx = cxx[k] - cxx[lo]; sxy = cxy[k] - cxy[lo]\n"
        "    Sxx = sxx - sx * sx / ms\n"
        "    Sxy = sxy - sx * sy / ms\n"
        "    beta = np.where(np.abs(Sxx) > 1e-12, Sxy / Sxx, np.nan)\n"
        "    out = y - beta * basket\n"
        "    out[m < 20] = np.nan\n"
        "    return out\n"
    ),
}

# The four canonical baselines the ADR tracer-bullet must be able to rediscover.
BASELINE_SEED_NAMES = ("dispersion_rank", "loo_z", "robust_z", "graph_laplacian")

RESEARCH_IDEAS: list[str] = [
    "Leave-one-out basket residual: standardise the target's USD-aligned return "
    "against the mean and std of the OTHER five majors only, so the target is not "
    "in its own benchmark; fade large residuals.",
    "Robust residual: use median and MAD instead of mean/std so one extreme peer "
    "print cannot distort the basket; fade outliers.",
    "Graph/cluster residual: compare the target only to its most related peers "
    "(e.g. EUR/GBP/AUD vs JPY/CHF/CAD) rather than the equal-weight basket.",
    "Participation/concentration gate: only treat a move as idiosyncratic when it "
    "is concentrated in the target (high participation ratio), not a broad USD move.",
    "Dispersion-regime conditioning: reversion of an extreme is stronger when "
    "cross-sectional dispersion (std of the six returns) is high; weight by it.",
    "Rank-transition: an extreme cross-sectional rank tends to move back toward the "
    "middle over the horizon; size the fade by how extreme the rank is.",
    "Pairwise spread: score the target by the median (or mean) of its return "
    "minus each peer's return, rather than versus a single basket mean.",
    "Factor / PCA residual (Avellaneda-Lee): remove the common USD-basket factor "
    "with a causal expanding/rolling regression beta (or the first principal "
    "component of a trailing window of the six returns) and fade the idiosyncratic "
    "residual; never use future rows.",
    "Covariance-aware residual: scale the basket residual by a causal trailing "
    "Mahalanobis-style covariance of the six returns so correlated moves count less.",
    "Correlation-weighted peer graph: weight peers by their trailing-window "
    "correlation with the target, then fade target-minus-weighted-peers.",
    "Stateful residual: EWMA or short trailing-window smoothing of the basket "
    "residual to separate one-bar noise from a persistent dislocation.",
    "Dispersion change: compare current cross-sectional dispersion to its trailing "
    "average (dispersion expansion vs contraction) and gate or size the fade by it.",
]

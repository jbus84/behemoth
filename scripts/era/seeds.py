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
    # correlation-weighted peer-network residual (ADR weighted graph_laplacian)
    "corr_weighted_graph": (
        "def residual(ctx):\n"
        "    r = ctx.r; n, m = r.shape; ti = ctx.target_idx; W = 250\n"
        "    pidx = ctx.peer_idx\n"
        "    out = np.full(n, np.nan)\n"
        "    for k in range(n):\n"
        "        lo = max(0, k - W)\n"
        "        if k - lo < 20:\n"
        "            continue\n"
        "        win = r[lo:k, :]  # strictly past bars only\n"
        "        tg = win[:, ti]\n"
        "        w = np.zeros(len(pidx))\n"
        "        for j, pj in enumerate(pidx):\n"
        "            c = np.corrcoef(tg, win[:, pj])[0, 1]\n"
        "            w[j] = c if np.isfinite(c) else 0.0\n"
        "        sw = np.abs(w).sum()\n"
        "        if sw <= 1e-9:\n"
        "            continue\n"
        "        w = w / sw\n"
        "        nb = float(np.dot(w, r[k, pidx]))\n"
        "        out[k] = r[k, ti] - nb\n"
        "    return out\n"
    ),
}

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
]

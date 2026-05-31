"""Fade-exploitation seeds: signed fade conviction (fair - mid), gated by mean-reversion regime.

Positive => mid below fair => long toward fair. np.nan => abstain. Level-free (returns +
microstructure). Gates: variance-ratio (Lo-MacKinlay 1988), lag-1 autocorrelation, Kaufman
efficiency ratio, extreme-dislocation; OU half-life (Leung-Li, Bertram) as an idea.
"""

_FAIR = (
    "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; a = 0.05\n"
    "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
    "    ew = np.empty(n); acc = p[0]\n"
    "    for i in range(n):\n"
    "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
    "    dev = ew - p  # fair - mid (pips); >0 => mid below fair => fade long\n"
)

FADE_SEED_PROGRAMS: dict[str, str] = {
    "fair_fade": (
        "def signal(ctx):\n" + _FAIR +
        "    return dev\n"
    ),
    "vr_gated_fade": (
        "def signal(ctx):\n" + _FAIR +
        "    W = 240; qv = 20\n"
        "    d1 = np.diff(p, prepend=p[0])\n"
        "    dq = np.empty(n); dq[:qv] = 0.0; dq[qv:] = p[qv:] - p[:-qv]\n"
        "    def rollvar(x):\n"
        "        c1 = np.concatenate(([0.0], np.cumsum(x)))\n"
        "        c2 = np.concatenate(([0.0], np.cumsum(x * x)))\n"
        "        k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "        ms = np.where(m > 0, m, 1.0)\n"
        "        mu = (c1[k] - c1[lo]) / ms\n"
        "        return (c2[k] - c2[lo]) / ms - mu * mu, m\n"
        "    v1, m = rollvar(d1); vq, _ = rollvar(dq)\n"
        "    vr = vq / (qv * v1 + 1e-12)\n"
        "    out = np.where((m >= 60) & (vr < 1.0), dev, np.nan)\n"
        "    return out\n"
    ),
    "vr_conditional_direction": (
        "def signal(ctx):\n" + _FAIR +
        "    W = 240; qv = 20\n"
        "    d1 = np.diff(p, prepend=p[0])\n"
        "    dq = np.empty(n); dq[:qv] = 0.0; dq[qv:] = p[qv:] - p[:-qv]\n"
        "    def rollvar(x):\n"
        "        c1 = np.concatenate(([0.0], np.cumsum(x)))\n"
        "        c2 = np.concatenate(([0.0], np.cumsum(x * x)))\n"
        "        k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "        ms = np.where(m > 0, m, 1.0)\n"
        "        mu = (c1[k] - c1[lo]) / ms\n"
        "        return (c2[k] - c2[lo]) / ms - mu * mu, m\n"
        "    v1, m = rollvar(d1); vq, _ = rollvar(dq)\n"
        "    vr = vq / (qv * v1 + 1e-12)\n"
        "    out = np.full(n, np.nan); ok = m >= 60\n"
        "    out = np.where(ok & (vr < 0.95), dev, out)   # mean-reverting -> FADE\n"
        "    out = np.where(ok & (vr > 1.05), -dev, out)  # trending -> CONTINUE\n"
        "    return out\n"
    ),
    "autocorr_gated_fade": (
        "def signal(ctx):\n" + _FAIR +
        "    W = 240; x = np.where(np.isfinite(r), r, 0.0); xp = np.concatenate(([0.0], x[:-1]))\n"
        "    cxx = np.concatenate(([0.0], np.cumsum(x * x)))\n"
        "    cxy = np.concatenate(([0.0], np.cumsum(x * xp)))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    rho = (cxy[k] - cxy[lo]) / (cxx[k] - cxx[lo] + 1e-12)\n"
        "    out = np.where((m >= 60) & (rho < 0.0), dev, np.nan)\n"
        "    return out\n"
    ),
    "efficiency_gated_fade": (
        "def signal(ctx):\n" + _FAIR +
        "    W = 120\n"
        "    absr = np.abs(np.where(np.isfinite(r), r, 0.0))\n"
        "    cabs = np.concatenate(([0.0], np.cumsum(absr)))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    net = np.abs(p - p[np.maximum(0, k - W)])\n"
        "    denom = cabs[k] - cabs[lo] + 1e-9\n"
        "    er = net / denom\n"
        "    out = np.where((m >= 60) & (er < 0.3), dev, np.nan)\n"
        "    return out\n"
    ),
    "extreme_fade": (
        "def signal(ctx):\n" + _FAIR +
        "    W = 240; ad = np.abs(np.where(np.isfinite(dev), dev, 0.0))\n"
        "    c = np.concatenate(([0.0], np.cumsum(ad)))\n"
        "    c2 = np.concatenate(([0.0], np.cumsum(ad * ad)))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    ms = np.where(m > 0, m, 1.0)\n"
        "    mu = (c[k] - c[lo]) / ms; var = (c2[k] - c2[lo]) / ms - mu * mu\n"
        "    sd = np.sqrt(np.clip(var, 1e-12, None))\n"
        "    out = np.where((m >= 60) & (ad > mu + 2.0 * sd), dev, np.nan)\n"
        "    return out\n"
    ),
    "conditional_response_fade": (
        "def signal(ctx):\n" + _FAIR +
        "    H = 100; W = 240; MINEP = 20\n"
        "    ad = np.abs(np.where(np.isfinite(dev), dev, 0.0))\n"
        "    c1 = np.concatenate(([0.0], np.cumsum(ad)))\n"
        "    c2 = np.concatenate(([0.0], np.cumsum(ad * ad)))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); mwin = (k - lo).astype(float)\n"
        "    ms = np.where(mwin > 0, mwin, 1.0)\n"
        "    mu = (c1[k] - c1[lo]) / ms; var = (c2[k] - c2[lo]) / ms - mu * mu\n"
        "    sd = np.sqrt(np.clip(var, 1e-12, None))\n"
        "    ext = (mwin >= 60) & (ad > mu + 2.0 * sd)\n"
        "    pf = np.full(n, np.nan); pf[:n - H] = p[H:] - p[:n - H]\n"
        "    fr = np.sign(dev) * pf\n"
        "    valid = ext & np.isfinite(fr)\n"
        "    resolved = np.full(n, np.nan)\n"
        "    j = np.nonzero(valid)[0]; resolved[j + H] = fr[j]\n"
        "    fin = np.isfinite(resolved)\n"
        "    rv = np.where(fin, resolved, 0.0); cnt = np.where(fin, 1.0, 0.0)\n"
        "    nep = np.cumsum(cnt)\n"
        "    R = np.cumsum(rv) / np.maximum(nep, 1.0)\n"
        "    direction = np.where(R >= 0.0, 1.0, -1.0)\n"
        "    out = np.where(nep >= MINEP, dev * direction, np.nan)\n"
        "    return out\n"
    ),
    "conditional_response_signed": (
        "def signal(ctx):\n" + _FAIR +
        "    H = 100; W = 240; MINEP = 20\n"
        "    ad = np.abs(np.where(np.isfinite(dev), dev, 0.0))\n"
        "    c1 = np.concatenate(([0.0], np.cumsum(ad)))\n"
        "    c2 = np.concatenate(([0.0], np.cumsum(ad * ad)))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); mwin = (k - lo).astype(float)\n"
        "    ms = np.where(mwin > 0, mwin, 1.0)\n"
        "    mu = (c1[k] - c1[lo]) / ms; var = (c2[k] - c2[lo]) / ms - mu * mu\n"
        "    sd = np.sqrt(np.clip(var, 1e-12, None))\n"
        "    ext = (mwin >= 60) & (ad > mu + 2.0 * sd)\n"
        "    pf = np.full(n, np.nan); pf[:n - H] = p[H:] - p[:n - H]\n"
        "    fr = np.sign(dev) * pf\n"
        "    def runmean(mask):\n"
        "        rs = np.full(n, np.nan); j = np.nonzero(mask & np.isfinite(fr))[0]\n"
        "        rs[j + H] = fr[j]; fn = np.isfinite(rs)\n"
        "        ct = np.cumsum(np.where(fn, 1.0, 0.0))\n"
        "        return np.cumsum(np.where(fn, rs, 0.0)) / np.maximum(ct, 1.0), ct\n"
        "    Rp, ep = runmean(ext & (dev > 0)); Rn, en = runmean(ext & (dev <= 0))\n"
        "    use_p = dev > 0\n"
        "    R = np.where(use_p, Rp, Rn); nep = np.where(use_p, ep, en)\n"
        "    direction = np.where(R >= 0.0, 1.0, -1.0)\n"
        "    out = np.where(nep >= MINEP, dev * direction, np.nan)\n"
        "    return out\n"
    ),
}

BASELINE_SEED_NAMES = ("fair_fade", "vr_gated_fade", "autocorr_gated_fade", "extreme_fade")

RESEARCH_IDEAS: list[str] = [
    "Variance ratio regime (Lo-MacKinlay 1988): the fade only pays when price mean-reverts; gate on "
    "a causal trailing variance ratio < 1 (q-step variance below q x 1-step variance).",
    "Lag-1 autocorrelation: negative trailing return autocorrelation = reverting; trade then.",
    "Kaufman efficiency ratio: |net move| / sum|moves| over a window; low ER = choppy/reverting "
    "(not trending) = good for fading.",
    "OU half-life (Leung-Li; Bertram): estimate a short reversion half-life on a trailing window; "
    "fade when reversion is fast and size the exit horizon to it.",
    "Extreme dislocation: only fade when |fair - mid| is in the tail of its own trailing "
    "distribution (e.g. > mean + 2 sd) - the edge is tail-concentrated.",
    "Combine: gate the fair-mispricing fade by a mean-reversion regime AND require an extreme "
    "dislocation; this opens a way in for otherwise-trending symbols (CHF/JPY) in their reverting "
    "windows without breaking the mean-reverting ones (EUR/AUD).",
    "Regime-conditional direction: do not assume reversion. Use the SAME causal trailing variance "
    "ratio to pick the side per bar - fade (toward fair) when VR<1 (mean-reverting), but go WITH the "
    "move (continuation) when VR>1 (trending), abstaining in a dead-band near 1. One causal rule, no "
    "per-symbol direction fitting; recovers EUR/AUD fade and GBP continuation from the regime alone.",
    "Entry-conditioned conditional response: do not gate direction by a trailing-average regime "
    "(which misclassifies the mean-reverting majors at the tail dislocations). Instead maintain a "
    "causal online mean of how the symbol's OWN past EXTREME dislocations resolved over the next H "
    "bars (completed episodes only), and fade when reversion has paid, continue when it has not. "
    "Empirical conditional-response/reversion function; learns direction per symbol with no peeking.",
]

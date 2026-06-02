"""Fair-price estimation seeds: literature-backed microstructure models.

Each seed defines `estimate_fair(ctx)` which returns a numpy array of fair price
estimates (same units as mid).  The deviation harness then computes:
    deviation = fair_price - mid
    entry when |deviation| > threshold, direction = sign(deviation)

Positive deviation => mid below fair => buy (fade long).
Negative deviation => mid above fair => sell (fade short).
np.nan => abstain.

Literature basis:
  - Roll (1984): bid-ask bounce creates negative autocorrelation; fair = mid adjusted
    for half-spread direction (reversing the bounce).
  - Hasbrouck (1993): efficient price is the random-walk component; fair = very-slow
    EWMA of mid that filters microstructure noise.
  - Evans-Lyons (2002): portfolio shifts / inventory drive FX; fair = mid + lambda *
    cumulative signed flow (proxied by signed velocity).
  - Barzykin (2025/2026): transient impact decays exponentially; fair = mid - residual
    impact from past bar ranges.
  - Stoikov-Kercheval (2010): OFI fair = mid + alpha * OFI; we proxy OFI with the
    signed deviation of return from its expected range contribution.
  - Krohn et al. (2024): fix windows create temporary distortion; fair = mid adjusted
    for known fix-seasonal effects.
  - Taylor (2017): Parkinson-vol-adaptive EWMA; higher vol -> faster adaptation.
  - Madhavan-Richardson-Roomans (1997) / Stoikov microprice: fair = mid + k * order
    imbalance proxy (signed velocity / bar_range).
"""
from __future__ import annotations

import numpy as np


# ── Shared fair-price baseline ────────────────────────────────────────────────
# Slow EWMA of cumulative mid (equivalent to EWMA of price level).
_FAIR_BASELINE = (
    "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; a = 0.02\n"
    "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
    "    ew = np.empty(n); acc = p[0]\n"
    "    for i in range(n):\n"
    "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
    "    fair = ew  # baseline fair price = slow EWMA of price level\n"
)


# ── Branch taxonomy ──────────────────────────────────────────────────────────
BRANCH_TAXONOMY: dict[str, str] = {
    "baseline": "Slow EWMA of price level; no adjustment for microstructure.",
    "roll_bounce": "Adjust fair for bid-ask bounce (Roll 1984); reverse half-spread direction.",
    "hasbrouck_efficient": "Very-slow random-walk filter (Hasbrouck 1993); extracts efficient price.",
    "evans_lyons_inventory": "Inventory/portfolio-shift model (Evans-Lyons 2002); cumulative flow.",
    "barzykin_propagator": "Transient impact decay (Barzykin 2025/2026); subtract residual impact.",
    "stoikov_ofi": "OFI fair (Stoikov-Kercheval 2010); proxy OFI from return-range deviation.",
    "krohn_fix_adjusted": "Fix-window seasonal adjustment (Krohn et al. 2024); remove fix distortion.",
    "taylor_adaptive": "Parkinson-vol-adaptive EWMA (Taylor 2017); faster when vol is high.",
    "microprice_imbalance": "Microprice with order-imbalance proxy (Madhavan 1997); signed flow / range.",
    "glosten_milgrom": "Adverse-selection adjustment (Glosten-Milgrom 1985); fair = mid - lambda*|velocity|.",
    "cointegration_trend": "Online cointegration fair (Engle-Granger 1987); fair = intercept + beta*time.",
    "jump_robust": "Median-based fair (Bibinger 2024); robust to jump contamination.",
}


# ── Seed-to-branch mapping ───────────────────────────────────────────────────
SEED_BRANCH_TAGS: dict[str, str] = {
    "slow_ewma_fair": "baseline",
    "roll_bounce_fair": "roll_bounce",
    "hasbrouck_efficient_fair": "hasbrouck_efficient",
    "evans_lyons_inventory_fair": "evans_lyons_inventory",
    "barzykin_propagator_fair": "barzykin_propagator",
    "stoikov_ofi_fair": "stoikov_ofi",
    "krohn_fix_adjusted_fair": "krohn_fix_adjusted",
    "taylor_adaptive_fair": "taylor_adaptive",
    "microprice_imbalance_fair": "microprice_imbalance",
    "glosten_milgrom_fair": "glosten_milgrom",
    "cointegration_trend_fair": "cointegration_trend",
    "jump_robust_fair": "jump_robust",
}


# ── Seed programs (estimate_fair returns fair price, NOT signal) ─────────────
FAIR_SEED_PROGRAMS: dict[str, str] = {
    "slow_ewma_fair": (
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    return ew\n"
    ),
    "roll_bounce_fair": (
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); sp = ctx.col('spread_pips')\n"
        "    n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    # Roll (1984): reverse the bid-ask bounce direction\n"
        "    # If last return was positive, mid was likely driven by ask; fair is lower.\n"
        "    # Proxy with sign(velocity) * half-spread.\n"
        "    bounce = np.sign(r) * sp * 0.5\n"
        "    return ew - bounce\n"
    ),
    "hasbrouck_efficient_fair": (
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    # Hasbrouck (1993): efficient price = very-slow random-walk component.\n"
        "    # Use alpha=0.005 to filter out microstructure noise.\n"
        "    a = 0.005\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    return ew\n"
    ),
    "evans_lyons_inventory_fair": (
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    # Evans-Lyons (2002): cumulative signed flow predicts price.\n"
        "    # Inventory proxy = cumulative signed velocity.\n"
        "    # Fair = mid + lambda * inventory  (positive inventory pushes fair above mid).\n"
        "    signed_r = np.where(np.isfinite(r), r, 0.0)\n"
        "    inventory = np.cumsum(signed_r)  # cumulative net flow in pips\n"
        "    lam = 0.001  # small coefficient: inventory of 1000 pips shifts fair by 1 pip\n"
        "    return ew + lam * inventory\n"
    ),
    "barzykin_propagator_fair": (
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "    n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    # Barzykin (2025/2026): transient impact decays exponentially.\n"
        "    rho = 0.1; lam = 0.5\n"
        "    impact = np.zeros(n)\n"
        "    for i in range(1, n):\n"
        "        impact[i] = (1 - rho) * impact[i-1] + lam * br[i-1]\n"
        "    return ew - impact  # remove residual impact from fair\n"
    ),
    "stoikov_ofi_fair": (
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "    n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    # Stoikov-Kercheval (2010): OFI fair = mid + alpha * OFI.\n"
        "    # Proxy OFI: signed return minus expected contribution from range.\n"
        "    ofi_proxy = np.where(br > 0, r - 0.5 * br, r)\n"
        "    ofi_proxy = np.where(np.isfinite(ofi_proxy), ofi_proxy, 0.0)\n"
        "    alpha = 0.5\n"
        "    return ew + alpha * ofi_proxy\n"
    ),
    "krohn_fix_adjusted_fair": (
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); hr = ctx.col('hour_utc')\n"
        "    n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    # Krohn et al. (2024): fix windows create temporary distortion.\n"
        "    # Pre-fix: dealers accumulate inventory -> appreciation.\n"
        "    # Post-fix: reversal.\n"
        "    in_london_fix = (hr >= 15.5) & (hr <= 16.5)\n"
        "    in_ecb_fix = (hr >= 12.0) & (hr <= 13.5)\n"
        "    adj = np.where(in_london_fix | in_ecb_fix, -r * 0.3, 0.0)\n"
        "    adj = np.where(np.isfinite(adj), adj, 0.0)\n"
        "    return ew + np.cumsum(adj)\n"
    ),
    "taylor_adaptive_fair": (
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "    n = r.shape[0]\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    # Taylor (2017): Parkinson-vol-adaptive alpha.\n"
        "    W = 20\n"
        "    c = np.concatenate(([0.0], np.cumsum(br * br)))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    ms = np.where(m > 0, m, 1.0)\n"
        "    parkinson = np.sqrt(np.clip((c[k] - c[lo]) / (ms * 4.0 * np.log(2.0)), 1e-12, None))\n"
        "    vol_cum = np.cumsum(np.where(np.isfinite(parkinson), parkinson, 0.0))\n"
        "    vol_cnt = np.cumsum(np.where(np.isfinite(parkinson), 1.0, 0.0))\n"
        "    vol_ref = vol_cum / np.maximum(vol_cnt, 1.0)\n"
        "    alpha = np.clip(0.02 + 0.08 * (parkinson / (vol_ref + 1e-9)), 0.02, 0.10)\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - alpha[i]) * acc + alpha[i] * p[i]; ew[i] = acc\n"
        "    return ew\n"
    ),
    "microprice_imbalance_fair": (
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "    n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    # Madhavan-Richardson-Roomans (1997) / Stoikov microprice.\n"
        "    # Order imbalance proxy: signed velocity / bar_range.\n"
        "    imb = np.where(br > 0, r / br, 0.0)\n"
        "    imb = np.where(np.isfinite(imb), imb, 0.0)\n"
        "    k = 0.5  # microprice coefficient\n"
        "    return ew + k * imb\n"
    ),
    "glosten_milgrom_fair": (
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    # Glosten-Milgrom (1985): adverse selection makes fair < mid for large moves.\n"
        "    # Proxy: fair = mid - lambda * |velocity|  (large moves are overreactions)\n"
        "    lam = 0.1\n"
        "    absr = np.abs(np.where(np.isfinite(r), r, 0.0))\n"
        "    return ew - lam * absr\n"
    ),
    "cointegration_trend_fair": (
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    # Engle-Granger (1987): online cointegration fair = intercept + beta * time.\n"
        "    t = np.arange(n, dtype=float)\n"
        "    sum_t = np.cumsum(t); sum_t2 = np.cumsum(t * t)\n"
        "    sum_p = np.cumsum(p); sum_tp = np.cumsum(t * p)\n"
        "    cnt = np.arange(1, n + 1, dtype=float)\n"
        "    denom = cnt * sum_t2 - sum_t * sum_t\n"
        "    denom = np.where(denom == 0, 1e-12, denom)\n"
        "    beta = (cnt * sum_tp - sum_t * sum_p) / denom\n"
        "    intercept = (sum_p - beta * sum_t) / cnt\n"
        "    fair = intercept + beta * t\n"
        "    return fair\n"
    ),
    "jump_robust_fair": (
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1')\n"
        "    n = r.shape[0]\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    # Bibinger (2024): robust fair price using median filter instead of mean.\n"
        "    W = 20\n"
        "    # Vectorised rolling median via np.lib.stride_tricks (no import needed).\n"
        "    padded = np.concatenate([np.full(W - 1, np.nan), p])\n"
        "    fair = np.nanmedian(np.lib.stride_tricks.sliding_window_view(padded, W), axis=1)\n"
        "    return fair\n"
    ),
}
# ── Rich prompt templates (one per branch) ────────────────────────────────────
RICH_TEMPLATES: dict[str, str] = {
    "baseline": (
        "BRANCH: baseline — slow EWMA fair price\n"
        "FORMULA: fair = EWMA(cumsum(returns), alpha=0.02)\n"
        "RATIONALE: A very slow EWMA captures the long-term price level while filtering"
        " out microstructure noise.  This is the simplest benchmark for fair-price estimation.\n"
        "NO ADJUSTMENT: No correction for bounce, impact, inventory, or seasonality.\n"
        "ALLOWED VARIATIONS: alpha ∈ {0.005, 0.01, 0.02, 0.05}\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    return ew\n"
        "```\n"
        "FAILURE PATTERN: alpha too high (>0.10) makes fair chase noise; too low (<0.005)"
        " makes fair unresponsive to genuine regime shifts.\n"
    ),
    "roll_bounce": (
        "BRANCH: roll_bounce — adjust fair for bid-ask bounce (Roll 1984, JFE)\n"
        "FORMULA: fair = EWMA(p) - sign(velocity) * spread/2\n"
        "RATIONALE: Roll (1984) showed that bid-ask bounce creates negative autocorrelation."
        " If the last return was positive, the transaction likely hit the ask, pushing mid up"
        " above fair.  Reversing the half-spread bounce gives a better fair estimate.\n"
        "KEY INSIGHT: This is NOT a spread-crossing strategy; it is a fair-price correction.\n"
        "ALLOWED VARIATIONS: spread_multiplier ∈ {0.3, 0.5, 0.7}\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); sp = ctx.col('spread_pips')\n"
        "    n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    bounce = np.sign(r) * sp * 0.5\n"
        "    return ew - bounce\n"
        "```\n"
        "FAILURE PATTERN: During fix windows or news, the bounce direction is not mechanical"
        " but driven by informed flow; reversing it then makes fair worse, not better.\n"
    ),
    "hasbrouck_efficient": (
        "BRANCH: hasbrouck_efficient — extract random-walk efficient price (Hasbrouck 1993, JFE)\n"
        "FORMULA: fair = EWMA(p, alpha=0.005) — much slower than baseline.\n"
        "RATIONALE: Hasbrouck (1993) decomposes price into efficient (random-walk) and"
        " microstructure noise components.  The efficient price is the component that persists;"
        " the noise mean-reverts to zero.  By using an extremely slow EWMA (alpha=0.005), we"
        " filter out the high-frequency noise and isolate the low-frequency efficient price.\n"
        "WHY ALPHA=0.005: At 100-tick bars, this is a ~200-bar half-life (~3 hours), matching"
        " the slowest persistent component in FX price dynamics.\n"
        "ALLOWED VARIATIONS: alpha ∈ {0.002, 0.005, 0.01}\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; a = 0.005\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    return ew\n"
        "```\n"
        "FAILURE PATTERN: Too slow to catch genuine regime shifts (e.g., ECB surprise); fair"
        " stays stale for hours after a structural break.\n"
    ),
    "evans_lyons_inventory": (
        "BRANCH: evans_lyons_inventory — portfolio-shift / inventory model (Evans-Lyons 2002, JPE)\n"
        "FORMULA: fair = EWMA(p) + lambda * cumulative_signed_velocity\n"
        "RATIONALE: Evans & Lyons (2002) showed that ~50% of daily FX variation is explained"
        " by portfolio shifts (order flow).  The cumulative signed flow is a proxy for dealer"
        " inventory imbalance.  When inventory is positive (net buying pressure), the fair price"
        " is above the current mid because the market must clear at a higher price to absorb"
        " the excess demand.  lambda is small (~0.001) because inventory effects are gradual.\n"
        "KEY INSIGHT: This is the OPPOSITE of fading — when inventory is high, fair is HIGHER,"
        " not lower.  The deviation (fair - mid) is positive, so we BUY (fade long).\n"
        "ALLOWED VARIATIONS: lambda ∈ {0.0005, 0.001, 0.002}\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    signed_r = np.where(np.isfinite(r), r, 0.0)\n"
        "    inventory = np.cumsum(signed_r)\n"
        "    lam = 0.001\n"
        "    return ew + lam * inventory\n"
        "```\n"
        "FAILURE PATTERN: lambda too large (>0.01) makes fair diverge linearly from mid;"
        " inventory never mean-reverts in this proxy, so the fair becomes unbounded.\n"
    ),
    "barzykin_propagator": (
        "BRANCH: barzykin_propagator — transient impact decay (Barzykin 2025/2026, arXiv:2601.13421)\n"
        "FORMULA: fair = EWMA(p) - impact_t; impact_t = (1-rho)*impact_{t-1} + lambda*range_{t-1}\n"
        "RATIONALE: Barzykin et al. model trade impact as an exponentially decaying propagator."
        " The observed mid includes not just the efficient price but also the residual impact"
        " from past trades.  By subtracting the estimated decaying impact, we get a cleansed"
        " fair price that reflects the underlying efficient price rather than mechanical"
        " price pressure.  This is especially important around news or fix windows.\n"
        "WHY RHO=0.1: At 100-tick bars, this is a ~10-bar half-life (~10 minutes), matching"
        " the observed short-term impact decay in EURUSD.\n"
        "ALLOWED VARIATIONS: rho ∈ {0.05, 0.10, 0.20}; lambda ∈ {0.3, 0.5, 0.8}\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "    n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    rho = 0.1; lam = 0.5\n"
        "    impact = np.zeros(n)\n"
        "    for i in range(1, n):\n"
        "        impact[i] = (1 - rho) * impact[i-1] + lam * br[i-1]\n"
        "    return ew - impact\n"
        "```\n"
        "FAILURE PATTERN: rho too high (>0.50) makes impact decay too fast, barely different"
        " from raw; rho too low (<0.01) makes impact accumulate endlessly, fair drifts to zero.\n"
    ),
    "stoikov_ofi": (
        "BRANCH: stoikov_ofi — OFI fair (Stoikov-Kercheval 2010, J. Financial Markets)\n"
        "FORMULA: fair = EWMA(p) + alpha * OFI_proxy; OFI_proxy = return - 0.5 * bar_range * sign(return)\n"
        "RATIONALE: Stoikov & Kercheval show that order flow imbalance (OFI) predicts price"
        " changes at the microsecond level.  Without Level-2 data, we proxy OFI using the"
        " deviation of the bar return from what we'd expect if the bar were symmetric."
        " If return > 0.5*range, the bar is buyer-initiated (positive OFI) and fair shifts up."
        " If return < -0.5*range, seller-initiated (negative OFI) and fair shifts down.\n"
        "ALLOWED VARIATIONS: alpha ∈ {0.3, 0.5, 0.8}; range_fraction ∈ {0.3, 0.5, 0.7}\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "    n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    ofi_proxy = np.where(br > 0, r - 0.5 * br, r)\n"
        "    ofi_proxy = np.where(np.isfinite(ofi_proxy), ofi_proxy, 0.0)\n"
        "    alpha = 0.5\n"
        "    return ew + alpha * ofi_proxy\n"
        "```\n"
        "FAILURE PATTERN: alpha too large (>2.0) makes fair overshoot; too small (<0.1)"
        " gives no microstructure signal.\n"
    ),
    "krohn_fix_adjusted": (
        "BRANCH: krohn_fix_adjusted — fix-window seasonal adjustment (Krohn et al. 2024, J. Finance)\n"
        "FORMULA: fair = EWMA(p) + cumulative_fix_adjustment; During London/ECB fix: adj = -velocity * 0.3\n"
        "RATIONALE: Krohn, Mueller & Whelan (2024) document a W-shaped intraday pattern in FX"
        " tied to three major fixes.  Dealers accumulate inventory pre-fix (appreciation),"
        " execute fix orders (dislocation), then reverse post-fix.  The observed mid during"
        " fix windows is temporarily distorted by fix-order flow.  Adjusting fair toward the"
        " expected post-fix reversal gives a better fair estimate during these windows.\n"
        "ALLOWED VARIATIONS: adjustment_scale ∈ {0.1, 0.2, 0.3, 0.5}\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); hr = ctx.col('hour_utc')\n"
        "    n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    in_london_fix = (hr >= 15.5) & (hr <= 16.5)\n"
        "    in_ecb_fix = (hr >= 12.0) & (hr <= 13.5)\n"
        "    adj = np.where(in_london_fix | in_ecb_fix, -r * 0.3, 0.0)\n"
        "    adj = np.where(np.isfinite(adj), adj, 0.0)\n"
        "    return ew + np.cumsum(adj)\n"
        "```\n"
        "FAILURE PATTERN: adjustment_scale too large (>0.5) over-corrects, fair flips sign;"
        " too small (<0.1) under-corrects, no improvement over baseline.\n"
    ),
    "taylor_adaptive": (
        "BRANCH: taylor_adaptive — Parkinson-vol-adaptive EWMA (Taylor 2017, J. Financial Econometrics)\n"
        "FORMULA: alpha_i = clip(0.02 + 0.08 * (parkinson_i / vol_ref_i), 0.02, 0.10)\n"
        "RATIONALE: FX volatility clusters (post-news spikes, Asian calm, London surges)."
        " A fixed EWMA alpha is either too sluggish during volatility spikes or too noisy"
        " during calm periods.  The Parkinson estimator (using bar_range) is more efficient"
        " than close-close variance.  Higher vol -> faster alpha catches dislocations quicker;"
        " lower vol -> smoother fair avoids false deviations.\n"
        "ALLOWED VARIATIONS: W ∈ {10, 20, 40}; alpha_min ∈ {0.01, 0.02}; alpha_max ∈ {0.08, 0.10, 0.15}\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "    n = r.shape[0]; W = 20\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    c = np.concatenate(([0.0], np.cumsum(br * br)))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "    ms = np.where(m > 0, m, 1.0)\n"
        "    parkinson = np.sqrt(np.clip((c[k] - c[lo]) / (ms * 4.0 * np.log(2.0)), 1e-12, None))\n"
        "    vol_cum = np.cumsum(np.where(np.isfinite(parkinson), parkinson, 0.0))\n"
        "    vol_cnt = np.cumsum(np.where(np.isfinite(parkinson), 1.0, 0.0))\n"
        "    vol_ref = vol_cum / np.maximum(vol_cnt, 1.0)\n"
        "    alpha = np.clip(0.02 + 0.08 * (parkinson / (vol_ref + 1e-9)), 0.02, 0.10)\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - alpha[i]) * acc + alpha[i] * p[i]; ew[i] = acc\n"
        "    return ew\n"
        "```\n"
        "FAILURE PATTERN: alpha_max too high (>0.15) fair chases noise; alpha_min too low"
        " (<0.01) fair is sluggish after vol spikes.\n"
    ),
    "microprice_imbalance": (
        "BRANCH: microprice_imbalance — order-imbalance fair (Madhavan 1997; Stoikov microprice)\n"
        "FORMULA: fair = EWMA(p) + k * (signed_velocity / bar_range)\n"
        "RATIONALE: Madhavan, Richardson & Roomans (1997) show that order imbalance explains"
        " a significant fraction of price variance.  The microprice (mid adjusted for imbalance)"
        " is a better estimate of fair value than the raw mid.  We proxy imbalance using the"
        " ratio of signed velocity to bar range: a bar with return = +range (fully up) implies"
        " strong buying imbalance, while return = -range implies selling imbalance.\n"
        "ALLOWED VARIATIONS: k ∈ {0.3, 0.5, 0.8, 1.0}\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "    n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    imb = np.where(br > 0, r / br, 0.0)\n"
        "    imb = np.where(np.isfinite(imb), imb, 0.0)\n"
        "    k = 0.5\n"
        "    return ew + k * imb\n"
        "```\n"
        "FAILURE PATTERN: k too large (>2.0) makes fair unstable; too small (<0.1) gives"
        " negligible adjustment.\n"
    ),
    "glosten_milgrom": (
        "BRANCH: glosten_milgrom — adverse-selection adjustment (Glosten-Milgrom 1985, JFE)\n"
        "FORMULA: fair = EWMA(p) - lambda * |velocity|\n"
        "RATIONALE: Glosten & Milgrom (1985) showed that market makers set bid/ask spreads"
        " to compensate for adverse selection.  Large moves are more likely to be informed"
        " than noise.  The fair price after a large move should be ADJUSTED in the direction"
        " of the move (because the informed trader knew something), not reverted.  Our proxy"
        " subtracts a small fraction of |velocity| from the EWMA fair, making fair LOWER after"
        " large positive moves (suggesting the move was overreaction, not information).\n"
        "NOTE: This is a FADE interpretation, not a momentum interpretation.  The literature"
        " is mixed on whether large moves are informed or noise; we test the fade hypothesis.\n"
        "ALLOWED VARIATIONS: lambda ∈ {0.05, 0.10, 0.20}\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; a = 0.02\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    ew = np.empty(n); acc = p[0]\n"
        "    for i in range(n):\n"
        "        acc = (1 - a) * acc + a * p[i]; ew[i] = acc\n"
        "    lam = 0.1\n"
        "    absr = np.abs(np.where(np.isfinite(r), r, 0.0))\n"
        "    return ew - lam * absr\n"
        "```\n"
        "FAILURE PATTERN: lambda too large (>0.5) makes fair diverge from mid permanently;"
        " too small (<0.01) gives no adjustment.\n"
    ),
    "cointegration_trend": (
        "BRANCH: cointegration_trend — online cointegration fair (Engle-Granger 1987, Econometrica)\n"
        "FORMULA: fair_t = intercept_t + beta_t * t; beta_t, intercept_t = causal expanding OLS of p on time.\n"
        "RATIONALE: If price has a persistent trend component (e.g., carry-trade drift), the"
        " fair price should include that trend.  The EWMA baseline ignores trends and treats"
        " a trending market as permanently deviated.  By fitting an online linear trend, we"
        " get a fair price that adapts to drift while still identifying deviations from trend.\n"
        "WHY EXPANDING (not rolling): FX trends can last months; a rolling window would"
        " break the trend at the window boundary.  Expanding OLS is more stable for long-lived trends.\n"
        "ALLOWED VARIATIONS: None (online OLS is self-tuning).\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    t = np.arange(n, dtype=float)\n"
        "    sum_t = np.cumsum(t); sum_t2 = np.cumsum(t * t)\n"
        "    sum_p = np.cumsum(p); sum_tp = np.cumsum(t * p)\n"
        "    cnt = np.arange(1, n + 1, dtype=float)\n"
        "    denom = cnt * sum_t2 - sum_t * sum_t\n"
        "    denom = np.where(denom == 0, 1e-12, denom)\n"
        "    beta = (cnt * sum_tp - sum_t * sum_p) / denom\n"
        "    intercept = (sum_p - beta * sum_t) / cnt\n"
        "    return intercept + beta * t\n"
        "```\n"
        "FAILURE PATTERN: Early bars (t < 100) have unstable OLS estimates; the fair oscillates.\n"
    ),
    "jump_robust": (
        "BRANCH: jump_robust — median-based fair robust to jumps (Bibinger 2024, arXiv:2403.00819)\n"
        "FORMULA: fair_t = median(p_{t-W+1}, ..., p_t)\n"
        "RATIONALE: Bibinger, Hautsch & Ristig (2024) show that >85% of intraday jumps have"
        " no identifiable news.  These are microstructure artifacts.  A mean-based fair (EWMA)"
        " is contaminated by jumps, pulling fair in the jump direction.  A median-based fair"
        " is robust: a single jump outlier does not shift the median.\n"
        "WHY MEDIAN NOT TRIMMED-MEAN: Median is naturally robust to arbitrary outliers without"
        " requiring a trimming threshold.  It also has a simple causal implementation.\n"
        "ALLOWED VARIATIONS: W ∈ {10, 20, 40} (median window length)\n"
        "REFERENCE IMPLEMENTATION:\n"
        "```python\n"
        "def estimate_fair(ctx):\n"
        "    r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "    n = r.shape[0]\n"
        "    p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "    W = 20\n"
        "    fair = np.empty(n)\n"
        "    for i in range(n):\n"
        "        lo = max(0, i - W + 1)\n"
        "        fair[i] = np.median(p[lo:i+1])\n"
        "    return fair\n"
        "```\n"
        "FAILURE PATTERN: W too small (<10) fair is noisy; too large (>100) fair lags badly.\n"
    ),
}

# ── Cross-branch recombination prompts ───────────────────────────────────────
CROSS_BRANCH_PROMPTS: dict[tuple[str, str], str] = {
    ("roll_bounce", "barzykin_propagator"): (
        "COMBINATION: roll_bounce + barzykin_propagator\n"
        "SYNERGY: Roll corrects for mechanical bid-ask bounce; Barzykin corrects for decaying"
        " trade impact.  Both are transient-distortion corrections but operate at different"
        " timescales.  Roll is immediate (one bar); Barzykin decays over ~10 bars."
        " Together they give a fair price cleansed of both short- and medium-term distortions.\n"
        "Write a single `estimate_fair(ctx)` that combines both ideas.\n"
    ),
    ("hasbrouck_efficient", "barzykin_propagator"): (
        "COMBINATION: hasbrouck_efficient + barzykin_propagator\n"
        "SYNERGY: Hasbrouck extracts the very-slow efficient price (random-walk component)."
        " Barzykin removes medium-term impact distortion.  Hasbrouck is too slow for scalping;"
        " Barzykin is too fast to capture the persistent trend.  Together: Barzykin provides a"
        " fast fair for short-horizon deviation; Hasbrouck provides a slow anchor for long-horizon"
        " trend.  Use Hasbrouck as baseline and Barzykin as a deviation adjustment.\n"
        "Write a single `estimate_fair(ctx)` that combines both ideas.\n"
    ),
    ("evans_lyons_inventory", "microprice_imbalance"): (
        "COMBINATION: evans_lyons_inventory + microprice_imbalance\n"
        "SYNERGY: Evans-Lyons uses cumulative signed flow (slow, persistent inventory)."
        " Microprice uses per-bar imbalance (fast, transient).  The cumulative flow captures"
        " long-term order-pressure; the per-bar imbalance captures immediate microstructure."
        " Together they cover both timescales of order-flow information.\n"
        "Write a single `estimate_fair(ctx)` that combines both ideas.\n"
    ),
    ("stoikov_ofi", "microprice_imbalance"): (
        "COMBINATION: stoikov_ofi + microprice_imbalance\n"
        "SYNERGY: Both use order-flow proxies but differently.  Stoikov OFI uses the deviation"
        " of return from its expected range contribution (buyer vs seller initiation)."
        " Microprice uses the ratio of signed return to range (imbalance intensity)."
        " OFI tells us the DIRECTION of flow; microprice tells us the INTENSITY."
        " Together they give a richer flow signal than either alone.\n"
        "Write a single `estimate_fair(ctx)` that combines both ideas.\n"
    ),
    ("krohn_fix_adjusted", "barzykin_propagator"): (
        "COMBINATION: krohn_fix_adjusted + barzykin_propagator\n"
        "SYNERGY: Krohn handles deterministic calendar distortion (fix windows)."
        " Barzykin handles stochastic mechanical distortion (trade impact)."
        " During fix windows, both effects are present: fix-order flow creates impact that"
        " decays after the fix.  Krohn adjusts for the calendar component; Barzykin adjusts"
        " for the residual impact.  Together they give a doubly-cleansed fair price during"
        " the most distorted periods of the day.\n"
        "Write a single `estimate_fair(ctx)` that combines both ideas.\n"
    ),
    ("taylor_adaptive", "barzykin_propagator"): (
        "COMBINATION: taylor_adaptive + barzykin_propagator\n"
        "SYNERGY: Taylor adapts the fair-price EWMA speed to local volatility."
        " Barzykin removes impact distortion from the fair price.  During high-vol periods"
        " (where Taylor speeds up), impact is also larger (where Barzykin is most needed)."
        " Together: a fast-responding fair that is also impact-cleansed — exactly what we"
        " need during volatile episodes.\n"
        "Write a single `estimate_fair(ctx)` that combines both ideas.\n"
    ),
    ("jump_robust", "hasbrouck_efficient"): (
        "COMBINATION: jump_robust + hasbrouck_efficient\n"
        "SYNERGY: Hasbrouck extracts the efficient price but is contaminated by jumps (the"
        " EWMA pulls toward the jump).  Jump_robust uses a median filter that is immune to jumps."
        " Use jump_robust as the fair-price estimator and Hasbrouck as a slow anchor to"
        " prevent median-based fair from drifting.  Or: switch to median only when a jump is"
        " detected, using EWMA otherwise.\n"
        "Write a single `estimate_fair(ctx)` that combines both ideas.\n"
    ),
    ("glosten_milgrom", "microprice_imbalance"): (
        "COMBINATION: glosten_milgrom + microprice_imbalance\n"
        "SYNERGY: Glosten-Milgrom adjusts fair DOWN after large moves (adverse selection /"
        " overreaction).  Microprice adjusts fair UP after buying-imbalance bars (order flow)."
        " These are OPPOSITE hypotheses: one says large moves are noise to fade; the other"
        " says they are informed to follow.  Combine them by letting the microprice imbalance"
        " decide whether a move is informed (follow) or noise (fade): if imbalance is high,"
        " follow; if low, fade.\n"
        "Write a single `estimate_fair(ctx)` that combines both ideas.\n"
    ),
    ("cointegration_trend", "hasbrouck_efficient"): (
        "COMBINATION: cointegration_trend + hasbrouck_efficient\n"
        "SYNERGY: Cointegration extracts a linear trend from the price history.  Hasbrouck"
        " extracts the efficient price by filtering noise.  The cointegration fair includes"
        " trend but is contaminated by short-term noise.  Hasbrouck is noise-free but trend-free."
        " Together: use Hasbrouck as the fair and add the cointegration trend as a slow drift"
        " adjustment.  This gives a fair price that both trends and filters noise.\n"
        "Write a single `estimate_fair(ctx)` that combines both ideas.\n"
    ),
}

def _build_cross_branch_index():
    out = {}
    for (b1, b2), text in CROSS_BRANCH_PROMPTS.items():
        out[(b1, b2)] = text
        out[(b2, b1)] = text
    return out

CROSS_BRANCH_INDEX: dict[tuple[str, str], str] = _build_cross_branch_index()

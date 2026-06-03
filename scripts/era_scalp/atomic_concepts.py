"""Atomic concept library for fair-price estimation.

Decomposes fair-price estimation into 5 categories of composable operators:
  1. Base Estimators     — slow_ewma, fast_ewma, median_filter, expanding_ols, rolling_ols
  2. Microstructure Corr — roll_bounce, barzykin_impact, glosten_adverse, ofi_imbalance,
                           microprice_imbalance, kyle_informed, pin_flow, almgren_impact,
                           ow_propagator, csk_impact
  3. Calendar/Seasonal   — krohn_fix_adjusted, hour_of_day_drift, weekend_gap
  4. Vol Adaptation      — taylor_adaptive_alpha, parkinson_vol, realized_vol_gate
  5. Combination         — additive_blend, multiplicative_gate, conditional_switch

Each operator is a small code template the LLM fills into a skeleton composition.
"""
from __future__ import annotations

import textwrap


# ── Atomic operator templates ────────────────────────────────────────────────
# Each template is a snippet of Python that operates on ctx and returns an array.
# The LLM is asked to combine these snippets into a full estimate_fair(ctx).

BASE_ESTIMATORS: dict[str, str] = {
    "slow_ewma": (
        "# Base: very-slow EWMA of price level (Hasbrouck efficient-price style)\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]; alpha = {{alpha}}  # e.g. 0.005\n"
        "p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "ew = np.empty(n); acc = p[0]\n"
        "for i in range(n):\n"
        "    acc = (1 - alpha) * acc + alpha * p[i]; ew[i] = acc\n"
        "base = ew\n"
    ),
    "fast_ewma": (
        "# Base: fast EWMA for responsiveness\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]; alpha = {{alpha}}  # e.g. 0.10\n"
        "p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "ew = np.empty(n); acc = p[0]\n"
        "for i in range(n):\n"
        "    acc = (1 - alpha) * acc + alpha * p[i]; ew[i] = acc\n"
        "base = ew\n"
    ),
    "median_filter": (
        "# Base: rolling median (jump-robust, Bibinger style)\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]\n"
        "p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "W = {{W}}  # e.g. 20\n"
        "padded = np.concatenate([np.full(W - 1, np.nan), p])\n"
        "base = np.nanmedian(np.lib.stride_tricks.sliding_window_view(padded, W), axis=1)\n"
    ),
    "expanding_ols": (
        "# Base: online linear trend (Engle-Granger style)\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]\n"
        "p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "t = np.arange(n, dtype=float)\n"
        "sum_t = np.cumsum(t); sum_t2 = np.cumsum(t * t)\n"
        "sum_p = np.cumsum(p); sum_tp = np.cumsum(t * p)\n"
        "cnt = np.arange(1, n + 1, dtype=float)\n"
        "denom = cnt * sum_t2 - sum_t * sum_t\n"
        "denom = np.where(denom == 0, 1e-12, denom)\n"
        "beta = (cnt * sum_tp - sum_t * sum_p) / denom\n"
        "intercept = (sum_p - beta * sum_t) / cnt\n"
        "base = intercept + beta * t\n"
    ),
    "rolling_ols": (
        "# Base: rolling-window linear trend\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]; W = {{W}}  # e.g. 100\n"
        "p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "t = np.arange(n, dtype=float)\n"
        "base = np.empty(n)\n"
        "for i in range(n):\n"
        "    lo = max(0, i - W + 1)\n"
        "    if i - lo + 1 < 5:\n"
        "        base[i] = p[i]\n"
        "    else:\n"
        "        tt = t[lo:i+1]; pp = p[lo:i+1]\n"
        "        A = np.vstack([tt, np.ones_like(tt)]).T\n"
        "        beta, inter = np.linalg.lstsq(A, pp, rcond=None)[0]\n"
        "        base[i] = beta * t[i] + inter\n"
    ),
}

MICROSTRUCTURE_CORRECTIONS: dict[str, str] = {
    "roll_bounce": (
        "# Correction: reverse bid-ask bounce (Roll 1984)\n"
        "r = ctx.col('vel_pips_h1'); sp = ctx.col('spread_pips')\n"
        "bounce = np.sign(r) * sp * {{mult}}  # mult ∈ {0.3, 0.5, 0.7}\n"
        "correction = -bounce\n"
    ),
    "barzykin_impact": (
        "# Correction: transient impact decay (Barzykin 2025/26)\n"
        "br = ctx.col('bar_range_pips'); n = br.shape[0]\n"
        "rho = {{rho}}; lam = {{lam}}  # rho ∈ {0.05,0.10,0.20}, lam ∈ {0.3,0.5,0.8}\n"
        "impact = np.zeros(n)\n"
        "for i in range(1, n):\n"
        "    impact[i] = (1 - rho) * impact[i-1] + lam * br[i-1]\n"
        "correction = -impact\n"
    ),
    "glosten_adverse": (
        "# Correction: adverse-selection fade (Glosten-Milgrom 1985)\n"
        "r = ctx.col('vel_pips_h1')\n"
        "lam = {{lam}}  # e.g. 0.1\n"
        "absr = np.abs(np.where(np.isfinite(r), r, 0.0))\n"
        "correction = -lam * absr\n"
    ),
    "ofi_imbalance": (
        "# Correction: order-flow imbalance proxy (Stoikov-Kercheval 2010)\n"
        "r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "ofi = np.where(br > 0, r - 0.5 * br, r)\n"
        "ofi = np.where(np.isfinite(ofi), ofi, 0.0)\n"
        "alpha = {{alpha}}  # e.g. 0.5\n"
        "correction = alpha * ofi\n"
    ),
    "microprice_imbalance": (
        "# Correction: microprice order-imbalance proxy (Madhavan 1997)\n"
        "r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "imb = np.where(br > 0, r / br, 0.0)\n"
        "imb = np.where(np.isfinite(imb), imb, 0.0)\n"
        "k = {{k}}  # e.g. 0.5\n"
        "correction = k * imb\n"
    ),
    "kyle_informed": (
        "# Correction: Kyle informed-trader permanent impact (Kyle 1985)\n"
        "r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "# Informed flow proxy: large bars with same-direction persistence\n"
        "sign_r = np.sign(np.where(np.isfinite(r), r, 0.0))\n"
        "abs_r = np.abs(np.where(np.isfinite(r), r, 0.0))\n"
        "informed = np.where(abs_r > np.quantile(abs_r, 0.75), sign_r, 0.0)\n"
        "lambda_k = {{lambda_k}}  # e.g. 0.3\n"
        "correction = lambda_k * np.cumsum(informed)\n"
    ),
    "pin_flow": (
        "# Correction: Easley-O'Hara PIN-informed-flow proxy (1987/1992)\n"
        "r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "vol = ctx.col('tick_volume')\n"
        "# Proxy: high-volume + large-range bars = more likely informed\n"
        "vol_z = (vol - np.nanmean(vol)) / np.nanstd(vol) if np.nanstd(vol) > 0 else np.zeros_like(vol)\n"
        "range_z = (br - np.nanmean(br)) / np.nanstd(br) if np.nanstd(br) > 0 else np.zeros_like(br)\n"
        "pin_proxy = np.where((vol_z > 1) & (range_z > 1), np.sign(r), 0.0)\n"
        "pin_proxy = np.where(np.isfinite(pin_proxy), pin_proxy, 0.0)\n"
        "pin_cum = np.cumsum(pin_proxy)\n"
        "gamma = {{gamma}}  # e.g. 0.001\n"
        "correction = gamma * pin_cum\n"
    ),
    "almgren_impact": (
        "# Correction: Almgren-Chriss permanent+temporary impact (2000)\n"
        "r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips'); n = r.shape[0]\n"
        "# Permanent impact: cumulative signed flow\n"
        "signed_r = np.where(np.isfinite(r), r, 0.0)\n"
        "perm = np.cumsum(signed_r)\n"
        "# Temporary impact: exponentially decaying residual\n"
        "rho = {{rho}}; eta = {{eta}}  # rho ∈ {0.05,0.10}, eta ∈ {0.3,0.5}\n"
        "temp = np.zeros(n)\n"
        "for i in range(1, n):\n"
        "    temp[i] = (1 - rho) * temp[i-1] + eta * br[i-1]\n"
        "correction = -perm * 0.01 - temp\n"
    ),
    "ow_propagator": (
        "# Correction: Obizhaeva-Wang resilience propagator (2013)\n"
        "br = ctx.col('bar_range_pips'); n = br.shape[0]\n"
        "# Resilience model: impact decays to zero at rate beta\n"
        "beta = {{beta}}; kappa = {{kappa}}  # beta ∈ {0.05,0.10}, kappa ∈ {0.3,0.5}\n"
        "J = np.zeros(n); Q = np.zeros(n)\n"
        "for i in range(1, n):\n"
        "    J[i] = (1 - beta) * J[i-1] + beta * kappa * br[i-1]\n"
        "    Q[i] = Q[i-1] + J[i]\n"
        "correction = -Q\n"
    ),
    "csk_impact": (
        "# Correction: Cont-Stoikov-Kukanov order-book impact (2014)\n"
        "r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips')\n"
        "vol = ctx.col('tick_volume')\n"
        "# Price impact proportional to signed order flow / market depth proxy\n"
        "depth_proxy = np.maximum(vol, 1.0)\n"
        "signed_flow = np.where(np.isfinite(r), r, 0.0) * depth_proxy\n"
        "xi = {{xi}}  # e.g. 0.001\n"
        "correction = -xi * np.cumsum(signed_flow)\n"
    ),
    "foucault_competition": (
        "# Correction: Foucault limit-order competition proxy (1999)\n"
        "r = ctx.col('vel_pips_h1'); sp = ctx.col('spread_pips')\n"
        "# Tight spread = intense competition; wide spread = relaxed\n"
        "sp_z = (sp - np.nanmean(sp)) / np.nanstd(sp) if np.nanstd(sp) > 0 else np.zeros_like(sp)\n"
        "# When spread is tight, fair is closer to mid (less room for edge)\n"
        "correction = -sp_z * {{scale}}  # scale ∈ {0.5, 1.0, 2.0}\n"
    ),
    "rosu_dynamic": (
        "# Correction: Rosu dynamic LOB equilibrium (2009)\n"
        "r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips'); n = r.shape[0]\n"
        "# Dynamic equilibrium: fair price drifts toward where supply=demand\n"
        "# Proxy: if range is expanding, market is imbalanced\n"
        "range_ma = np.empty(n); acc = br[0] if np.isfinite(br[0]) else 0.0\n"
        "for i in range(n):\n"
        "    acc = 0.9 * acc + 0.1 * br[i] if np.isfinite(br[i]) else acc\n"
        "    range_ma[i] = acc\n"
        "imbalance = np.where(br > range_ma, 1.0, -1.0)\n"
        "imbalance = np.where(np.isfinite(imbalance), imbalance, 0.0)\n"
        "drift = np.cumsum(imbalance) * {{mu}}  # mu ∈ {0.001, 0.005}\n"
        "correction = drift\n"
    ),
    "bhs_book_depth": (
        "# Correction: Biais-Hillion-Spatt order-book depth dynamics (1995)\n"
        "r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips'); n = r.shape[0]\n"
        "# Depth proxy: inverse of range (tight range = deep book)\n"
        "depth = 1.0 / np.maximum(br, 1e-6)\n"
        "depth_ew = np.empty(n); acc = depth[0] if np.isfinite(depth[0]) else 0.0\n"
        "for i in range(n):\n"
        "    acc = 0.95 * acc + 0.05 * depth[i] if np.isfinite(depth[i]) else acc\n"
        "    depth_ew[i] = acc\n"
        "# When depth drops (shallow book), fair shifts away from mid\n"
        "depth_change = depth_ew - np.nanmean(depth_ew)\n"
        "correction = depth_change * {{scale}}  # scale ∈ {0.5, 1.0, 2.0}\n"
    ),
}

CALENDAR_CORRECTIONS: dict[str, str] = {
    "krohn_fix_adjusted": (
        "# Calendar: fix-window seasonal adjustment (Krohn et al. 2024)\n"
        "r = ctx.col('vel_pips_h1'); hr = ctx.col('hour_utc')\n"
        "in_london = (hr >= 15.5) & (hr <= 16.5)\n"
        "in_ecb = (hr >= 12.0) & (hr <= 13.5)\n"
        "adj = np.where(in_london | in_ecb, -r * {{scale}}, 0.0)  # scale ∈ {0.1,0.2,0.3,0.5}\n"
        "adj = np.where(np.isfinite(adj), adj, 0.0)\n"
        "calendar = np.cumsum(adj)\n"
    ),
    "hour_drift": (
        "# Calendar: hour-of-day drift correction\n"
        "r = ctx.col('vel_pips_h1'); hr = ctx.col('hour_utc'); n = r.shape[0]\n"
        "# Expanding mean return by hour\n"
        "hour_sums = np.zeros(24); hour_cnts = np.zeros(24)\n"
        "drift = np.zeros(n)\n"
        "for i in range(n):\n"
        "    h = int(hr[i]) % 24\n"
        "    if hour_cnts[h] > 0:\n"
        "        drift[i] = hour_sums[h] / hour_cnts[h]\n"
        "    hour_sums[h] += r[i] if np.isfinite(r[i]) else 0.0\n"
        "    hour_cnts[h] += 1.0\n"
        "calendar = -drift * {{scale}}  # scale ∈ {0.5, 1.0, 2.0}\n"
    ),
    "weekend_gap": (
        "# Calendar: weekend gap fade\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]\n"
        "# Detect large opening moves (weekend gap proxy)\n"
        "gap = np.where(np.abs(r) > np.nanquantile(np.abs(r), 0.95), r, 0.0)\n"
        "calendar = -gap * {{reversion}}  # reversion ∈ {0.3, 0.5, 0.7}\n"
    ),
}

VOLATILITY_ADAPTATIONS: dict[str, str] = {
    "taylor_adaptive_alpha": (
        "# Vol-adapt: Parkinson-based adaptive EWMA alpha (Taylor 2017)\n"
        "br = ctx.col('bar_range_pips'); n = br.shape[0]; W = {{W}}  # e.g. 20\n"
        "c = np.concatenate(([0.0], np.cumsum(br * br)))\n"
        "k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "ms = np.where(m > 0, m, 1.0)\n"
        "parkinson = np.sqrt(np.clip((c[k] - c[lo]) / (ms * 4.0 * np.log(2.0)), 1e-12, None))\n"
        "vol_cum = np.cumsum(np.where(np.isfinite(parkinson), parkinson, 0.0))\n"
        "vol_cnt = np.cumsum(np.where(np.isfinite(parkinson), 1.0, 0.0))\n"
        "vol_ref = vol_cum / np.maximum(vol_cnt, 1.0)\n"
        "alpha_arr = np.clip(0.02 + 0.08 * (parkinson / (vol_ref + 1e-9)), {{alpha_min}}, {{alpha_max}})\n"
        "r = ctx.col('vel_pips_h1'); p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "ew = np.empty(n); acc = p[0]\n"
        "for i in range(n):\n"
        "    acc = (1 - alpha_arr[i]) * acc + alpha_arr[i] * p[i]; ew[i] = acc\n"
        "vol_adapted = ew\n"
    ),
    "parkinson_vol_gate": (
        "# Vol-adapt: gate based on Parkinson vol vs reference\n"
        "br = ctx.col('bar_range_pips'); n = br.shape[0]; W = {{W}}  # e.g. 20\n"
        "c = np.concatenate(([0.0], np.cumsum(br * br)))\n"
        "k = np.arange(n); lo = np.maximum(0, k - W)\n"
        "m = (k - lo).astype(float); ms = np.where(m > 0, m, 1.0)\n"
        "parkinson = np.sqrt(np.clip((c[k] - c[lo]) / (ms * 4.0 * np.log(2.0)), 1e-12, None))\n"
        "vol_ref = np.nanmean(parkinson) if np.nanmean(parkinson) > 0 else 1.0\n"
        "vol_ratio = parkinson / vol_ref\n"
        "# Higher vol = faster fair (use fast_ewma), lower vol = slower fair (use slow_ewma)\n"
        "vol_adapted = vol_ratio\n"
    ),
    "realized_vol_gate": (
        "# Vol-adapt: gate based on realized volatility\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]; W = {{W}}  # e.g. 20\n"
        "abs_r = np.abs(np.where(np.isfinite(r), r, 0.0))\n"
        "c = np.concatenate(([0.0], np.cumsum(abs_r * abs_r)))\n"
        "k = np.arange(n); lo = np.maximum(0, k - W)\n"
        "rv = np.sqrt(np.clip((c[k] - c[lo]) / np.maximum(k - lo, 1).astype(float), 0, None))\n"
        "rv_ref = np.nanmean(rv) if np.nanmean(rv) > 0 else 1.0\n"
        "vol_adapted = rv / rv_ref\n"
    ),
}

COMBINATION_OPERATORS: dict[str, str] = {
    "additive_blend": (
        "# Combine: weighted additive blend\n"
        "fair = {{w_base}} * base + {{w_corr}} * correction + {{w_cal}} * calendar\n"
    ),
    "multiplicative_gate": (
        "# Combine: multiplicative gate — correction scales the base\n"
        "fair = base * (1 + {{gain}} * correction / (np.nanstd(base) + 1e-9))\n"
    ),
    "conditional_switch": (
        "# Combine: conditional switch based on regime\n"
        "regime = {{regime_signal}}  # e.g. vol_ratio > 1.5\n"
        "fair = np.where(regime, base + correction, base)\n"
    ),
    "vol_adaptive_base": (
        "# Combine: vol-adaptive base selection\n"
        "# If vol is high, use responsive estimator; if low, use smooth estimator\n"
        "fair = np.where(vol_adapted > {{threshold}}, fast_base, slow_base)\n"
    ),
}


# ── Concept taxonomy for branch tracking ─────────────────────────────────────
CONCEPT_TAXONOMY: dict[str, tuple[str, str]] = {
    # (category, description)
    "slow_ewma": ("base", "Very-slow EWMA of price level (alpha ~0.005)"),
    "fast_ewma": ("base", "Fast EWMA for responsiveness (alpha ~0.10)"),
    "median_filter": ("base", "Rolling median jump-robust filter (Bibinger)"),
    "expanding_ols": ("base", "Online linear trend (Engle-Granger)"),
    "rolling_ols": ("base", "Rolling-window linear trend"),
    "roll_bounce": ("microstructure", "Reverse bid-ask bounce (Roll 1984)"),
    "barzykin_impact": ("microstructure", "Transient impact decay (Barzykin 2025/26)"),
    "glosten_adverse": ("microstructure", "Adverse-selection fade (Glosten-Milgrom 1985)"),
    "ofi_imbalance": ("microstructure", "OFI imbalance proxy (Stoikov-Kercheval 2010)"),
    "microprice_imbalance": ("microstructure", "Microprice order-imbalance (Madhavan 1997)"),
    "kyle_informed": ("microstructure", "Kyle informed-trader permanent impact (1985)"),
    "pin_flow": ("microstructure", "PIN informed-flow proxy (Easley-O'Hara 1987/92)"),
    "almgren_impact": ("microstructure", "Permanent+temporary impact (Almgren-Chriss 2000)"),
    "ow_propagator": ("microstructure", "Resilience propagator (Obizhaeva-Wang 2013)"),
    "csk_impact": ("microstructure", "Order-book impact (Cont-Stoikov-Kukanov 2014)"),
    "foucault_competition": ("microstructure", "LOB competition proxy (Foucault 1999)"),
    "rosu_dynamic": ("microstructure", "Dynamic LOB equilibrium (Rosu 2009)"),
    "bhs_book_depth": ("microstructure", "Order-book depth dynamics (Biais-Hillion-Spatt 1995)"),
    "krohn_fix_adjusted": ("calendar", "Fix-window seasonal adjustment (Krohn et al. 2024)"),
    "hour_drift": ("calendar", "Hour-of-day drift correction"),
    "weekend_gap": ("calendar", "Weekend gap fade"),
    "taylor_adaptive_alpha": ("volatility", "Parkinson adaptive EWMA alpha (Taylor 2017)"),
    "parkinson_vol_gate": ("volatility", "Parkinson vol regime gate"),
    "realized_vol_gate": ("volatility", "Realized vol regime gate"),
    "additive_blend": ("combination", "Weighted additive blend"),
    "multiplicative_gate": ("combination", "Multiplicative scaling gate"),
    "conditional_switch": ("combination", "Conditional regime switch"),
    "vol_adaptive_base": ("combination", "Vol-adaptive base selection"),
}


# ── Skeleton compositions the LLM fills ──────────────────────────────────────
# Each skeleton is a full estimate_fair(ctx) with {{holes}} for operators.

SKELETONS: dict[str, str] = {
    "simple": (
        "def estimate_fair(ctx):\n"
        "    import numpy as np\n"
        "    {{base}}\n"
        "    return base\n"
    ),
    "base_plus_correction": (
        "def estimate_fair(ctx):\n"
        "    import numpy as np\n"
        "    {{base}}\n"
        "    {{correction}}\n"
        "    {{combination}}\n"
        "    return fair\n"
    ),
    "base_plus_correction_plus_calendar": (
        "def estimate_fair(ctx):\n"
        "    import numpy as np\n"
        "    {{base}}\n"
        "    {{correction}}\n"
        "    {{calendar}}\n"
        "    {{combination}}\n"
        "    return fair\n"
    ),
    "vol_adaptive": (
        "def estimate_fair(ctx):\n"
        "    import numpy as np\n"
        "    {{vol_adaptation}}\n"
        "    {{base}}\n"
        "    {{correction}}\n"
        "    {{combination}}\n"
        "    return fair\n"
    ),
    "dual_base_switch": (
        "def estimate_fair(ctx):\n"
        "    import numpy as np\n"
        "    {{vol_adaptation}}\n"
        "    {{slow_base}}\n"
        "    {{fast_base}}\n"
        "    {{correction}}\n"
        "    {{combination}}\n"
        "    return fair\n"
    ),
}


def build_composition_prompt(
    skeleton_name: str,
    base: str,
    correction: str | None = None,
    calendar: str | None = None,
    vol_adaptation: str | None = None,
    combination: str = "additive_blend",
) -> str:
    """Build a rich prompt asking the LLM to fill a skeleton with specific operators.

    Parameters
    ----------
    skeleton_name : str
        One of SKELETONS keys.
    base, correction, calendar, vol_adaptation, combination : str
        Concept names whose templates are substituted into the skeleton.
    """
    skeleton = SKELETONS.get(skeleton_name, SKELETONS["simple"])

    # Fetch templates
    base_tmpl = BASE_ESTIMATORS.get(base, BASE_ESTIMATORS["slow_ewma"])
    corr_tmpl = MICROSTRUCTURE_CORRECTIONS.get(correction, "") if correction else ""
    cal_tmpl = CALENDAR_CORRECTIONS.get(calendar, "") if calendar else ""
    vol_tmpl = VOLATILITY_ADAPTATIONS.get(vol_adaptation, "") if vol_adaptation else ""
    comb_tmpl = COMBINATION_OPERATORS.get(combination, COMBINATION_OPERATORS["additive_blend"])

    # Indent for function body
    base_code = textwrap.indent(base_tmpl.strip(), "    ")
    corr_code = textwrap.indent(corr_tmpl.strip(), "    ") if corr_tmpl else "    # (no correction)"
    cal_code = textwrap.indent(cal_tmpl.strip(), "    ") if cal_tmpl else "    # (no calendar)"
    vol_code = textwrap.indent(vol_tmpl.strip(), "    ") if vol_tmpl else "    # (no vol adaptation)"
    comb_code = textwrap.indent(comb_tmpl.strip(), "    ")

    body = skeleton.format(
        base=base_code,
        correction=corr_code,
        calendar=cal_code,
        vol_adaptation=vol_code,
        combination=comb_code,
    )

    prompt = (
        "You are composing a fair-price estimator from atomic microstructure operators.\n"
        "Fill in the {{parameter}} placeholders (e.g. alpha=0.005, mult=0.5, etc.)\n"
        "with sensible values from the allowed ranges shown in comments.\n\n"
        "SKELETON: " + skeleton_name + "\n"
        "COMPONENTS:\n"
        "  - base: " + base + "\n"
        + ("  - correction: " + correction + "\n" if correction else "")
        + ("  - calendar: " + calendar + "\n" if calendar else "")
        + ("  - vol_adaptation: " + vol_adaptation + "\n" if vol_adaptation else "")
        + "  - combination: " + combination + "\n\n"
        "CODE TO FILL:\n"
        "```python\n" + body + "```\n\n"
        "YOUR TASK:\n"
        "Write a COMPLETE `estimate_fair(ctx)` function. Fill ALL {{parameter}}\n"
        "placeholders with concrete numbers. Output ONLY one ```python block.\n"
    )
    return prompt


def extract_concepts_from_source(src: str) -> list[str]:
    """Heuristic extraction of which atomic concepts appear in a program source.

    Looks for comment markers and variable names that match concept keys.
    Returns a list of matched concept names (best-effort, not guaranteed).
    """
    concepts = []
    for name in CONCEPT_TAXONOMY:
        # Match concept name in comments or as variable names
        patterns = [
            f"# .*{name}",
            f"{name}_",
            f"_{name}",
            f" {name} ",
        ]
        for pat in patterns:
            if pat.replace(" ", "").lower() in src.lower():
                concepts.append(name)
                break
    return concepts

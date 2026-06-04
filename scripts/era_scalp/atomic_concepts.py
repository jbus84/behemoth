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
    "price_level": (
        "# Base: raw cumulative price level (no smoothing)\n"
        "r = ctx.col('vel_pips_h1')\n"
        "base = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
    ),
    "permanent_extract": (
        "# Base: Hasbrouck-style permanent component (VAR random-walk extraction)\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]; W = {{W}}  # e.g. 100\n"
        "rc = np.where(np.isfinite(r), r, 0.0)\n"
        "r_lag = np.empty_like(rc); r_lag[0] = 0.0; r_lag[1:] = rc[:-1]\n"
        "# Rolling AR(1) coefficient on returns (causal)\n"
        "rlag_padded = np.concatenate([np.full(W - 1, np.nan), r_lag])\n"
        "rc_padded = np.concatenate([np.full(W - 1, np.nan), rc])\n"
        "rlag_win = np.lib.stride_tricks.sliding_window_view(rlag_padded, W)\n"
        "rc_win = np.lib.stride_tricks.sliding_window_view(rc_padded, W)\n"
        "mean_lag = np.nanmean(rlag_win, axis=1); mean_cur = np.nanmean(rc_win, axis=1)\n"
        "cov = np.nanmean((rlag_win - mean_lag[:, None]) * (rc_win - mean_cur[:, None]), axis=1)\n"
        "var_lag = np.nanmean((rlag_win - mean_lag[:, None])**2, axis=1)\n"
        "rho = np.where(var_lag > 0, cov / var_lag, 0.0)\n"
        "# Permanent shock = innovation (return minus predicted part)\n"
        "perm = rc - rho * r_lag\n"
        "base = np.cumsum(perm)\n"
    ),
    "adaptive_ewma": (
        "# Base: EWMA with externally supplied or self-computed volatility-adaptive alpha\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]\n"
        "p = np.cumsum(np.where(np.isfinite(r), r, 0.0))\n"
        "# If vol_adapted is missing, self-compute Parkinson vol ratio\n"
        "try:\n"
        "    _vol = vol_adapted\n"
        "except NameError:\n"
        "    br = ctx.col('bar_range_pips'); W = {{W}}\n"
        "    c = np.concatenate(([0.0], np.cumsum(br * br)))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W)\n"
        "    m = (k - lo).astype(float); ms = np.where(m > 0, m, 1.0)\n"
        "    parkinson = np.sqrt(np.clip((c[k] - c[lo]) / (ms * 4.0 * np.log(2.0)), 1e-12, None))\n"
        "    p_cum = np.cumsum(np.where(np.isfinite(parkinson), parkinson, 0.0))\n"
        "    p_cnt = np.cumsum(np.where(np.isfinite(parkinson), 1.0, 0.0))\n"
        "    _vol = parkinson / (p_cum / np.maximum(p_cnt, 1.0) + 1e-9)\n"
        "v_cum = np.cumsum(np.where(np.isfinite(_vol), _vol, 0.0))\n"
        "v_cnt = np.cumsum(np.where(np.isfinite(_vol), 1.0, 0.0))\n"
        "vol_ref = v_cum / np.maximum(v_cnt, 1.0)\n"
        "alpha_arr = np.clip({{alpha_min}} + ({{alpha_max}} - {{alpha_min}}) * np.clip(_vol / (vol_ref + 1e-9), 0, 1), {{alpha_min}}, {{alpha_max}})\n"
        "ew = np.empty(n); acc = p[0]\n"
        "for i in range(n):\n"
        "    acc = (1 - alpha_arr[i]) * acc + alpha_arr[i] * p[i]; ew[i] = acc\n"
        "base = ew\n"
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
        "r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips'); n = r.shape[0]\n"
        "# Informed flow proxy: large bars with same-direction persistence\n"
        "sign_r = np.sign(np.where(np.isfinite(r), r, 0.0))\n"
        "abs_r = np.abs(np.where(np.isfinite(r), r, 0.0))\n"
        "# Causal rolling 75th-percentile proxy (mean + 0.67*std of trailing window)\n"
        "W = {{W}}  # e.g. 100\n"
        "absr_padded = np.concatenate([np.full(W - 1, np.nan), abs_r])\n"
        "absr_win = np.lib.stride_tricks.sliding_window_view(absr_padded, W)\n"
        "q75_proxy = np.nanmean(absr_win, axis=1) + 0.67 * np.nanstd(absr_win, axis=1)\n"
        "informed = np.where(abs_r > q75_proxy, sign_r, 0.0)\n"
        "lambda_k = {{lambda_k}}  # e.g. 0.3\n"
        "correction = lambda_k * np.cumsum(informed)\n"
    ),
    "pin_flow": (
        "# Correction: Easley-O'Hara PIN-informed-flow proxy (1987/1992)\n"
        "r = ctx.col('vel_pips_h1'); br = ctx.col('bar_range_pips'); n = r.shape[0]\n"
        "vol = ctx.col('tick_volume')\n"
        "# Proxy: high-volume + large-range bars = more likely informed\n"
        "# Causal expanding mean/std\n"
        "vol_c = np.cumsum(np.where(np.isfinite(vol), vol, 0.0)); vol_n = np.cumsum(np.where(np.isfinite(vol), 1.0, 0.0))\n"
        "vol_m = vol_c / np.maximum(vol_n, 1.0)\n"
        "vol_sq = np.cumsum(np.where(np.isfinite(vol), vol*vol, 0.0))\n"
        "vol_s = np.sqrt(np.maximum(vol_sq / np.maximum(vol_n, 1.0) - vol_m**2, 0.0))\n"
        "vol_z = np.where(vol_s > 0, (vol - vol_m) / vol_s, np.zeros_like(vol))\n"
        "br_c = np.cumsum(np.where(np.isfinite(br), br, 0.0)); br_n = np.cumsum(np.where(np.isfinite(br), 1.0, 0.0))\n"
        "br_m = br_c / np.maximum(br_n, 1.0)\n"
        "br_sq = np.cumsum(np.where(np.isfinite(br), br*br, 0.0))\n"
        "br_s = np.sqrt(np.maximum(br_sq / np.maximum(br_n, 1.0) - br_m**2, 0.0))\n"
        "range_z = np.where(br_s > 0, (br - br_m) / br_s, np.zeros_like(br))\n"
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
        "r = ctx.col('vel_pips_h1'); sp = ctx.col('spread_pips'); n = sp.shape[0]\n"
        "# Tight spread = intense competition; wide spread = relaxed\n"
        "# Causal expanding mean/std\n"
        "sp_c = np.cumsum(np.where(np.isfinite(sp), sp, 0.0)); sp_n = np.cumsum(np.where(np.isfinite(sp), 1.0, 0.0))\n"
        "sp_m = sp_c / np.maximum(sp_n, 1.0)\n"
        "sp_sq = np.cumsum(np.where(np.isfinite(sp), sp*sp, 0.0))\n"
        "sp_s = np.sqrt(np.maximum(sp_sq / np.maximum(sp_n, 1.0) - sp_m**2, 0.0))\n"
        "sp_z = np.where(sp_s > 0, (sp - sp_m) / sp_s, np.zeros_like(sp))\n"
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
        "# Causal expanding mean\n"
        "d_cum = np.cumsum(np.where(np.isfinite(depth_ew), depth_ew, 0.0))\n"
        "d_cnt = np.cumsum(np.where(np.isfinite(depth_ew), 1.0, 0.0))\n"
        "d_mean = d_cum / np.maximum(d_cnt, 1.0)\n"
        "depth_change = depth_ew - d_mean\n"
        "correction = depth_change * {{scale}}  # scale ∈ {0.5, 1.0, 2.0}\n"
    ),
    "transitory_fade": (
        "# Correction: subtract transitory mean-reverting component (Hasbrouck 1993)\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]; W = {{W}}  # e.g. 100\n"
        "rc = np.where(np.isfinite(r), r, 0.0)\n"
        "r_lag = np.empty_like(rc); r_lag[0] = 0.0; r_lag[1:] = rc[:-1]\n"
        "# Rolling AR(1) coefficient on returns (causal)\n"
        "rlag_padded = np.concatenate([np.full(W - 1, np.nan), r_lag])\n"
        "rc_padded = np.concatenate([np.full(W - 1, np.nan), rc])\n"
        "rlag_win = np.lib.stride_tricks.sliding_window_view(rlag_padded, W)\n"
        "rc_win = np.lib.stride_tricks.sliding_window_view(rc_padded, W)\n"
        "mean_lag = np.nanmean(rlag_win, axis=1); mean_cur = np.nanmean(rc_win, axis=1)\n"
        "cov = np.nanmean((rlag_win - mean_lag[:, None]) * (rc_win - mean_cur[:, None]), axis=1)\n"
        "var_lag = np.nanmean((rlag_win - mean_lag[:, None])**2, axis=1)\n"
        "rho = np.where(var_lag > 0, cov / var_lag, 0.0)\n"
        "# Transitory deviation = cumulative predictable part\n"
        "trans = rho * r_lag\n"
        "correction = -np.cumsum(trans)\n"
    ),
    "error_correction": (
        "# Correction: subtract deviation from long-run trend (Engle-Granger error-correction)\n"
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
        "trend = intercept + beta * t\n"
        "# Error-correction: mean-revert toward trend\n"
        "deviation = p - trend\n"
        "speed = {{speed}}  # e.g. 0.1\n"
        "correction = -speed * deviation\n"
    ),
    "jump_replace": (
        "# Correction: bring jump bars back to local median (Bibinger 2024)\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]; W = {{W}}  # e.g. 20\n"
        "rc = np.where(np.isfinite(r), r, 0.0)\n"
        "p = np.cumsum(rc)\n"
        "# Local median level\n"
        "padded = np.concatenate([np.full(W - 1, np.nan), p])\n"
        "local_level = np.nanmedian(np.lib.stride_tricks.sliding_window_view(padded, W), axis=1)\n"
        "# Local spread (MAD)\n"
        "local_mad = np.nanmedian(np.abs(np.lib.stride_tricks.sliding_window_view(padded, W) - local_level[:, None]), axis=1)\n"
        "# Jump flag: deviation >> local MAD\n"
        "jump = np.abs(p - local_level) > {{k}} * local_mad  # k e.g. 3.0\n"
        "# Correction = shift jump bars toward local level\n"
        "correction = np.where(jump, local_level - p, 0.0)\n"
    ),
    "inventory_flow": (
        "# Correction: Evans-Lyons inventory/portfolio-shift flow (2002)\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]\n"
        "rc = np.where(np.isfinite(r), r, 0.0)\n"
        "# Inventory proxy: cumulative net signed flow\n"
        "inventory = np.cumsum(rc)\n"
        "lam = {{lam}}  # e.g. 0.001\n"
        "correction = lam * inventory\n"
    ),
    "amihud_illiquidity": (
        "# Correction: Amihud (2002) illiquidity — fade low-volume overshoots\n"
        "r = ctx.col('vel_pips_h1'); vol = ctx.col('tick_volume'); n = r.shape[0]\n"
        "rc = np.where(np.isfinite(r), r, 0.0)\n"
        "vc = np.maximum(np.where(np.isfinite(vol), vol, 0.0), 1.0)\n"
        "illiq = np.abs(rc) / vc\n"
        "csum = np.cumsum(illiq); cnt = np.arange(1, n + 1, dtype=float)\n"
        "mean = csum / cnt\n"
        "csq = np.cumsum(illiq * illiq)\n"
        "std = np.sqrt(np.maximum(csq / cnt - mean * mean, 0.0))\n"
        "illiq_z = np.where(std > 0, (illiq - mean) / std, 0.0)\n"
        "lam = {{lam}}  # e.g. 0.5\n"
        "correction = -lam * np.sign(rc) * np.maximum(illiq_z, 0.0)\n"
    ),
    "bouchaud_propagator": (
        "# Correction: Bouchaud et al. (2004) power-law transient-impact propagator\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]; W = {{W}}  # e.g. 50\n"
        "beta = {{beta}}  # power-law exponent, e.g. 0.5\n"
        "sgn = np.sign(np.where(np.isfinite(r), r, 0.0))\n"
        "kernel = 1.0 / np.power(1.0 + np.arange(W, dtype=float), beta)\n"
        "impact = np.convolve(sgn, kernel)[:n]  # causal: impact[i] uses past signs only\n"
        "correction = -{{lam}} * impact\n"
    ),
    "kyle_lambda_regression": (
        "# Correction: rolling Kyle (1985) lambda from return ~ signed-volume regression\n"
        "r = ctx.col('vel_pips_h1'); vol = ctx.col('tick_volume'); n = r.shape[0]; W = {{W}}  # e.g. 100\n"
        "rc = np.where(np.isfinite(r), r, 0.0); v = np.where(np.isfinite(vol), vol, 0.0)\n"
        "sv = np.sign(rc) * v\n"
        "rp = np.concatenate([np.full(W - 1, np.nan), rc])\n"
        "svp = np.concatenate([np.full(W - 1, np.nan), sv])\n"
        "rw = np.lib.stride_tricks.sliding_window_view(rp, W)\n"
        "svw = np.lib.stride_tricks.sliding_window_view(svp, W)\n"
        "mr = np.nanmean(rw, axis=1); msv = np.nanmean(svw, axis=1)\n"
        "cov = np.nanmean((rw - mr[:, None]) * (svw - msv[:, None]), axis=1)\n"
        "var = np.nanmean((svw - msv[:, None]) ** 2, axis=1)\n"
        "lam_k = np.where(var > 0, cov / var, 0.0)\n"
        "correction = -{{scale}} * lam_k * np.cumsum(sv)\n"
    ),
    "bns_bipower_jump": (
        "# Correction: Barndorff-Nielsen-Shephard bipower-variation jump detection\n"
        "r = ctx.col('vel_pips_h1'); n = r.shape[0]; W = {{W}}  # e.g. 50\n"
        "rc = np.where(np.isfinite(r), r, 0.0); absr = np.abs(rc)\n"
        "bp = absr * np.concatenate([[0.0], absr[:-1]])  # |r_i|*|r_{i-1}| (causal)\n"
        "bpp = np.concatenate([np.full(W - 1, np.nan), bp])\n"
        "bv = (np.pi / 2.0) * np.nanmean(np.lib.stride_tricks.sliding_window_view(bpp, W), axis=1)\n"
        "jump = (rc * rc) > {{k}} * np.maximum(bv, 1e-12)  # k e.g. 3.0\n"
        "correction = np.cumsum(np.where(jump, -rc, 0.0))\n"
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
        "# Detect large opening moves (weekend gap proxy) — causal expanding 95th pctile proxy\n"
        "abs_r = np.abs(np.where(np.isfinite(r), r, 0.0))\n"
        "cs = np.cumsum(abs_r); css = np.cumsum(abs_r * abs_r); cnt = np.cumsum(np.where(np.isfinite(r), 1.0, 0.0))\n"
        "thr = np.empty(n)\n"
        "for i in range(n):\n"
        "    m = max(cnt[i], 1.0); mu = cs[i] / m; va = css[i] / m - mu * mu; sigma = np.sqrt(np.clip(va, 0, None))\n"
        "    thr[i] = mu + 2.5 * sigma\n"
        "gap = np.where(np.abs(r) > thr, r, 0.0)\n"
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
        "vol_adapted = parkinson / (vol_ref + 1e-9)\n"
    ),
    "parkinson_vol_gate": (
        "# Vol-adapt: gate based on Parkinson vol vs reference\n"
        "br = ctx.col('bar_range_pips'); n = br.shape[0]; W = {{W}}  # e.g. 20\n"
        "c = np.concatenate(([0.0], np.cumsum(br * br)))\n"
        "k = np.arange(n); lo = np.maximum(0, k - W)\n"
        "m = (k - lo).astype(float); ms = np.where(m > 0, m, 1.0)\n"
        "parkinson = np.sqrt(np.clip((c[k] - c[lo]) / (ms * 4.0 * np.log(2.0)), 1e-12, None))\n"
        "# Causal expanding mean for reference\n"
        "p_cum = np.cumsum(np.where(np.isfinite(parkinson), parkinson, 0.0))\n"
        "p_cnt = np.cumsum(np.where(np.isfinite(parkinson), 1.0, 0.0))\n"
        "vol_ref = p_cum / np.maximum(p_cnt, 1.0)\n"
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
        "# Causal expanding mean for reference\n"
        "r_cum = np.cumsum(np.where(np.isfinite(rv), rv, 0.0))\n"
        "r_cnt = np.cumsum(np.where(np.isfinite(rv), 1.0, 0.0))\n"
        "rv_ref = r_cum / np.maximum(r_cnt, 1.0)\n"
        "vol_adapted = rv / rv_ref\n"
    ),
    "acd_intensity": (
        "# Vol-adapt: Engle-Russell ACD trade-intensity adaptation (tick arrival rate)\n"
        "tr = ctx.col('tick_rate_z'); n = tr.shape[0]\n"
        "trc = np.where(np.isfinite(tr), tr, 0.0)\n"
        "inten = np.empty(n); acc = trc[0]\n"
        "for i in range(n):\n"
        "    acc = 0.9 * acc + 0.1 * trc[i]; inten[i] = acc\n"
        "vol_adapted = np.exp(np.clip(inten, -3.0, 3.0))\n"
    ),
}

COMBINATION_OPERATORS: dict[str, str] = {
    "additive_blend": (
        "# Combine: weighted additive blend\n"
        "fair = {{w_base}} * base + {{w_corr}} * correction + {{w_cal}} * calendar\n"
    ),
    "multiplicative_gate": (
        "# Combine: multiplicative gate — correction scales the base\n"
        "# Causal expanding std of base\n"
        "n = base.shape[0]\n"
        "b_cum = np.cumsum(np.where(np.isfinite(base), base, 0.0))\n"
        "b_cnt = np.cumsum(np.where(np.isfinite(base), 1.0, 0.0))\n"
        "b_mean = b_cum / np.maximum(b_cnt, 1.0)\n"
        "b_sq = np.cumsum(np.where(np.isfinite(base), base*base, 0.0))\n"
        "b_std = np.sqrt(np.maximum(b_sq / np.maximum(b_cnt, 1.0) - b_mean**2, 0.0))\n"
        "fair = base * (1 + {{gain}} * correction / (b_std + 1e-9))\n"
    ),
    "conditional_switch": (
        "# Combine: conditional switch based on regime\n"
        "# If regime_signal is missing, default to always-false\n"
        "try:\n"
        "    regime = {{regime_signal}}\n"
        "except NameError:\n"
        "    regime = False\n"
        "fair = np.where(regime, base + correction, base)\n"
    ),
    "vol_adaptive_base": (
        "# Combine: vol-adaptive base selection\n"
        "# If vol_adapted is missing, compute self-contained proxy\n"
        "try:\n"
        "    _vol = vol_adapted\n"
        "except NameError:\n"
        "    r = ctx.col('vel_pips_h1'); n = r.shape[0]; W = {{W}}\n"
        "    abs_r = np.abs(np.where(np.isfinite(r), r, 0.0))\n"
        "    c = np.concatenate(([0.0], np.cumsum(abs_r * abs_r)))\n"
        "    k = np.arange(n); lo = np.maximum(0, k - W)\n"
        "    rv = np.sqrt(np.clip((c[k] - c[lo]) / np.maximum(k - lo, 1).astype(float), 0, None))\n"
        "    r_cum = np.cumsum(np.where(np.isfinite(rv), rv, 0.0))\n"
        "    r_cnt = np.cumsum(np.where(np.isfinite(rv), 1.0, 0.0))\n"
        "    _vol = rv / (r_cum / np.maximum(r_cnt, 1.0) + 1e-9)\n"
        "# If slow_base/fast_base are missing, fall back to base\n"
        "try:\n"
        "    _slow = slow_base\n"
        "except NameError:\n"
        "    _slow = base\n"
        "try:\n"
        "    _fast = fast_base\n"
        "except NameError:\n"
        "    _fast = base\n"
        "fair = np.where(_vol > {{threshold}}, _fast, _slow)\n"
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
    "price_level": ("base", "Raw cumulative price level (no smoothing)"),
    "permanent_extract": ("base", "Hasbrouck VAR permanent component (random-walk extraction)"),
    "adaptive_ewma": ("base", "EWMA with externally supplied vol-adaptive alpha (Taylor 2017)"),
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
    "transitory_fade": ("microstructure", "Subtract transitory AR(1) component (Hasbrouck 1993)"),
    "error_correction": ("microstructure", "Engle-Granger error-correction to trend"),
    "jump_replace": ("microstructure", "Jump detection + local median replacement (Bibinger 2024)"),
    "inventory_flow": ("microstructure", "Evans-Lyons cumulative inventory flow (2002)"),
    "amihud_illiquidity": ("microstructure", "Amihud (2002) illiquidity-adjusted fade of low-volume overshoots"),
    "bouchaud_propagator": ("microstructure", "Power-law transient-impact propagator (Bouchaud et al. 2004)"),
    "kyle_lambda_regression": ("microstructure", "Rolling Kyle lambda from return~signed-volume regression (Kyle 1985)"),
    "bns_bipower_jump": ("microstructure", "Bipower-variation jump detection (Barndorff-Nielsen-Shephard)"),
    "krohn_fix_adjusted": ("calendar", "Fix-window seasonal adjustment (Krohn et al. 2024)"),
    "hour_drift": ("calendar", "Hour-of-day drift correction"),
    "weekend_gap": ("calendar", "Weekend gap fade"),
    "taylor_adaptive_alpha": ("volatility", "Parkinson adaptive EWMA alpha (Taylor 2017)"),
    "parkinson_vol_gate": ("volatility", "Parkinson vol regime gate"),
    "realized_vol_gate": ("volatility", "Realized vol regime gate"),
    "acd_intensity": ("volatility", "Trade-intensity adaptive EWMA (Engle-Russell ACD)"),
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
        "    {{base}}\n"
        "    return base\n"
    ),
    "base_plus_correction": (
        "def estimate_fair(ctx):\n"
        "    {{base}}\n"
        "    {{correction}}\n"
        "    {{combination}}\n"
        "    return fair\n"
    ),
    "base_plus_correction_plus_calendar": (
        "def estimate_fair(ctx):\n"
        "    {{base}}\n"
        "    {{correction}}\n"
        "    {{calendar}}\n"
        "    {{combination}}\n"
        "    return fair\n"
    ),
    "vol_adaptive": (
        "def estimate_fair(ctx):\n"
        "    {{vol_adaptation}}\n"
        "    {{base}}\n"
        "    {{correction}}\n"
        "    {{combination}}\n"
        "    return fair\n"
    ),
    "dual_base_switch": (
        "def estimate_fair(ctx):\n"
        "    {{vol_adaptation}}\n"
        "    {{slow_base}}\n"
        "    {{fast_base}}\n"
        "    {{correction}}\n"
        "    {{combination}}\n"
        "    return fair\n"
    ),
    "vol_adaptive_calendar": (
        "def estimate_fair(ctx):\n"
        "    {{vol_adaptation}}\n"
        "    {{base}}\n"
        "    {{correction}}\n"
        "    {{calendar}}\n"
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


# ── Composition rendering ───────────────────────────────────────────────────

_ALL_OPERATORS = {
    **BASE_ESTIMATORS,
    **MICROSTRUCTURE_CORRECTIONS,
    **CALENDAR_CORRECTIONS,
    **VOLATILITY_ADAPTATIONS,
    **COMBINATION_OPERATORS,
}


def _auto_upgrade_skeleton(skeleton_name: str, operators: dict[str, str]) -> str:
    """Promote skeleton to the richest one that covers all operator slots.

    Richness hierarchy (most slots → least):
      dual_base_switch      : vol_adaptation, slow_base, fast_base, correction, combination
      vol_adaptive_calendar : vol_adaptation, base, correction, calendar, combination
      vol_adaptive          : vol_adaptation, base, correction, combination
      base_plus_correction_plus_calendar : base, correction, calendar, combination
      base_plus_correction  : base, correction, combination
      simple                : base
    """
    slots = set(operators.keys())
    has_slow_fast = "slow_base" in slots or "fast_base" in slots
    has_vol = "vol_adaptation" in slots
    has_cal = "calendar" in slots
    has_corr = "correction" in slots

    if has_slow_fast:
        return "dual_base_switch"
    if has_vol and has_cal:
        return "vol_adaptive_calendar"
    if has_vol:
        return "vol_adaptive"
    if has_cal:
        return "base_plus_correction_plus_calendar"
    if has_corr:
        return "base_plus_correction"
    return "simple"


def render_composition(
    skeleton_name: str,
    operators: dict[str, str],
    params: dict[str, float] | None = None,
) -> str:
    """Render a composition (skeleton + operators + params) into complete source code."""
    # Defensive: malformed LLM output may pass a list/string for operators
    if not isinstance(operators, dict):
        operators = {}
    # Auto-upgrade skeleton to richest one that covers all operator slots
    upgraded = _auto_upgrade_skeleton(skeleton_name, operators)
    skeleton = SKELETONS.get(upgraded, SKELETONS["simple"])
    params = params or {}

    # Handle dual_base_switch edge case: ensure both slow_base and fast_base are
    # present.  If base is present, copy it to missing slots.  If only one of
    # slow_base/fast_base is present, copy it to the other so the combination
    # operator never falls back to the 0.0 default.
    _ops = dict(operators)
    if upgraded == "dual_base_switch":
        if "base" in _ops:
            base_op = _ops.pop("base")
            if "slow_base" not in _ops:
                _ops["slow_base"] = base_op
            if "fast_base" not in _ops:
                _ops["fast_base"] = base_op
        if "slow_base" in _ops and "fast_base" not in _ops:
            _ops["fast_base"] = _ops["slow_base"]
        if "fast_base" in _ops and "slow_base" not in _ops:
            _ops["slow_base"] = _ops["fast_base"]
        operators = _ops

    # Collect operator code for each slot
    slot_code: dict[str, str] = {}
    for slot, op_name in operators.items():
        tmpl = _ALL_OPERATORS.get(op_name, "")
        if not tmpl:
            slot_code[slot] = f"    # (no {slot})"
            continue
        # Substitute params
        code = tmpl
        for param_name, val in params.items():
            code = code.replace(f"{{{{{param_name}}}}}", str(val))
        # Any remaining placeholders get a default value (best-effort)
        import re
        placeholders = set(re.findall(r"\{\{(\w+)\}\}", code))
        for ph in placeholders:
            # Numeric defaults
            if ph in ("alpha", "alpha_min", "alpha_max", "lambda", "lam", "mult", "scale", "w_base", "w_corr", "w_cal", "gain", "threshold", "reversion", "beta"):
                code = code.replace(f"{{{{{ph}}}}}", "0.5")
            elif ph in ("W",):
                code = code.replace(f"{{{{{ph}}}}}", "20")
            elif ph == "k":
                code = code.replace(f"{{{{{ph}}}}}", "3.0")
            elif ph == "regime_signal":
                code = code.replace(f"{{{{{ph}}}}}", "vol_adapted > 1.5")
            else:
                code = code.replace(f"{{{{{ph}}}}}", "0.0")
        code = textwrap.indent(code.strip(), "    ")
        # For dual_base_switch, base estimators assign to `base`; copy to slot name
        # so the combination operator can reference slow_base / fast_base distinctly.
        if upgraded == "dual_base_switch" and slot in ("slow_base", "fast_base"):
            code += f"\n    {slot} = base"
        slot_code[slot] = code

    # Build zero-default declarations for slots that aren't present or have no
    # valid template (so combination operators can safely reference e.g. `calendar`).
    defaults: list[str] = []
    for slot in ("base", "correction", "calendar", "vol_adaptation", "slow_base", "fast_base"):
        has_valid = slot in slot_code and not slot_code[slot].strip().startswith("#")
        if slot not in operators or not has_valid:
            defaults.append(f"    {slot} = 0.0")
    default_block = "\n".join(defaults)

    # Fill skeleton slots
    filled = skeleton
    for slot, code in slot_code.items():
        filled = filled.replace(f"{{{{{slot}}}}}", code)
    # Any unfilled slots become comments
    for slot in ("base", "correction", "calendar", "vol_adaptation", "combination", "slow_base", "fast_base"):
        filled = filled.replace(f"{{{{{slot}}}}}", f"    # (no {slot})")

    # Inject zero-defaults right after the function definition so they precede slot code
    if default_block:
        lines = filled.split("\n")
        for i, line in enumerate(lines):
            if line.strip().startswith("def estimate_fair"):
                lines.insert(i + 1, default_block)
                break
        filled = "\n".join(lines)

    return filled


# Convenience: full composition → source
Composition = dict  # {skeleton, operators, params}


def composition_to_source(comp: Composition) -> str:
    """Render a composition dict to source string."""
    return render_composition(
        comp.get("skeleton", "simple"),
        comp.get("operators", {}),
        comp.get("params"),
    )


def extract_concepts_from_composition(comp: Composition) -> list[str]:
    """Extract concept names from a composition dict."""
    return list(comp.get("operators", {}).values())

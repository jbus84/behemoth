"""Atomic concept library for cross-symbol residual scalping.

Decomposes a cross-sectional residual into 4 composable slots:
  1. Base residual      — loo_z, robust_z, all6_z, pairwise_median, graph_laplacian,
                          dispersion_rank, factor_resid, corr_weighted_graph
  2. Gate               — asia_session, high_dispersion, high_vol
  3. Smoothing          — ewma, trailing_mean
  4. Normalization      — vol_scale

Each operator is a small code template the LLM fills into a skeleton composition.
Missing optional slots (gate, smoothing, normalization) are auto-filled with
passthrough defaults so the rendered program is always valid.
"""
from __future__ import annotations

import textwrap

# ── Atomic operator templates ────────────────────────────────────────────────
# Each template is a snippet of Python that operates on ctx and assigns to a
# well-known variable that the next pipeline stage reads.

XS_BASE_OPERATORS: dict[str, str] = {
    "loo_z": (
        "# Base: leave-one-out basket z (target vs peer mean/std)\n"
        "t = ctx.target_col(); p = ctx.peers()\n"
        "raw = (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)"
    ),
    "robust_z": (
        "# Base: robust z using cross-sectional median / MAD\n"
        "r = ctx.r\n"
        "med = np.median(r, axis=1)\n"
        "mad = np.median(np.abs(r - med[:, None]), axis=1) + 1e-9\n"
        "raw = (ctx.target_col() - med) / (1.4826 * mad)"
    ),
    "all6_z": (
        "# Base: z-score against full cross-section mean/std\n"
        "r = ctx.r\n"
        "mu = r.mean(axis=1, keepdims=True)\n"
        "sd = r.std(axis=1, keepdims=True) + 1e-9\n"
        "z = (r - mu) / sd\n"
        "raw = z[:, ctx.target_idx]"
    ),
    "pairwise_median": (
        "# Base: median of target-minus-each-peer spreads\n"
        "raw = np.median(ctx.target_col()[:, None] - ctx.peers(), axis=1)"
    ),
    "graph_laplacian": (
        "# Base: fixed-cluster graph laplacian residual\n"
        "cl = {'EURUSD':0,'GBPUSD':0,'AUDUSD':0,'USDJPY':1,'USDCHF':1,'USDCAD':1}\n"
        "g = np.array([cl.get(n, 0) for n in ctx.names])\n"
        "ti = ctx.target_idx; same = (g == g[ti])\n"
        "same[ti] = False\n"
        "if same.sum() == 0:\n"
        "    nb = ctx.peers().mean(axis=1)\n"
        "else:\n"
        "    nb = ctx.r[:, same].mean(axis=1)\n"
        "raw = ctx.target_col() - nb"
    ),
    "dispersion_rank": (
        "# Base: ordinal dispersion rank extremity\n"
        "r = ctx.r; n, m = r.shape\n"
        "order = np.argsort(-r, axis=1, kind='stable')\n"
        "ranks = np.empty_like(order)\n"
        "rows = np.arange(n)[:, None]\n"
        "ranks[rows, order] = np.broadcast_to(np.arange(1, m + 1), order.shape)\n"
        "tr = ranks[:, ctx.target_idx].astype(float)\n"
        "mid = (m + 1) / 2.0\n"
        "raw = mid - tr"
    ),
    "factor_resid": (
        "# Base: causal rolling-OLS residual vs USD-basket mean\n"
        "r = ctx.r; n = r.shape[0]; ti = ctx.target_idx; W = 250\n"
        "basket = r.mean(axis=1); y = r[:, ti]\n"
        "k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "ms = np.where(m > 0, m, 1.0)\n"
        "cx = np.concatenate(([0.0], np.cumsum(basket)))\n"
        "cy = np.concatenate(([0.0], np.cumsum(y)))\n"
        "cxx = np.concatenate(([0.0], np.cumsum(basket * basket)))\n"
        "cxy = np.concatenate(([0.0], np.cumsum(basket * y)))\n"
        "sx = cx[k] - cx[lo]; sy = cy[k] - cy[lo]\n"
        "sxx = cxx[k] - cxx[lo]; sxy = cxy[k] - cxy[lo]\n"
        "Sxx = sxx - sx * sx / ms\n"
        "Sxy = sxy - sx * sy / ms\n"
        "beta = np.where(np.abs(Sxx) > 1e-12, Sxy / Sxx, np.nan)\n"
        "raw = y - beta * basket\n"
        "raw[m < 20] = np.nan"
    ),
    "corr_weighted_graph": (
        "# Base: causal rolling Pearson-weighted peer residual\n"
        "r = ctx.r; n = r.shape[0]; ti = ctx.target_idx; W = 250\n"
        "pidx = ctx.peer_idx\n"
        "x = r[:, ti]; P = r[:, pidx]\n"
        "k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "ms = np.where(m > 0, m, 1.0)[:, None]\n"
        "z = np.zeros((1, P.shape[1]))\n"
        "cx = np.concatenate(([0.0], np.cumsum(x)))\n"
        "cxx = np.concatenate(([0.0], np.cumsum(x * x)))\n"
        "cP = np.vstack((z, np.cumsum(P, axis=0)))\n"
        "cPP = np.vstack((z, np.cumsum(P * P, axis=0)))\n"
        "cXP = np.vstack((z, np.cumsum(P * x[:, None], axis=0)))\n"
        "sx = (cx[k] - cx[lo])[:, None]; sxx = (cxx[k] - cxx[lo])[:, None]\n"
        "sP = cP[k] - cP[lo]; sPP = cPP[k] - cPP[lo]; sXP = cXP[k] - cXP[lo]\n"
        "Sxx = sxx - sx * sx / ms\n"
        "Spp = sPP - sP * sP / ms\n"
        "Sxp = sXP - sx * sP / ms\n"
        "denom = np.sqrt(np.clip(Sxx * Spp, 0.0, None))\n"
        "w = np.where(denom > 1e-12, Sxp / denom, 0.0)\n"
        "sw = np.abs(w).sum(axis=1, keepdims=True)\n"
        "w = np.where(sw > 1e-9, w / sw, 0.0)\n"
        "raw = x - (w * P).sum(axis=1)\n"
        "raw[(m < 20) | (sw[:, 0] <= 1e-9)] = np.nan"
    ),
    "participation_ratio": (
        "# Base: participation ratio (target share of total cross-sectional variance)\n"
        "r = ctx.r; t = ctx.target_col(); p = ctx.peers()\n"
        "z = (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)\n"
        "total_var = np.sum(r * r, axis=1)\n"
        "target_var = t * t\n"
        "participation = target_var / (total_var + 1e-9)\n"
        "raw = z * participation"
    ),
    "dispersion_change": (
        "# Base: dispersion-change weighted residual\n"
        "d = ctx.dispersion()\n"
        "d_csum = np.cumsum(np.where(np.isfinite(d), d, 0.0))\n"
        "d_ccnt = np.cumsum(np.where(np.isfinite(d), 1.0, 0.0))\n"
        "d_mean = d_csum / np.maximum(d_ccnt, 1.0)\n"
        "t = ctx.target_col(); p = ctx.peers()\n"
        "z = (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)\n"
        "raw = z * (d / (d_mean + 1e-9))"
    ),
    "covariance_aware_z": (
        "# Base: Mahalanobis-style residual (causal rolling cov-aware)\n"
        "r = ctx.r; n = r.shape[0]; ti = ctx.target_idx; W = 250\n"
        "x = r[:, ti]; p = r[:, ctx.peer_idx].mean(axis=1)\n"
        "k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "ms = np.where(m > 0, m, 1.0)\n"
        "cx = np.concatenate(([0.0], np.cumsum(x)))\n"
        "cp = np.concatenate(([0.0], np.cumsum(p)))\n"
        "cxx = np.concatenate(([0.0], np.cumsum(x * x)))\n"
        "cpp = np.concatenate(([0.0], np.cumsum(p * p)))\n"
        "cxp = np.concatenate(([0.0], np.cumsum(x * p)))\n"
        "sx = cx[k] - cx[lo]; sp = cp[k] - cp[lo]\n"
        "sxx = cxx[k] - cxx[lo]; spp = cpp[k] - cpp[lo]; sxp = cxp[k] - cxp[lo]\n"
        "Sxx = sxx - sx * sx / ms\n"
        "Spp = spp - sp * sp / ms\n"
        "Sxp = sxp - sx * sp / ms\n"
        "var_diff = Sxx + Spp - 2.0 * Sxp\n"
        "mahal = np.sqrt(np.maximum(var_diff, 0.0))\n"
        "raw = (x - p) / (mahal + 1e-9)\n"
        "raw[m < 20] = np.nan"
    ),
    "rank_transition": (
        "# Base: rank-transition reversion (fade extremity by distance from centre)\n"
        "r = ctx.r; n, m = r.shape\n"
        "order = np.argsort(-r, axis=1, kind='stable')\n"
        "ranks = np.empty_like(order)\n"
        "rows = np.arange(n)[:, None]\n"
        "ranks[rows, order] = np.broadcast_to(np.arange(1, m + 1), order.shape)\n"
        "tr = ranks[:, ctx.target_idx].astype(float)\n"
        "mid = (m + 1) / 2.0\n"
        "dist = tr - mid\n"
        "raw = -np.sign(dist) * np.abs(dist)"
    ),
    "residual_directional": (
        "# Base: hybrid residual × directional alignment\n"
        "r = ctx.r\n"
        "basket = r.mean(axis=1)\n"
        "t = ctx.target_col(); p = ctx.peers()\n"
        "z = (t - p.mean(axis=1)) / (p.std(axis=1) + 1e-9)\n"
        "alignment = np.sign(z) * np.sign(basket)\n"
        "alpha = {{alpha}}  # e.g. 0.3\n"
        "raw = z * (1.0 - alpha * alignment)"
    ),
}

XS_GATE_OPERATORS: dict[str, str] = {
    "asia_session": (
        "# Gate: Asia session only (UTC hour 0-5)\n"
        "mask = (ctx.hour <= 5) if ctx.hour is not None else np.ones(n, dtype=bool)"
    ),
    "high_dispersion": (
        "# Gate: only when cross-sectional dispersion >= its causal expanding mean\n"
        "d = ctx.dispersion()\n"
        "csum = np.cumsum(np.where(np.isfinite(d), d, 0.0))\n"
        "ccnt = np.cumsum(np.where(np.isfinite(d), 1.0, 0.0))\n"
        "expanding_mean = csum / np.maximum(ccnt, 1.0)\n"
        "mask = d >= expanding_mean"
    ),
    "high_vol": (
        "# Gate: only when |target return| >= its causal expanding mean\n"
        "t = ctx.target_col()\n"
        "abs_t = np.abs(np.where(np.isfinite(t), t, 0.0))\n"
        "csum = np.cumsum(abs_t)\n"
        "ccnt = np.cumsum(np.where(np.isfinite(abs_t), 1.0, 0.0))\n"
        "expanding_mean = csum / np.maximum(ccnt, 1.0)\n"
        "mask = abs_t >= expanding_mean"
    ),
    "low_correlation": (
        "# Gate: only when mean abs target-peer correlation is below expanding mean\n"
        "r = ctx.r; n = r.shape[0]; ti = ctx.target_idx; W = 250\n"
        "pidx = ctx.peer_idx\n"
        "x = r[:, ti]; P = r[:, pidx]\n"
        "k = np.arange(n); lo = np.maximum(0, k - W); m = (k - lo).astype(float)\n"
        "ms = np.where(m > 0, m, 1.0)[:, None]\n"
        "z = np.zeros((1, P.shape[1]))\n"
        "cx = np.concatenate(([0.0], np.cumsum(x)))\n"
        "cxx = np.concatenate(([0.0], np.cumsum(x * x)))\n"
        "cP = np.vstack((z, np.cumsum(P, axis=0)))\n"
        "cPP = np.vstack((z, np.cumsum(P * P, axis=0)))\n"
        "cXP = np.vstack((z, np.cumsum(P * x[:, None], axis=0)))\n"
        "sx = (cx[k] - cx[lo])[:, None]; sxx = (cxx[k] - cxx[lo])[:, None]\n"
        "sP = cP[k] - cP[lo]; sPP = cPP[k] - cPP[lo]; sXP = cXP[k] - cXP[lo]\n"
        "Sxx = sxx - sx * sx / ms\n"
        "Spp = sPP - sP * sP / ms\n"
        "Sxp = sXP - sx * sP / ms\n"
        "denom = np.sqrt(np.clip(Sxx * Spp, 0.0, None))\n"
        "corr = np.where(denom > 1e-12, Sxp / denom, 0.0)\n"
        "mean_abs_corr = np.abs(corr).mean(axis=1)\n"
        "csum = np.cumsum(np.where(np.isfinite(mean_abs_corr), mean_abs_corr, 0.0))\n"
        "ccnt = np.cumsum(np.where(np.isfinite(mean_abs_corr), 1.0, 0.0))\n"
        "expanding_mean = csum / np.maximum(ccnt, 1.0)\n"
        "mask = mean_abs_corr < expanding_mean"
    ),
}

XS_SMOOTHING_OPERATORS: dict[str, str] = {
    "ewma": (
        "# Smoothing: causal EWMA\n"
        "alpha = {{alpha}}  # e.g. 0.10\n"
        "smoothed = np.empty(n)\n"
        "acc = 0.0\n"
        "for i in range(n):\n"
        "    if np.isfinite(raw[i]):\n"
        "        acc = (1 - alpha) * acc + alpha * raw[i]\n"
        "    smoothed[i] = acc"
    ),
    "trailing_mean": (
        "# Smoothing: causal trailing-window mean\n"
        "W = {{W}}  # e.g. 20\n"
        "csum = np.concatenate(([0.0], np.cumsum(np.where(np.isfinite(raw), raw, 0.0))))\n"
        "ccnt = np.concatenate(([0.0], np.cumsum(np.where(np.isfinite(raw), 1.0, 0.0))))\n"
        "k = np.arange(n) + 1\n"
        "lo = np.maximum(0, k - W)\n"
        "window_sum = csum[k] - csum[lo]\n"
        "window_cnt = ccnt[k] - ccnt[lo]\n"
        "smoothed = np.where(window_cnt > 0, window_sum / window_cnt, 0.0)"
    ),
}

XS_NORMALIZATION_OPERATORS: dict[str, str] = {
    "vol_scale": (
        "# Normalization: causal trailing-window std scaling\n"
        "W = {{W}}  # e.g. 20\n"
        "csum = np.concatenate(([0.0], np.cumsum(np.where(np.isfinite(smoothed), smoothed, 0.0))))\n"
        "ccnt = np.concatenate(([0.0], np.cumsum(np.where(np.isfinite(smoothed), 1.0, 0.0))))\n"
        "csq = np.concatenate(([0.0], np.cumsum(np.where(np.isfinite(smoothed), smoothed * smoothed, 0.0))))\n"
        "k = np.arange(n) + 1\n"
        "lo = np.maximum(0, k - W)\n"
        "m = ccnt[k] - ccnt[lo]\n"
        "ms = np.where(m > 0, m, 1.0)\n"
        "s = csum[k] - csum[lo]\n"
        "sq = csq[k] - csq[lo]\n"
        "mean = s / ms\n"
        "std = np.sqrt(np.maximum(sq / ms - mean * mean, 0.0))\n"
        "normalized = np.where(std > 0, smoothed / (std + 1e-9), 0.0)"
    ),
    "proportional_dispersion": (
        "# Normalization: scale by dispersion relative to its expanding mean\n"
        "d = ctx.dispersion()\n"
        "d_csum = np.cumsum(np.where(np.isfinite(d), d, 0.0))\n"
        "d_ccnt = np.cumsum(np.where(np.isfinite(d), 1.0, 0.0))\n"
        "d_mean = d_csum / np.maximum(d_ccnt, 1.0)\n"
        "scale = d / (d_mean + 1e-9)\n"
        "normalized = smoothed * scale"
    ),
}

# Default code injected when an optional slot is missing or invalid.
_SLOT_DEFAULTS: dict[str, str] = {
    "base": "    # (no base)\n    raw = np.zeros(n)",
    "smoothing": "    # Smoothing: none (passthrough)\n    smoothed = raw",
    "normalization": "    # Normalization: none (passthrough)\n    normalized = smoothed",
    "gate": "    # Gate: pass-through (no gating)\n    mask = np.ones(n, dtype=bool)",
}

# ── Concept taxonomy for branch tracking ─────────────────────────────────────
XS_CONCEPT_TAXONOMY: dict[str, tuple[str, str]] = {
    # (category, description)
    "loo_z": ("base", "Leave-one-out basket z (target vs peer mean/std)"),
    "robust_z": ("base", "Robust z using cross-sectional median / MAD"),
    "all6_z": ("base", "Z-score against full cross-section mean/std"),
    "pairwise_median": ("base", "Median of target-minus-each-peer spreads"),
    "graph_laplacian": ("base", "Fixed-cluster graph laplacian residual"),
    "dispersion_rank": ("base", "Ordinal dispersion rank extremity"),
    "factor_resid": ("base", "Causal rolling-OLS residual vs USD-basket mean"),
    "corr_weighted_graph": ("base", "Causal rolling Pearson-weighted peer residual"),
    "participation_ratio": ("base", "Residual weighted by target's share of total variance"),
    "dispersion_change": ("base", "Residual scaled by dispersion relative to expanding mean"),
    "covariance_aware_z": ("base", "Mahalanobis-style residual with causal rolling cov"),
    "rank_transition": ("base", "Fade extremity by distance from cross-sectional centre"),
    "residual_directional": ("base", "Hybrid residual × USD-basket directional alignment"),
    "asia_session": ("gate", "Asia session only (UTC hour 0-5)"),
    "high_dispersion": ("gate", "Gate to bars where dispersion >= expanding mean"),
    "high_vol": ("gate", "Gate to bars where |target return| >= expanding mean"),
    "low_correlation": ("gate", "Gate to bars where target-peer correlation is below mean"),
    "ewma": ("smoothing", "Causal EWMA smoothing"),
    "trailing_mean": ("smoothing", "Causal trailing-window mean smoothing"),
    "vol_scale": ("normalization", "Causal trailing-window std scaling"),
    "proportional_dispersion": ("normalization", "Scale by dispersion relative to expanding mean"),
}

# ── Skeleton compositions ──────────────────────────────────────────────────
XS_SKELETONS: dict[str, str] = {
    "xs_residual": (
        "def residual(ctx):\n"
        "    r = ctx.r\n"
        "    n = r.shape[0]\n"
        "    {{base}}\n"
        "    {{smoothing}}\n"
        "    {{normalization}}\n"
        "    {{gate}}\n"
        "    return np.where(mask, normalized, np.nan)\n"
    ),
}

# ── Internal operator registry ─────────────────────────────────────────────
_ALL_XS_OPERATORS: dict[str, str] = {
    **XS_BASE_OPERATORS,
    **XS_GATE_OPERATORS,
    **XS_SMOOTHING_OPERATORS,
    **XS_NORMALIZATION_OPERATORS,
}

# Mapping from concept category to skeleton slot name
_CATEGORY_TO_SLOT: dict[str, str] = {
    "base": "base",
    "gate": "gate",
    "smoothing": "smoothing",
    "normalization": "normalization",
}


# ── Composition rendering ──────────────────────────────────────────────────


def _default_params_for_placeholder(ph: str) -> str:
    """Best-effort default values for numeric placeholders."""
    if ph in ("alpha", "alpha_min", "alpha_max", "lam", "mult", "scale",
              "w_base", "w_corr", "w_cal", "gain", "gamma", "threshold",
              "reversion", "beta"):
        return "0.5"
    if ph == "W":
        return "20"
    if ph == "k":
        return "3.0"
    if ph == "regime_signal":
        return "vol_adapted > 1.5"
    return "0.0"


def render_composition(
    skeleton_name: str,
    operators: dict[str, str],
    params: dict[str, float] | None = None,
) -> str:
    """Render a composition (skeleton + operators + params) into complete source code."""
    if not isinstance(operators, dict):
        operators = {}
    skeleton = XS_SKELETONS.get(skeleton_name, XS_SKELETONS["xs_residual"])
    params = params or {}
    if not isinstance(params, dict):
        params = {}

    # Build slot code from explicitly requested operators
    slot_code: dict[str, str] = {}
    for slot, op_name in operators.items():
        tmpl = _ALL_XS_OPERATORS.get(op_name, "") if isinstance(op_name, str) else ""
        if not tmpl:
            continue
        code = tmpl
        for param_name, val in params.items():
            code = code.replace(f"{{{{{param_name}}}}}", str(val))
        # Fill any remaining placeholders with defaults
        import re

        placeholders = set(re.findall(r"\{\{(\w+)\}\}", code))
        for ph in placeholders:
            code = code.replace(f"{{{{{ph}}}}}", _default_params_for_placeholder(ph))
        code = textwrap.indent(code.strip(), "    ")
        slot_code[slot] = code

    # Fill missing slots with defaults
    for slot, default_code in _SLOT_DEFAULTS.items():
        if slot not in slot_code:
            slot_code[slot] = default_code

    # Fill skeleton slots
    filled = skeleton
    for slot, code in slot_code.items():
        filled = filled.replace(f"{{{{{slot}}}}}", code)

    return filled


Composition = dict  # {skeleton, operators, params}


def composition_to_source(comp: Composition) -> str:
    """Render a composition dict to source string."""
    return render_composition(
        comp.get("skeleton", "xs_residual"),
        comp.get("operators", {}),
        comp.get("params"),
    )


def extract_concepts_from_composition(comp: Composition) -> list[str]:
    """Extract concept names from a composition dict."""
    return list(comp.get("operators", {}).values())


# ── Seed compositions mirroring the existing cross-symbol seeds ─────────────
XS_SEED_COMPOSITIONS: dict[str, Composition] = {
    "loo_z": {
        "skeleton": "xs_residual",
        "operators": {"base": "loo_z"},
        "params": {},
    },
    "robust_z": {
        "skeleton": "xs_residual",
        "operators": {"base": "robust_z"},
        "params": {},
    },
    "all6_z": {
        "skeleton": "xs_residual",
        "operators": {"base": "all6_z"},
        "params": {},
    },
    "graph_laplacian": {
        "skeleton": "xs_residual",
        "operators": {"base": "graph_laplacian"},
        "params": {},
    },
    "dispersion_rank": {
        "skeleton": "xs_residual",
        "operators": {"base": "dispersion_rank"},
        "params": {},
    },
    "pairwise_median": {
        "skeleton": "xs_residual",
        "operators": {"base": "pairwise_median"},
        "params": {},
    },
    "loo_z_asia": {
        "skeleton": "xs_residual",
        "operators": {"base": "loo_z", "gate": "asia_session"},
        "params": {},
    },
    "loo_z_highdisp": {
        "skeleton": "xs_residual",
        "operators": {"base": "loo_z", "gate": "high_dispersion"},
        "params": {},
    },
    "factor_resid": {
        "skeleton": "xs_residual",
        "operators": {"base": "factor_resid"},
        "params": {},
    },
    "corr_weighted_graph": {
        "skeleton": "xs_residual",
        "operators": {"base": "corr_weighted_graph"},
        "params": {},
    },
    "participation_ratio": {
        "skeleton": "xs_residual",
        "operators": {"base": "participation_ratio"},
        "params": {},
    },
    "dispersion_change": {
        "skeleton": "xs_residual",
        "operators": {"base": "dispersion_change"},
        "params": {},
    },
    "covariance_aware_z": {
        "skeleton": "xs_residual",
        "operators": {"base": "covariance_aware_z"},
        "params": {},
    },
    "rank_transition": {
        "skeleton": "xs_residual",
        "operators": {"base": "rank_transition"},
        "params": {},
    },
    "residual_directional": {
        "skeleton": "xs_residual",
        "operators": {"base": "residual_directional"},
        "params": {},
    },
}

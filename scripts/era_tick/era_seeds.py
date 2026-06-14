"""Seed programs + writer rules for the ERA tick-momentum search.

Each seed is a self-contained `signal(ctx) -> np.ndarray[n_ticks]` (no imports; `np` is provided
by the sandbox). Sign = trade direction, magnitude = conviction (the executor enters the top-q
|conviction| in the DRIFT regime and rides). The five seeds span distinct momentum branches so
the diversity-PUCT search starts from genuinely different ideas, not five tweaks of one.
"""

from __future__ import annotations

SEED_PROGRAMS: dict[str, str] = {
    # 1. Confident-momentum baseline: the Kalman drift t-stat is the conviction.
    "drift_t": "def signal(ctx):\n    return ctx.col('drift_t')\n",
    # 2. Drift direction, conviction = trend quality (efficiency ratio).
    "drift_eff": (
        "def signal(ctx):\n"
        "    r = ctx.col('drift_hat'); e = ctx.col('eff_ratio')\n"
        "    return np.sign(r) * e\n"
    ),
    # 3. Residual continuation: a price extension away from the filter keeps going.
    "residual_cont": "def signal(ctx):\n    return ctx.col('residual_z')\n",
    # 4. Amplitude focus: drift t-stat scaled by elevated realized range.
    "drift_range": (
        "def signal(ctx):\n"
        "    dt = ctx.col('drift_t'); rz = ctx.col('range_z')\n"
        "    return dt * np.clip(rz, 0.0, None)\n"
    ),
    # 5. Acceleration-confirmed momentum: drift and its change agree in sign.
    "accel_confirm": (
        "def signal(ctx):\n"
        "    r = ctx.col('drift_hat'); a = ctx.col('accel'); c = ctx.col('drift_t')\n"
        "    return np.where(np.sign(r) == np.sign(a), c, 0.0)\n"
    ),
}

BRANCH_TAGS: dict[str, str] = {name: name for name in SEED_PROGRAMS}

IDEAS: list[str] = [
    "Gate entries to only the most confident trend states (combine drift_t with eff_ratio).",
    "Scale conviction by realized-range so bigger-amplitude moves dominate (use range_z, rvol_fast).",
    "Require acceleration (accel) to agree with drift before committing.",
    "Down-weight high-spread / low-activity ticks (spread_pips, tick_rate) where cost eats the edge.",
    "Use residual_z as a continuation kicker on top of drift_t rather than fading it.",
]

TICK_RULES = (
    "You write a Python function `signal(ctx) -> np.ndarray` of length ctx.n_bars.\n"
    "Output = per-tick CONVICTION: sign = trade direction (positive=long, negative=short),\n"
    "magnitude = confidence. The executor enters the top-|q| conviction ticks while the tape\n"
    "is in the DRIFT (trending) regime and rides with hysteresis exits, so your job is the\n"
    "ENTRY signal — make it large and correctly-signed when a real continuation is underway,\n"
    "and ~0 otherwise. You MAY return 0.0 (or np.nan) for ticks you do not want to trade.\n"
    "ctx.col(name) returns a causal per-tick column. Available columns:\n"
    "  drift_hat   - Kalman velocity (price/sec); sign = current micro-trend\n"
    "  drift_t     - drift_hat / std(drift): the filter's t-stat confidence in the trend\n"
    "  residual_z  - (mid - mid_hat) in innovation std: >0 extended up, <0 extended down\n"
    "  regime_code - 0 warmup,1 shock,2 DRIFT,3 revert,4 churn\n"
    "  spread_pips - current spread (cost driver); avoid trading when high\n"
    "  accel       - change in drift over ~10 ticks (lagged); momentum acceleration\n"
    "  rvol_fast / rvol_slow - rolling realized vol (pips), short/long window\n"
    "  eff_ratio   - Kaufman efficiency ratio 0..1 (1 = clean trend, 0 = chop)\n"
    "  range_z     - z-score of current realized range vs its baseline (activity)\n"
    "  tick_rate   - EWMA ticks/sec (liquidity/activity)\n"
    "  hour        - UTC hour\n"
    "`np` is available. You CANNOT import anything and CANNOT read future rows: signal[k]\n"
    "must depend ONLY on bars <= k (use trailing/EWMA ops, no centered windows, no full-split\n"
    "mean/std). A causality probe perturbs future rows and REJECTS leaky programs.\n"
    "Output ONLY one ```python code block.\n"
)

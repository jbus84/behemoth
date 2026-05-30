from __future__ import annotations

FEATURE_NAMES: list[str] = [
    "spread_pips", "spread_z", "tick_volume", "tick_rate_hz", "tick_rate_z",
    "tick_burst", "tick_burst_score", "high_pos_tick", "low_pos_tick",
    "hl_pos_delta_tick", "bar_return_sign", "vel_pips_h1", "vel_pips_h2",
    "vel_pips_h5", "vel_pips_h10", "vel_z_h1", "vel_z_h2", "vel_z_h5",
    "vel_z_h10", "accel_pips", "hour_utc",
]

SCALP_RULES = (
    "You write a Python function `signal(ctx) -> np.ndarray` for 100-tick FX scalping.\n"
    "It returns a per-bar DIRECTIONAL score: sign = predicted direction of the next move,\n"
    "magnitude = conviction. The harness scales it (MAD), trades side=sign(signal) when\n"
    "|scaled| >= threshold, and scores net = side*y_fwd - cost. Return np.nan for bars you\n"
    "DO NOT want to trade (self-gating).\n"
    "ctx.col(name) returns a causal per-bar feature column; ctx.X is (n_bars x n_feat);\n"
    "ctx.n_bars; ctx.hour is the per-bar UTC hour. `np` is available. NO imports.\n"
    "Available causal features (all backward / as-of, NEVER forward):\n"
    f"  {', '.join(FEATURE_NAMES)}\n"
    "You CANNOT access y_fwd / cost / future bars. You MAY use the full time axis causally:\n"
    "trailing/expanding windows, EWMA, rolling stats over bars <= k ONLY (use x[k-W:k], not\n"
    "x[k:], no centered windows, no full-sample mean/std). A causality probe perturbs future\n"
    "rows and REJECTS any program whose past output changes.\n"
    "Mechanisms to consider: order-flow imbalance (signed flow -> continuation), Ornstein-\n"
    "Uhlenbeck s-score reversion (fade trailing-equilibrium deviation), Hawkes bursts\n"
    "(EWMA tick intensity gating continuation), multi-horizon momentum, spread/vol regime\n"
    "gates.\n"
    "PERFORMANCE: the scoring split has up to ~50k bars and your program is run 3x (a\n"
    "causality check re-runs it). PREFER vectorised numpy — rolling windows via cumulative\n"
    "sums (np.cumsum), not per-bar Python loops over bars. A single O(n) pass (e.g. an EWMA\n"
    "loop) is fine, but a per-bar inner WINDOW loop (O(n*W)) may exceed the 10s limit and be\n"
    "REJECTED with no score. Output ONLY one ```python code block.\n"
)

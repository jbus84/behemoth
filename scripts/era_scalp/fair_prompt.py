from __future__ import annotations

from scripts.era_scalp.load_splits import WHITELIST

FAIR_FEATURE_NAMES: list[str] = list(WHITELIST)

FAIR_RULES = (
    "You write `fair(ctx) -> np.ndarray` for 100-tick FX fair-price estimation.\n"
    "Return a per-bar predicted MISPRICING (fair - mid) in PIPS: sign = the direction mid is\n"
    "mispriced (positive => mid is BELOW fair => fair is higher), magnitude = how far. np.nan\n"
    "= abstain on that bar. You are NOT predicting the next tick; you estimate the deviation of\n"
    "the current mid from the efficient (fair) price, which is scored by its correlation with\n"
    "the realized de-noised future move over thousands of bars.\n"
    "LEVEL-FREE: you never see an absolute price. Use the RETURN series (vel_pips_h1, pips) and\n"
    "microstructure features. To denoise/anchor, build a RELATIVE path p = np.cumsum(vel_pips_h1)\n"
    "and subtract its own EWMA / trailing-mean (the origin cancels). `np` is available, NO imports.\n"
    "ctx.col(name) gives a causal per-bar feature; ctx.X is (n_bars x n_feat); ctx.n_bars; ctx.hour.\n"
    "Causal features (all backward/as-of, NEVER forward):\n"
    f"  {', '.join(FAIR_FEATURE_NAMES)}\n"
    "Use the time axis causally (trailing/expanding/EWMA over bars <= k only; never x[k:], no\n"
    "centered windows, no full-sample stats). A causality probe perturbs future rows and REJECTS\n"
    "any program whose past output changes.\n"
    "Ingredients (recent literature): EWMA/efficient-price denoising (Hasbrouck), bid-ask bounce\n"
    "reversal (Roll), micro-price imbalance tilt (Stoikov), trailing anchor, order-flow tilt\n"
    "(persistent vs transient). The best estimator usually BLENDS denoising + imbalance + bounce.\n"
    "PERFORMANCE: ~50k bars, run 3x; prefer vectorised cumsum windows over per-bar loops (a single\n"
    "O(n) EWMA pass is fine); >10s is REJECTED. Output ONLY one ```python code block.\n"
)

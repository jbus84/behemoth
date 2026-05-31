from __future__ import annotations

from scripts.era_scalp.load_splits import WHITELIST

FADE_FEATURE_NAMES: list[str] = list(WHITELIST)

FADE_RULES = (
    "You write `signal(ctx) -> np.ndarray` for a 100-tick fair-value FADE strategy.\n"
    "Return a per-bar SIGNED fade conviction: positive => mid is BELOW fair => go LONG toward fair;\n"
    "negative => SHORT; magnitude => conviction. np.nan => ABSTAIN on that bar. The harness trades\n"
    "the top-quantile |conviction| bars (side = sign), exits after a fixed horizon, and scores\n"
    "net-of-cost PnL POOLED across all major pairs at once.\n"
    "The edge: fading the fair-mispricing only pays when the market MEAN-REVERTS. So your job is to\n"
    "(a) estimate the mispricing (fair - mid) level-free, and (b) ABSTAIN (np.nan) when the market\n"
    "is trending / not reverting. A signal that trades everywhere loses on trending symbols.\n"
    "LEVEL-FREE: no absolute price. Build a relative path p = np.cumsum(vel_pips_h1) and denoise it\n"
    "(EWMA / trailing mean) for the fair estimate; use microstructure for tilt. `np` available, NO imports.\n"
    "ctx.col(name) = causal per-bar feature; ctx.X (n_bars x n_feat); ctx.n_bars; ctx.hour.\n"
    "Causal features (all backward, NEVER forward):\n"
    f"  {', '.join(FADE_FEATURE_NAMES)}\n"
    "Use the time axis causally (trailing/expanding/EWMA over bars <= k; never x[k:], no full-sample\n"
    "stats). A causality probe perturbs future rows and REJECTS any program whose past output changes.\n"
    "Mean-reversion gates to consider: trailing variance-ratio < 1 (Lo-MacKinlay), negative lag-1\n"
    "return autocorrelation, low Kaufman efficiency ratio (choppy not trending), short OU half-life;\n"
    "and only fade EXTREME dislocations (|fair-mid| in its trailing tail). Best programs COMBINE a\n"
    "mean-reversion gate with an extreme-dislocation filter.\n"
    "KEEP IT CONCISE (<= ~40 lines); short causal blends generalise, long tunable ones overfit.\n"
    ">10s is REJECTED. Output ONLY one ```python code block.\n"
)

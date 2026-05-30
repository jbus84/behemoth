from __future__ import annotations

from scripts.era_scalp.load_splits import WHITELIST

DEPLOY_FEATURE_NAMES: list[str] = list(WHITELIST)

RANGE_RULES = (
    "You write `deploy(ctx) -> np.ndarray` for direction-agnostic 100-tick range scalping.\n"
    "Return a per-bar NON-DIRECTIONAL score: HIGH = 'a two-sided maker bracket is worth\n"
    "deploying at this bar', and np.nan = stand aside. You do NOT predict a direction -\n"
    "the harness rests BOTH a buy limit below and a sell limit above; whichever the market\n"
    "hits first sets the side, and it takes profit back at the center. Your only job is to\n"
    "detect WHEN the next window is range-bound and wide enough to harvest net of cost.\n"
    "Higher score = more confident; keep it >= 0 (magnitude only, no sign meaning).\n"
    "ctx.col(name) gives a causal per-bar feature; ctx.X is (n_bars x n_feat); ctx.n_bars;\n"
    "ctx.hour is UTC hour. `np` is available. NO imports.\n"
    "Causal features (all backward/as-of, NEVER forward):\n"
    f"  {', '.join(DEPLOY_FEATURE_NAMES)}\n"
    "No y_fwd/cost/future. Use the time axis causally (trailing/expanding/EWMA over bars\n"
    "<= k only; never x[k:], no centered windows, no full-sample stats). A causality probe\n"
    "perturbs future rows and REJECTS any program whose past output changes.\n"
    "Ingredients to combine (recent literature): realized-range/vol size (deploy when wide),\n"
    "mean-reversion regime (variance-ratio<1 / negative autocorrelation), flow-toxicity veto\n"
    "(suppress when order-flow imbalance is one-sided), Hawkes burst veto (suppress when tick\n"
    "intensity spikes), wide-spread-with-balanced-flow harvest. The best detector is usually\n"
    "the INTERSECTION of a wide-range signal and the regime/toxicity vetoes.\n"
    "PERFORMANCE: ~50k bars, run 3x; prefer vectorised cumsum windows over per-bar window\n"
    "loops (a single O(n) EWMA pass is fine); >10s is REJECTED. Output ONLY one ```python\n"
    "code block.\n"
)

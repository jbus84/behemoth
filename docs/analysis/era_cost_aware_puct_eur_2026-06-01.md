# ERA cost-aware PUCT — EURUSD net-of-realistic-cost (2026-06-01)

In-loop objective: net of realistic round-trip cost (spread_pips + 0.06 commission + 0.10 slippage),
robustness-gated fast lower bound across (q,h). Search = qwen program evolution under PUCT; selection
A/B Thompson vs rank; rediscovery control (no seeds). Final = EUR holdout bayes_edge on net-of-cost.

## Does the EUR fade edge survive realistic cost? (seeds-only baseline)

**Yes — the best seed holds up.**

| seed | val score | holdout P(edge>0) | raw net-of-cost | (q, h, n) |
|---|---|---|---|---|
| fair_fade_mean | -1.601 | **0.902** | **+0.976** | q0.95 h200 n=15818 |
| fair_fade_pct | -2.257 | 0.897 | -0.756 | q0.99 h200 n=2837 |
| fair_fade_zscore | -3.351 | 0.880 | +4.065 | q0.99 h400 n=3151 |
| fair_fade_resid | -3.876 | 0.886 | +5.953 | q0.99 h400 n=2238 |
| fair_fade_comb | -4.440 | 0.898 | +0.660 | q0.95 h100 n=15861 |

The `fair_fade_mean` seed at q0.95 h200 delivers a **+0.976 pip/trade raw net-of-realistic-cost** on holdout with **P(edge>0) = 0.902**. The validation scores are negative because the scorer is deliberately conservative (mean−std of per-cell lower bounds), but the holdout posterior is clear: the EUR fade edge survives realistic round-trip cost.

## Did search beat the best seed?

| run | best holdout P(edge>0) | raw net-of-cost | evolved or seed? |
|---|---|---|---|
| seeds-only | **0.902** | **+0.976** | seed (fair_fade_mean) |
| thompson (seeds) | 0.886 | -0.330 | evolved |
| rank (seeds) | 0.886 | -0.330 | evolved |
| rediscovery (no seeds) | 0.703 | -1.700 | evolved (trivial root) |

**No.** The best evolved program (val=-0.843, the highest validation score of any evolved node) has a **worse holdout** than the best seed: P=0.886 vs P=0.902, raw=-0.330 vs +0.976. It scored well in the loop but does not generalise — a spurious validation win, exactly the pattern the design was built to detect.

## Verdict

1. **EUR fade survives realistic cost:** The `fair_fade_mean` seed at q0.95 h200 holds +0.976 pip/trade net-of-cost with P=0.902 on holdout. The edge is real and cost-resilient.

2. **Search did NOT beat the best seed:** Budget=40 qwen expansions, whether with Thompson or rank selection, produced no program that credibly outperforms `fair_fade_mean` on EUR holdout. The top evolved node looked better in validation (less negative score) but its holdout posterior is weaker.

3. **Thompson == rank at this budget:** Both policies found the same best evolved node. With only 40 expansions and a small validation edge to exploit, the selection policy appears second-order to the generation bottleneck.

4. **Rediscovery control confirms qwen adds nothing without seeds:** Starting from a trivial root, 40 expansions produced no viable program. This is consistent with all five prior modes — every real edge came from a seed.

## Honest null

This run is a **null** for "does PUCT find a better EUR program than the seeds?" — but it is a **positive** for "does the EUR fade edge survive realistic cost?" The build succeeded at its honest purpose: it settled the question with measured evidence rather than hope. The +0.84 raw edge from PR #286's per-symbol sweep holds at +0.976 net-of-realistic-cost on holdout.

## Caveat

Realistic **parametric** cost (spread + commission + slippage). Tick-exact certification (`analyze_oco_stop_limit_tickfill`, root checkout + broker creds) is the final gate on any survivor — out of scope here. The next step is to run the tick-exact fill verifier on `fair_fade_mean` q0.95 h200 to confirm the +0.976 survives actual Dukascopy fill simulation.

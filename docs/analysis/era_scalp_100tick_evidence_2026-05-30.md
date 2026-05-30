# ERA 100-tick scalping evidence (2026-05-30) — directional

Live `qwen3-coder-next` (ollama.com) runs of the ERA-scalp loop (`scripts/era_scalp/`)
on **EURUSD 100-tick**, validation ranking split capped to the most-recent 50k bars
(`--score-max-bars 50000`), holdout = full 2025–2026. Executed by Opus (not CI).

## Verdict

**No certifiable directional scalping edge found.** Across h1 and h3, coverage and
rediscovery runs, the discovered programs predict the *sign* of the forward move at
**~48–53% hit-rate (coin-flip)**, and net-of-cost mean is consistently **negative
(~−0.59 pips ≈ the round-trip cost)**. **BH-FDR holdout survivors: none** in every run.

This is a trustworthy negative result, **not** an infrastructure artifact (see Search
health: timeouts ≈ 0 after the scoring-split cap, so heavy programs were not silently
culled by the timer).

## Runs

| run | horizon | budget | nodes | search health | survivors |
|---|---|---|---|---|---|
| coverage | h3 | 80 | 86 | rejected 27 (timeout **0**, causality 5, static/exec 18, other 4) | none |
| coverage | h1 | 60 | 66 | rejected 25 (timeout **1**, causality 8, static/exec 10, other 6) | none |
| rediscovery (`--no-baseline-seeds`) | h3 | 40 | 42 | rejected 15 (timeout **0**, causality 1, static/exec 7, other 7) | none |

Representative top-program holdout diagnostics:

```text
h3: hit_rate 0.483 / 0.510 / 0.521, mean_net -0.57 / -0.72 / -0.75, month_hit <=0.24
h1: hit_rate 0.490 / 0.488 / 0.482, mean_net -0.61 / -0.58 / -0.63, month_hit 0.0
rediscovery h3: hit_rate 0.491 / 0.491 / 0.531, mean_net -0.59 / -0.60 / -0.74
```

The single positive *validation* score (h3, +0.1155) had an **empty holdout** — it
triggers <5 times out of sample, i.e. it fit validation noise and the holdout/BH-FDR
gate correctly gave it nothing.

## Findings

1. **Direction is ~coin-flip at 100-tick on EURUSD.** OFI / OU-s-score / Hawkes /
   multi-horizon-momentum signals do not predict the sign of `y_fwd` better than chance,
   and at ~0.59-pip cost a coin-flip is a steady loss. Consistent with tick-scale
   efficiency on a major.
2. **The timeout concern is resolved.** Capping the ranking split to 50k recent bars
   drove timeouts to ~0 (was a real risk at 207k bars × 3 probe runs). Rejections are now
   dominated by qwen writing invalid programs (static/exec) and genuine causality
   violations (correctly caught) — not the clock. So the negative result is not a
   coverage artifact.
3. **Rediscovery confirms the loop works**: with baselines removed it still explores the
   families and reaches the same (negative) frontier — the engine isn't broken, the edge
   isn't there.

## Implication / next direction

The fixed-horizon **directional** payoff (`side·y_fwd_h − cost`) is the wrong yardstick
for any **range / oscillation** strategy, whose payoff is path-dependent (two-sided,
maker). The promising pivot is **range-harvest market-making**: predict realized
range/volatility (clustering is predictable even when direction isn't) + a
range-vs-trend (breakout) gate, harvested via resting limit orders on both band edges
(Avellaneda–Stoikov / Guéant–Lehalle), scored with a maker fill model against the tick
path (the repo's tick-exact verifier). That is a new payoff harness, not a signal tweak,
and would be its own ERA variant (design pending).

Nothing here is deployable; this records a clean negative so the directional avenue is
not re-tread.

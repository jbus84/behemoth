# ERA range-harvest scalping evidence (2026-05-30)

Live `qwen3-coder-next` (ollama.com) runs of the direction-agnostic range-harvest loop
(`scripts/era_scalp/run_era_range.py`) on **EURUSD 100-tick**. Validation ranking split
capped to the most-recent 50k bars; holdout = full 2025–2026; `max_hold=10`,
`commission=0.07` pips. Executed by Opus (not CI). Two-sided maker bracket: rest BUY@center−Δ
and SELL@center+Δ, market picks the side, TP at center, SL beyond band, time-stop; conservative
fills (trade-through only, pessimistic same-bar SL, ambiguous-span skip).

## Verdict

**No certifiable edge — but structurally far closer than directional.** The maker entry
(earning the spread instead of paying it) closes ~97% of the cost gap: best holdout
`mean_net` **−0.015 pips** vs the directional variant's **−0.59**. Still net-negative, and
**BH-FDR holdout survivors: none** in both runs. Timeouts: 0 (the O(n) seed fixes held).

## Runs

| run | budget | nodes | search health | best holdout mean_net | survivors |
|---|---|---|---|---|---|
| coverage | 80 | 85 | rejected 66 (timeout **0**, causality 34, static/exec 24, other 8) | **−0.015** (node2, month-hit 0.41) | none |
| rediscovery (`--no-baseline-seeds`) | 40 | 41 | rejected 17 (timeout 0, causality 3, static/exec 13, other 1) | −0.169 | none |

Representative coverage top-3 holdout diagnostics:

```text
val 0.737  deploy 0.060  fill 0.557  tp 0.222  sl 0.453  timeout 0.325  net -0.064  month-hit 0.29
val 0.732  deploy 0.101  fill 0.570  tp 0.233  sl 0.458  timeout 0.308  net -0.015  month-hit 0.41
val 0.721  deploy 0.095  fill 0.396  tp 0.126  sl 0.382  timeout 0.492  net -0.178  month-hit 0.06
```

## Findings

1. **Maker economics work as predicted.** Earning the spread on entry moves net-of-cost from
   −0.59 (directional taker) to as little as −0.015 (range-harvest maker) — the structural
   thesis is validated. The spread was the whole problem; flipping it to revenue nearly closes
   the gap.
2. **But reversion does not beat break-through here.** Across every top program,
   **SL-rate (~38–46%) > TP-rate (~12–23%)** at the searched band/stop geometries: price breaks
   the band or times out more often than it reverts to center. That residual asymmetry is what
   keeps net just below zero.
3. **Overfit gap.** Validation ~0.74 collapses to ~−0.05…−0.2 on the embargoed holdout — the
   deploy detector found in 2024 does not generalize to 2025–26. BH-FDR correctly admits nothing.
4. **No leakage, no timeouts.** Causality rejections (34/85 coverage) show qwen frequently tries
   future-reading programs and the probe catches them; timeouts are 0 after the O(n) seed fixes.
5. **Rediscovery is weaker than coverage** — removing the baselines did not help here (unlike the
   dispersion track); the literature seeds are pulling toward the better (if still sub-zero)
   region.

## Important caveat — the fast loop is pessimistic on purpose

The fast-loop fill model resolves a same-bar TP&SL touch as **SL** (worst case). On the real
tick path many of those bars resolve TP-first. So the reported TP-rate is a **lower bound** and
the net is **understated**. The near-breakeven candidates (coverage node2 at −0.015, month-hit
0.41) are exactly the cases where honest tick-exact maker-fill verification
(`simulate_state_barrier_touch` / `analyze_oco_stop_limit_tickfill`, already in the repo) could
flip the verdict either way. That promotion step — not run here — is the right next move before
any conclusion that range-harvest "doesn't work".

## Next (not in this PR)

- Promote the closest candidates (coverage node2) through **tick-exact maker-fill verification**;
  the pessimistic same-bar-SL assumption may be masking a real (small) edge.
- Explore asymmetric brackets / partial-center TP and lower deploy quantiles (the SL>TP asymmetry
  suggests TP=center may be too far for max_hold=10).
- Other symbols/sessions (EURUSD is the most efficient major; a less-liquid pair or a specific
  session may range more cleanly).
- Nothing here is deployable; this records that maker range-harvest is near-breakeven and
  bottlenecked by tick-exact fill realism, not by the spread.

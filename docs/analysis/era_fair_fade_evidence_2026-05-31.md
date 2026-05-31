# ERA fair-fade exploitation evidence (2026-05-31)

Pooled multi-symbol fade search (`scripts/era_scalp/run_era_fade.py`): program emits a signed fade
conviction (gated fair-mispricing); trade the top-quantile |conviction|, side=sign, exit at mid[t+h];
net-of-cost PnL POOLED across the 5 majors; mean-reversion regime gate inside the program. Live
`qwen3-coder-next` (num_predict-capped, timeout-safe). Validation capped 50k recent bars/symbol;
full 2025–26 holdout; flat taker cost (cost_est_pips). Executed by Opus.

## Headline: a real, mechanistic, cross-symbol fade edge — strongest on the mean-reverting majors,
## with a marginal (fragile) way-in for CHF/JPY.

The single best program is the **`vr_gated_fade` literature seed** (Lo-MacKinlay variance-ratio gate
+ top-1% extreme dislocation, h=100). On the pooled holdout it is **net-positive on ALL FIVE majors**:

| | EURUSD | GBPUSD | AUDUSD | USDCHF | USDJPY | pooled |
|---|---|---|---|---|---|---|
| mean net/trade (pips) | +2.74 | +0.81 | +1.06 | +0.32 | +0.87 | **+1.17** |

Mechanism (sensible): at the **top 1% of fair-mispricing (extreme dislocations)**, price snaps back
**even on the random-walk-ish CHF/JPY** — extremes overshoot and revert regardless of the average
regime. The pooled objective worked: other survivors are pooled-positive only by riding EUR/AUD
(CHF/JPY still negative); `vr_gated_fade` is the only genuinely all-five-positive program.

## qwen added nothing here

- Coverage (budget 80): 7 pooled survivors, but the evolved programs are pooled-positive only by
  winning some symbols and losing others (e.g. GBP −1.08 / AUD −0.27), never all-five; several
  converged to identical duplicates. None beat the `vr_gated_fade` seed.
- Rediscovery (budget 40, `--no-baseline-seeds`): **no survivors** — without the literature seeds the
  search did not recover the gated fade. The value is in the seeded literature gate (VR + extreme),
  not the LLM search at this budget.
- Search health (coverage): 50/85 rejected (37 static/exec from qwen writing invalid programs, 6
  timeout, 0 causality). Timeouts low thanks to the num_predict cap.

## Honest caveats — the CHF/JPY "way in" is marginal, not solid

- **Strong & solid:** EUR/GBP/AUD (the mean-reverting majors) — large positive net, many trades,
  consistent with the earlier per-symbol mean-reversion analysis. This is the real edge.
- **Marginal & fragile:** CHF (+0.32) and JPY (+0.87) are small and trade only at q=0.99 (top 1%).
  With overlapping h=100 windows, the **effective independent episodes** are roughly n/h: CHF ~1724/100
  ≈ 17, JPY ~3152/100 ≈ 31. A handful of independent episodes — the pooled n=11460 makes BH-FDR pass
  trivially, but the per-symbol CHF/JPY result rests on too few independent episodes to trust yet.
- **Fast-metric, flat taker cost; overlapping-window significance is inflated.** Month-consistency and
  non-overlapping resampling are the honest next checks; per-symbol month-consistency was not isolated
  here.

## Verdict

The investigation's clearest positive: a **mean-reversion-gated extreme-dislocation fade** is
net-positive across the majors on a pooled, embargoed holdout — robustly on EUR/GBP/AUD, marginally
on CHF/JPY — grounded in literature (variance-ratio regime + extreme reversion), discovered by the
*seeds* (qwen did not improve it). Not deployable: it is a fast-metric / taker-cost result and the
CHF/JPY portion needs non-overlapping confirmation; tick-exact fills + the Stage-2/3 → Reduced-Core →
Robustness ladder remain the real gates.

## Next
- Non-overlapping / per-symbol month-consistency re-measure of `vr_gated_fade` (especially CHF/JPY).
- Tick-exact fill verification of the EUR/GBP/AUD edge (the solid part).
- Then the governance ladder. qwen search added no value here — the literature seed is the result.

# ERA range-harvest 1000-tick evidence + cross-symbol verdict (2026-05-31)

Follow-up to the 100-tick range-harvest evidence (near-breakeven, −0.015). Tests whether coarser
1000-tick bars — where the band Δ can be wide against the same fixed cost — produce a real edge.
Live `qwen3-coder-next`, validation capped 50k recent bars, full holdout, `max_hold=10`,
widened bracket grid (Δ∈{2,3,5,8,12}, stop∈{2,4,8}).

## Verdict: the positive 1000-tick result was a mirage — it does NOT replicate cross-symbol

| symbol | run | BH-FDR survivors | best holdout mean_net | month-hit |
|---|---|---|---|---|
| **EURUSD** | coverage b80 | **5 (all top)** | **+0.223** | 0.89 |
| EURUSD | rediscovery b40 (no baselines) | none | −2.41 | 0.0 |
| GBPUSD | coverage b80 | none | −2.74 | 0.0 |
| USDCHF | coverage b80 | none | −2.84 | 0.0 |
| AUDUSD | coverage b80 | none | −2.54 | 0.0 |

EURUSD coverage was the **only** configuration of five (4 symbols + EURUSD rediscovery) to produce
survivors. One-in-five aligning is the textbook signature of **overfitting on a multiple-testing
surface**: the programs fit the validation split (val node-scores ~2.8–3.4 everywhere), and only
EURUSD's holdout happened to align. The validation→holdout gap is enormous and the failures are
catastrophic (sl-rate ~0.88–0.98, mean_net ~−2.7, 0% positive months) — not "weaker edge" but "no
edge, plus overfit".

## Findings

1. **No robust 1000-tick range edge.** The cost-economics improvement (7× move/cost ratio) was real,
   but reversion-from-extreme does not beat break-through at coarse bars on any major — sl-rates of
   0.88–0.98 confirm price trends/walks through the band far more than it reverts to center.
2. **EURUSD +0.22 was a fragile artifact.** It failed to replicate on GBPUSD, USDCHF, AUDUSD, and on
   EURUSD itself with a different seed set (rediscovery). A real edge would survive at least one of
   those. This is the project's known "barrier-family mirage" failure mode recurring.
3. **The fast-loop fill model is not the culprit.** Timeouts were 0 and the conservative same-bar-SL
   tie-break is pessimistic, so tick-exact verification could only *lower* the EURUSD number, not
   rescue the −2.7 cross-symbol failures. Cross-symbol non-replication is decisive on its own.
4. **Cross-symbol replication is the cheap, decisive guard** against this mirage class — far cheaper
   than tick-exact verification and it killed the false positive immediately.

## Conclusion

Range-harvest (both 100-tick near-breakeven and 1000-tick EURUSD-only positive) does **not** yield a
certifiable edge. Combined with the directional negative (PR #280), the per-trade-P&L scalping
framings are exhausted on this data. The motivation to pivot to **fair-price prediction** (an IC over
tens of thousands of samples, far harder to overfit, validated cross-symbol the same way) stands
reinforced — see `docs/superpowers/specs/2026-05-31-era-fair-price-prediction-design.md`.

Nothing here is deployable. This records the honest negative so the EURUSD 1000-tick number is not
mistaken for a win.

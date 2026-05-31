# Bayesian edge verdict — vr_gated_fade (2026-05-31)

Hierarchical, partial-pooled posterior (`scripts/era_scalp/bayes_edge.py`, NumPyro) over the
net-of-cost edge of `vr_gated_fade` (q=0.99, h=100) on the 2025–26 holdout. Observations =
per-(symbol,month) mean net (de-correlates the h=100 overlap that inflated the per-trade BH-FDR).
Skeptical Normal(0, 0.5) prior; Student-t likelihood; `mu_s>0` ⇒ beats cost.

## Verdict

```
Pooled: P(edge>0)=0.410   mean -0.07   94% CI [-0.90, +0.83] pips  -> indistinguishable from zero
```

| symbol | P(edge>0) | mean (pips) | 94% CI | read |
|---|---|---|---|---|
| EURUSD | **0.994** | +1.16 | [+0.62, +1.93] | **credibly positive** |
| AUDUSD | **0.983** | +1.02 | [+0.18, +3.13] | **credibly positive** |
| USDJPY | 0.881 | +0.35 | [-0.36, +1.34] | leans +, CI straddles 0 — uncertain |
| USDCHF | 0.408 | -0.21 | [-2.12, +2.36] | indistinguishable from zero |
| GBPUSD | 0.072 | -3.49 | [-4.28, +0.57] | **credibly negative** |

## What the Bayesian layer revealed (vs the naive per-trade backtest)

The per-trade pooled headline was "+1.17 pip/trade, all five majors positive". Once the overlap is
de-correlated (monthly observations) and symbols are partial-pooled, that picture changes sharply:

1. **The pooled edge is indistinguishable from zero** (P=0.41). The "+1.17, all-5-positive" was
   inflated by overlapping/correlated trades — exactly the failure the monthly aggregation guards.
2. **Only EURUSD and AUDUSD are credibly positive** (P>0.98, CI entirely above 0, ~+1 pip/trade) —
   the genuine edge, consistent with their being the most mean-reverting majors (low variance ratio).
3. **GBPUSD is credibly NEGATIVE** (P=0.072): its per-trade +0.81 was a few-months artifact; month
   to month it loses. The monthly posterior caught a mirage the per-trade mean hid.
4. **USDCHF and USDJPY are noise** — wide CIs straddling 0. The CHF/JPY "way in" suggested by the
   pooled per-trade numbers is **not** confirmed; it was the few-independent-episodes fragility
   (~17/31 effective episodes) flagged in the fade evidence.

## Verdict in one line

`vr_gated_fade` has a **real, credible edge on EURUSD and AUDUSD only** (~+1 pip/trade, mean-reverting
majors); it is **negative on GBPUSD** and **indistinguishable from zero on USDCHF/USDJPY**. The pooled
"all-five-positive" result was a per-trade-overlap artifact.

## Caveats / next

- This posterior is over the **optimistic mid-to-mid / flat-cost** net, so even EUR/AUD's credibly
  positive ~+1 pip is **pre-tick-exact-cost**; the tick-exact + realistic round-trip cost gate is the
  binding next check and could erode it. The Bayesian layer bounds *confidence given that net*, not
  deployability.
- Honest framing for the strategy: pursue EURUSD + AUDUSD (mean-reverting majors); drop the GBP/CHF/JPY
  "breadth" claim. Low-frequency (a few dozen tradeable entries/yr/symbol).
- The Bayesian layer worked as intended: it shrank an inflated multi-symbol headline to the two
  symbols that survive honest, de-correlated, partial-pooled scrutiny. This is the confidence tool the
  investigation needed; Phase 2 (Bayesian-integrated PUCT) builds on it.

## Follow-up: GBP wants CONTINUATION, not reversion (directional regime split)

GBP's credibly-negative fade prompted the question "just flip to continuation?". Tested by negating
the signal (same VR gate + q=0.99 extreme, opposite side) and re-running the Bayesian verdict:

| symbol | fade P(edge>0) | continuation P(edge>0) | regime |
|---|---|---|---|
| EURUSD | 0.994 (+1.16) | 0.000 (-2.11) | reversion |
| AUDUSD | 0.983 (+1.02) | 0.000 (-3.01) | reversion |
| GBPUSD | 0.072 (-3.49) | **1.000 (+1.96)** | **continuation** |
| USDJPY | 0.881 (+0.35) | 0.000 (-2.25) | weak reversion (not credible) |
| USDCHF | 0.408 (-0.21) | 0.217 (-1.19) | no edge either way |

**GBP is credibly a continuation symbol** (flip -> +1.96, P=1.000, CI [+1.56,+2.26]). The clean
ANTI-CORRELATION (EUR/AUD fade-positive go strongly continuation-NEGATIVE, GBP the reverse) confirms a
real per-symbol directional regime split, not noise — noise would not flip to credible opposite signs.
JPY leans reversion but uncredible; CHF is noise in both directions (drop it).

**Principled deployment (avoids per-symbol overfit):** condition direction on the measurable regime —
`fade if trailing variance-ratio < 1 (mean-reverting: EUR/AUD) else continue (trending: GBP)` — a
single causal rule decided without peeking at PnL, then Bayesian-validated. A natural next ERA seed
(`vr_conditional_direction`). Still mid-to-mid/flat-cost; tick-exact gate pending. Real credible edge
now = EUR+AUD (fade) + GBP (continuation), ~+1 to +2 pip/trade pre-cost; JPY/CHF no credible edge.

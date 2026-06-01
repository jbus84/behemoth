# ERA per-symbol edge sweep — validation-selected, holdout-confirmed (2026-06-01)

Each major chose its own (direction ∈ {fade, continue}, q, h) on the VALIDATION split (2024) by the
lower credible bound of the monthly posterior under a sample guard (≥200 trades, ≥6 months), then
confirmed that ONE setting on the HOLDOUT (2025–26). No holdout selection. This replaces the
pooled-across-5 scalar and tests whether pooling was masking a per-symbol continuation edge. The
posterior is shown alongside the trade-weighted raw mean + month-hit, because the monthly posterior can
be inflated by low-count months.

## Headline — validation-selected, holdout-confirmed

| symbol | dir | q | h | holdout P(edge>0) | post mean | raw mean | n_trades | n_months | month_hit |
|---|---|---|---|---|---|---|---|---|---|
| EURUSD | **fade** | 0.90 | 400 | **0.889** | +0.597 | **+0.839** | 31716 | 17 | 0.65 |
| GBPUSD | fade | 0.90 | 400 | 0.129 | -0.399 | +0.231 | 34444 | 17 | 0.47 |
| AUDUSD | fade | 0.95 | 200 | 0.750 | +0.272 | +0.843 | 12950 | 17 | 0.65 |
| USDCHF | fade | 0.90 | 200 | 0.649 | +0.090 | **-1.230** | 23684 | 17 | 0.59 |
| USDJPY | **continue** | 0.99 | 200 | 0.568 | +0.108 | +1.051 | 4385 | 17 | 0.41 |

## Verdict — no symbol credibly positive out-of-sample; pooling was NOT hiding a continuation edge

**Once holdout selection is removed, nothing clears the credibility bar.** Every symbol's
validation-chosen setting gives a holdout `P(edge>0) < 0.95`. The best is **EURUSD fade (P=0.889, raw
+0.84 pip/trade, 65% of months positive, 31,716 trades)** — a genuine *lean*, on a huge clean sample,
but not a credible edge. AUDUSD fade is similar but weaker (P=0.750, +0.84). This is the honest,
de-inflated picture: the earlier EUR "+1.78 / P≈1.0" was the q=0.99/h=400 cell, and the conservative
lower-CI-bound selection (which rewards confidence/sample size) instead picked q=0.90/h=400 — more
trades, lower magnitude. EUR's true fade edge sits between those: real and positive-leaning, not a slam
dunk.

**On the continuation question — the key reason for this sweep: pooling was not masking a continuation
goldmine.** When each symbol is free to pick fade *or* continue on its own validation data:
- only **USDJPY** selected **continue** — and it does *not* confirm (holdout P=0.568, month-hit 0.41, a
  coin flip despite a +1.05 raw mean driven by few months);
- **GBPUSD** — which the earlier `vr_conditional` run suggested wanted continuation — selected **fade**
  here and did not confirm (P=0.129). Its apparent continuation edge was a single-grid-point artifact,
  not a robust out-of-sample property.

So averaging the five majors *diluted* the EUR/AUD fade lean (correctly identified), but it was **not**
hiding a credible continuation edge in any symbol. The honest per-symbol map is: **EUR/AUD have a weak
positive fade lean; GBP/CHF/JPY have no credible edge in either direction.**

## What this settles
- The recurring EUR+AUD-fade signal is confirmed *qualitatively* (4th reconvergence) but is **weaker
  than the selection-inflated headlines** — honest holdout P≈0.89 / raw +0.84 for EUR.
- There is **no hidden continuation edge** to recover by un-pooling. The continuation hypothesis is
  closed: faded-major reversion (EUR/AUD) is the only thing here, and it is marginal.
- USDCHF illustrates the posterior-vs-raw trap again: posterior +0.09 but **raw −1.23** — the monthly
  model is misleading there; trust the raw + month-hit.

## Caveat & next
Mid-to-mid / flat-cost. The honest EUR fade lean (+0.84 raw pip/trade over 31,716 trades, 65% months)
is the only candidate worth the **tick-exact realistic round-trip cost gate** — and at sub-pip it is now
borderline whether it survives cost, which is exactly what that gate must decide. Selection used the
lower-CI bound (favours sample size); a magnitude-first view would re-surface EUR q=0.99/h=400, so the
cost gate should test EUR fade at both q=0.90 and q=0.99 / h=400.

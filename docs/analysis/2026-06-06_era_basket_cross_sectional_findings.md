# Intraday Cross-Sectional FX Basket Book — Findings (Negative Result)

**Date:** 2026-06-06
**Branch:** `worktree-era-basket-cross-sectional`
**Status:** Infrastructure complete and tested; **no reliable edge found** in the 6-major
universe. Merged for reuse, not deployed.

---

## Purpose

Pivot away from single-pair, time-series tick scalping (latency-disadvantaged for retail)
toward a **cross-sectional** approach: rank a universe of FX pairs against each other each
bar and trade the relative ordering as a **dollar-neutral long/short basket** — long the
top-k, short the bottom-k. The thesis: the edge becomes *breadth across many diversified
bets* rather than speed, which is the game retail can actually play.

Built as a new ERA `RunSpec` (`scripts/era_scalp/era_basket.py`), sibling to the single-leg
`era_xs`, reusing the engine's verdict machinery (`edge_verdict`, DSR, temporal robustness,
effective-m Šidák). Design + plan: `docs/superpowers/specs/2026-06-06-…-design.md`,
`docs/superpowers/plans/2026-06-06-…`.

## Outcome

**No statistically reliable cross-sectional edge exists in the 6 USD majors at 1000-tick.**
The build is correct (18 tests + masking fix, `make quality` clean); the signal is not there.
The negative result was reached cheaply — before any expensive PUCT search — which is the
value delivered.

---

## What was tested

Validation split only (2025-07…10; holdout untouched), 1000-tick bars, USD-aligned
`xs_ret_z` ranking. Seeds: cross-sectional **reversal**, relative **momentum**, **lead-lag**.
Per-rebalance P&L decomposed into **gross** (pre-cost) vs **cost**, with t-stats, across a
sweep of holding horizon `h ∈ {3,6,12,24,48,96}`, `k ∈ {1,2}`, and aggressive/passive fills.

## Key findings

1. **Gross (pre-cost) edge is indistinguishable from zero.** The gross t-stat never exceeds
   ~1.4 in any configuration. Reversal shows a small *positive* gross (~0.15 pips/rebalance
   at h=3); momentum ~zero; lead-lag *negative* (a bad seed).

2. **Turnover cost dwarfs the signal by 10–20×.** Aggressive cost ≈ 2–3 pips/rebalance,
   passive ≈ 1–1.5, versus gross ≈ 0.15. Short-horizon net is significantly *negative*
   (t = −7 to −8) — pure cost domination, exactly the conversation's thesis.

3. **The "amortize cost with longer holds" hypothesis fails the significance bar.** Net
   turns nominally positive at long horizons (h=96, k=1: net +10.1 aggressive / +11.5
   passive), but this is a **small-sample mirage**: only ~60 rebalances, net t ≈ 1.06, and
   `gross/bar` *flips sign* across horizons (+0.05, −0.08, −0.08, +0.02, +0.14, +0.13). A
   real persistent edge improves monotonically with hold; this wanders. Same shape as the
   logged barrier-family mirage.

4. **Momentum is reliably losing at long horizon** (h=48, k=2: net −11.3, **t = −2.6**).

5. **Breadth is the binding constraint.** Cross-sectional power comes from many weakly
   correlated bets. The universe is **6 instruments, all USD-quoted** — a narrow,
   USD-correlated cross-section; with k=1–2 there is almost no diversification. The robust
   cross-sectional FX factors (carry, value) are flat intraday. Only the 6 majors have
   velocity data — no crosses (EURGBP, EURJPY, …) to widen the book.

## Implementation notes (kept for reuse)

- **Band lever is a no-op as implemented.** The book-level L1 turnover band has no effect in
  its useful range and blocks *initial entry* at its threshold (band ≥ entry L1 ⇒ never
  enters). If revisited, replace with per-symbol rank hysteresis or rebalance-cadence control.
- **Holding horizon, not the band, is the real turnover lever** — and it is what determines
  cost amortization. The periodic-rebalance model is parameterized for it.
- A masking fix landed so a leg with non-finite forward return or cost is never held
  (prevents `nansum` cost-accounting bias at panel boundaries).

## Recommended future direction (if cross-sectional is pursued)

Onboard **cross-pair data for genuine breadth** (EURGBP/EURJPY/GBPJPY/AUDJPY/…) and
generalize the cross-section beyond USD-quoted pairs (non-USD pairs have no USD leg, so the
`usd_sign` alignment needs rethinking). Without breadth, an intraday cross-sectional book on
6 correlated majors is structurally unlikely to clear costs.

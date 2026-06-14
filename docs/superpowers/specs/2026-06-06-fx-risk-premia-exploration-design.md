# FX Risk-Premia Exploration — Design / Running Notes

**Date:** 2026-06-06
**Branch:** `worktree-era-fixing-premium`
**Status:** Exploration in progress (autonomous, user-authorised). Holdout sacred until final.

## Motivation

Single-pair tick scalping and intraday cross-sectional baskets both failed (latency /
cost / no breadth). The remaining retail-viable edge is a **risk premium**: a small,
structural, *patience-not-speed* return that survives because it compensates someone for
bearing a risk, not because we out-race anyone. Goal: find a tiny but real, cost-surviving
edge in the intraday tick data of the 6 USD majors.

## Hypothesis portfolio (literature-grounded)

1. **Intraday fixing / seasonality premium (primary).** Krohn–Mueller–Whelan (JF 2024):
   USD appreciates into the Tokyo/ECB/London fixes and reverts after (W-shape, ~2bps),
   compensation for dealer inventory risk. Low-turnover (once/day), uses all 6 majors as a
   timed *directional USD basket*, cost paid once.
2. **Daily time-series momentum (secondary).** Moskowitz–Ooi–Pedersen: trend premium,
   speculators earn it from hedgers. Our 14-month sample is short for its 1–12mo horizon.

## Discovery probe result (validation+train, 1000-tick, z-returns by UTC hour)

Mean USD-strength return per UTC hour shows **real intraday structure but NOT the textbook
fix W-shape**:
- Cumulative USD path drifts **down** through the London/NY session (to ~−0.09z by ~20:00
  UTC), then **reverts up sharply overnight** (22–23 UTC: +0.039, +0.033z).
- Largest effects: late-session USD rally (22–23 UTC, but thin liquidity ⇒ widest spreads)
  and London-session USD weakness (10–11 UTC, liquid, large sample).
- The classic "USD appreciates *into* 13–16 UTC fixes" run-up is not clean here.

Read: intraday seasonality is present (not a martingale), but small (z~0.01–0.04/hr) and
shaped as a **London-session USD fade + overnight reversion**, not the literature fix shape.

## The make-or-break test (next)

Tradability is a **pip-net-of-cost** question, once-daily turnover. Candidate timed trades on
a USD basket, scored on validation with monthly t-stats (holdout untouched):
- (a) Short USD basket over the London/NY session window (~10:00→~16:00 UTC).
- (b) Long USD basket overnight (~21:00→~23:00 UTC) — flag: thin = high cost.
- (c) Textbook fix run-up/reversion windows.

Decision rule: gross pips per day must be **several × the one round-trip cost** to be worth
pursuing; otherwise document negative and move to TSMOM. No band/window tuned to holdout.

## Framework alignment

Reuse `build_basket_panel` (pip `y_fwd_panel` + `cost_panel`, USD-aligned `r`) from the
merged basket work; add a time-of-day gate + a once-daily timed-trade score frame. If an edge
clears, formalise as a `RunSpec` sibling; else a documented negative-result findings doc.

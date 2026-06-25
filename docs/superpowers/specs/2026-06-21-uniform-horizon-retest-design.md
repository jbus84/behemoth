# Uniform 1h-Grid Multi-Horizon Net-Edge Re-test — Design

Date: 2026-06-21
Status: Design (approved in brainstorming, pending spec review)
Trigger: the Phase-B timeframe pre-screen's "only 2h shifts" was found to be an
  ARTIFACT — disjoint truncate-from-epoch bars give only ~4 in-session bars/day at
  3h/4h, and 24-bar feature windows over nightly contiguity breaks decimate the panel
  (3h/4h panel ≈ 2171 vs 2h ≈ 8689; 3h≡4h identical counts). 3h/4h were never validly
  tested, and 1h's net edge was never directly measured.

---

## 1. Motivation

Two open questions the Phase-B pipeline could not answer fairly:
1. **3h/4h** were decimated by the intraday-session × bar-count-feature interaction — their
   "no shift" is an artifact, not evidence.
2. **1h** was fairly sampled but only tested for path-*shape* shift, never for **net
   directional edge after cost** — the question "does 1h clear cost?" was assumed, not
   measured.

The fix (user's reframe): **decouple the sampling grid from the holding horizon.** Build
everything on a uniform **1h grid** (tiles (7,21) cleanly → 14 bars/day, contiguous,
features well-defined at every horizon), and treat 2h/3h/4h as the **forward horizon**,
sampled every hour. Then measure the **net-after-cost directional edge per horizon** with
honest, overlap-aware inference.

---

## 2. Architecture — one grid, many horizons

- **1h bars** on the (7,21) session (reuse `build_freq_bars(df, "1h")`). Contiguous;
  24-bar features never decimate.
- **Features** (`r_1, mom_short, mom_long, rvol_24, hour`) computed once on the 1h grid,
  shared across horizons.
- **Horizon-parameterized target (NEW):** for `H ∈ {1,2,3,4}` hours, target =
  forward-H-bar return on the 1h grid (`(log(mid[t+H]) − log(mid[t]))·1e4`), vol-normalized
  by `sigma_h`. Entry can occur at **any** 1h bar. This is the core new code — the existing
  `build_panel` only does next-1-bar.
- **Causal ridge WFO per horizon** (same expanding-fold scheme as `tail_wfo.walk_forward`),
  tail-long = top-q predicted, held H hours. Realized return is the **bar-close-to-bar-close**
  forward-H return (`ret_fwd_bps`), cost charged once. (The 1-minute path is NOT used here —
  it is only needed for bracket geometry, which is downstream. This supersedes an earlier
  draft that mentioned the 1-min path.)
- Old disjoint-bucket 2h/3h/4h construction is **retired** for this comparison; all horizons
  re-baselined under one uniform rule.

---

## 3. Dual inference (both must agree) + decision metric

For each (pair, horizon) the tail-long net-after-cost track is evaluated **two ways**, and an
edge is called real only if **both clear zero with the same sign**:

- **Overlapping / clustered:** all hourly entries; significance via **day-clustered t** +
  **year-block bootstrap 95% CI**; the **effective non-overlapping N** is reported beside the
  raw N so autocorrelation inflation is always visible.
- **Non-overlapping:** one entry per H-hour block (stride = H bars); independent track with
  its own t / CI.

Disagreement ⇒ the overlapping signal was autocorrelation, not edge.

**Decision metric (decompose gross / cost / significance):** per (pair, H) report gross
top-decile mean, hit-rate, **net after per-pair `COST_BPS`**, day-clustered p, bootstrap CI,
positive-years; pooled across TIGHT majors (EUR/GBP/JPY) for power, per-pair cost charged.
This is the readout that directly answers "does 1h clear cost?" — putting the 1h
gross-vs-cost ratio on the table rather than assuming it.

**Multiplicity:** **BH-FDR across the full {horizon × pair-pool} grid** so adding horizons
cannot manufacture a winner.

---

## 4. Honest expectation

Cost is ~flat per trade (~0.64 bps) while the H-hour move scales ~√H, so the cost ratio
*improves* with H. Therefore:
- **1h faces the steepest cost headwind** — if it is net-negative, that is the structural
  answer to "is 1h really dead," now measured not guessed.
- **2h–4h, once un-decimated, may show a fair real edge** — potentially *expanding* the
  deployable set beyond just 2h (the original point of the timeframe question).
Either outcome is decisive and fairly measured.

---

## 5. Scope

This re-test is about the **net directional edge per horizon** — the thing both open questions
hinge on. Path-shift gating and bracket geometry are **downstream**: only worth re-running on
horizons that clear (or nearly clear) cost. The Phase-B 2h geometry NO_GO is unaffected and
stands.

New module: `scripts/fx_coint/horizon_retest.py` (horizon panel builder + per-horizon
net-edge + dual inference + CLI → `horizon_retest_results.md`). Reuses `reg_signal_hunt`
(build_freq_bars/features/COST_BPS/bh_reject), `tail_wfo` (Ridge WFO pattern,
day_clustered_tstat), Phase-A `path_geometry_paths`/`path_ensemble` (1-min path, bar-close
anchor), and the year-block bootstrap from Phase-B `path_geometry_opt`.

---

## 6. Out of scope (YAGNI)

- Re-running geometry/path-shift now (downstream; only on cost-clearing horizons).
- Horizons beyond 1–4h or sub-1h (the prior says shorter is worse; 15m already NO_GO).
- New instruments beyond the six majors.
- Changing the validated 2h (7,21) edge's prior result — this re-test re-baselines under a
  uniform rule for comparison; the original stands as its own reference.
- 24h-session bars (considered; rejected in favor of keeping liquid (7,21) + 1h grid +
  liquid-hour entries implicit in the session).

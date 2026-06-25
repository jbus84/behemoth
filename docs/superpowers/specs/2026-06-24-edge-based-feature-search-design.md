# Two-Track Edge-Based Feature Search — Design

**Date:** 2026-06-24
**Status:** Approved (design); pending spec review
**Location:** `scripts/fx_coint/`, reports in `reports/edge_feature_search/`

## Problem

This session established that **IC robustness ≠ tradeable edge**. The
`dev_age × adf_sup` gate had beautiful, monotone, OOS-robust rank IC yet
contributed **nothing** to walk-forward non-overlap net P&L over simple
magnitude isolation. IC is a rank statistic: it weights every event equally and
discards magnitude, while P&L is dominated by the few large-|return| trades and
is a threshold function of cost. So a feature search that ranks by IC optimises
the wrong objective.

This redesigns the feature search so the objective **equates to edge** (net
bps/trade after cost, walk-forward, non-overlapping), via two prediction tracks
plus a conditioning lens.

## Non-goals

- **No modelling.** Every track combines features with the base via a simple,
  non-fit rule (ranking, veto, tercile-gate). This produces feature
  *assessments*, not a fitted model. Full higher-order non-linear interaction
  discovery (HistGBM importance under a P&L objective) is the **planned next
  phase**, explicitly deferred.

## Established base strategy (fixed)

The only configuration that survived the walk-forward non-overlap P&L gate:
**fade `ffd_zvol20`** (direction = `-sign(ffd_zvol20)`) × **top-decile
`|ffd_zvol20|`** selection, triple-barrier target, vol-scaled symmetric barriers
`1.0 * vol * sqrt(N)`, primarily **N=50** (secondarily N=30), pooled 5 ex-JPY
majors, realistic round-trip cost 1.0 bps. All edge contribution is measured as
**marginal lift over this fixed base.**

## Two tracks + one conditioning lens

A feature "equates to edge" if it adds net-bps in **any** of three roles. The
search reports all three; a feature is not discarded for failing the linear
(marginal) lenses if it succeeds as a conditioner.

### Direction track
- **Predicts:** the *side* of the move, weighted toward big-money events.
- **Stage-1 screen (cheap):** **|return|-weighted directional IC** — Spearman of
  feature vs first-touch return, event weights ∝ |return| (the
  `fx-sample-weights` machinery). Fixes IC's magnitude blind spot.

### Magnitude track
- **Predicts:** continuous **|return|** (move size) — to select cost-clearing
  trades. (Chosen over binary clears-cost: more informative, generalises the
  `top_mag` lever that worked, keeps the cost assumption out of the search.)
- **Stage-1 screen (cheap):** **IC(feature, |return|)** — does it rank move size.

### Conditioning / interaction lens
- **Predicts:** *when* the base fade works (interaction value, e.g. the `dev_age`
  gate) — value that is invisible to additive/linear screens.
- **Stage-1 screen (cheap):** tercile-gate the base on the feature; report the
  **net-bps spread across terciles** — judged in **net-bps, NOT IC** (the gate
  scan's strong IC spread was exactly what failed to pay). Also a pairwise
  **candidate × base multiplicative** net-bps check (the `ffd × dev_age`
  pattern), so interaction-only features are not missed.

## Two-stage protocol

**Stage 1 — cheap screen (rank candidates).** Compute each track's screen
statistic, pooled over the 5 majors, with **sign-consistency (≥4/5)** and
**non-overlap stability** gates, swept over N. Produces a ranked candidate list
per role.

**Stage 2 — confirm survivors (marginal net-bps over the fixed base).** Run
survivors through the existing **walk-forward non-overlap** P&L harness
(`pnl_walkforward`) and measure Δ net-bps via the role's simple non-fit rule:
- *Magnitude candidate:* re-rank selection by the candidate (or avg-rank of
  candidate & `|ffd_zvol20|`), take top decile → Δ net-bps vs base.
- *Direction candidate:* among base-selected trades, keep only those where the
  candidate's signed vote **agrees** with the fade direction (confirmation/veto)
  → Δ net-bps vs base.
- *Conditioner:* restrict base trades to the best candidate tercile → Δ net-bps
  vs base.

A feature is an edge feature only if it clears **both** the screen and the
net-bps confirm in at least one role — never either alone (multiplicity guard).

## Scope

- **Feature universe:** the ~25 tick-native features already built in
  `feature_ic_definitive` (engineered-lag + microstructure + De Prado
  price-only). No new feature construction in this phase.
- **Bars/pool/target:** 1000-tick bars, 5 ex-JPY majors, N-bar triple-barrier;
  confirm at N=50 (primary), N=30 (secondary).
- **Cost:** 1.0 bps round-trip primary; report breakeven.

## Module layout

- `edge_feature_search.py` — Stage-1 two-track-plus-conditioning weighted-IC /
  net-bps-spread screen; pure scoring functions + a thin `main()` producing the
  ranked candidate report.
- Extend/wrap `pnl_walkforward.py` for the Stage-2 marginal-lift confirm (add a
  per-feature, per-role Δ-net-bps mode reusing the existing non-overlap +
  walk-forward machinery).
- `reports/edge_feature_search/` — ranked screen tables, confirm tables, plots,
  and a markdown report.
- Tests in `tests/fx_coint/` for the new pure scoring functions (weighted IC,
  tercile net-bps spread, marginal-lift rule), following the `test_*.py` pattern.

## Honesty guardrails

- Walk-forward + non-overlap from the first confirm (no single-split numbers).
- Conditioning value judged in **net-bps, not IC** (the session's central lesson).
- Multiplicity: ≈25 features × 3 roles — survivors must clear screen *and*
  confirm; report how many roles/configs were tried.
- The no-modelling boundary is explicit; HistGBM-under-P&L importance is the
  documented next phase, not part of this build.

## Decisions locked

- Magnitude target: continuous |return| (not binary clears-cost).
- Scoring: two-stage (cheap weighted-IC / net-bps-spread screen → net-bps confirm).
- Baseline: marginal lift over the fixed base (not free combination).
- Third lens: conditioning/interaction, judged in net-bps, to catch
  interaction-only features the linear screens miss.
- No modelling this phase; full non-linear interaction discovery deferred.

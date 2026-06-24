# Target Predictability Report Card — Design

**Date:** 2026-06-23
**Status:** Approved (design); pending spec review
**Location:** `scripts/fx_coint/`, tests in `tests/fx_coint/`

## Problem

All existing tooling (`triple_barrier_ic.py`, `lagged_feature_ic.py`, `tail_*`, etc.)
measures **feature → target** association: given a feature, how well does it predict.
This is silent on the orthogonal axis: **how predictable is a target in the first
place**, independent of any feature set.

Without a target-side measure we cannot distinguish:
- "No signal exists in this target" (abandon the target), from
- "Signal exists but my features are weak" (keep engineering features).

This ambiguity has produced repeated mirages (triple-barrier overlap inflating
significance, day-clustered edges, stale-bar artifacts, tick-exact-vs-OHLC illusions).
A feature-agnostic target report card lets us triage targets *before* spending
feature-engineering or GPU effort.

## Scope

The tool scores a **target**, not a feature. Unit of analysis:

```
score_target(target_spec, dataset, pair_pool) -> ReportCard
```

- `target_spec` reuses existing label builders: `triple_barrier` (path-dependent),
  fixed-horizon return, `reversion_targets`.
- Run across the existing horizon × bar-type × label-family grid; rank the resulting
  cards.

Out of scope: cross-sectional / exogenous information sets for the ceiling (own-history
only — see "Information set" below). Best-effort achievable predictability ("Stage B")
is considered already covered by the existing IC/WFO scripts and is **not** rebuilt here.

## Diagnostic funnel

Two stages, cheapest first; each gates the next.

### Stage C — Well-posedness (cheap, runs first, own-history only)

Catches the artifacts that have repeatedly burned us. Each metric maps to a past failure:

| Metric | What it catches |
|---|---|
| Effective-N / overlap ratio (label autocorrelation → independent-sample count) | Triple-barrier overlap & overlapping-horizon significance inflation |
| Temporal concentration (Gini of \|signal\| over days) | "95% of edge in 3 days" / day-clustered significance |
| Class/sign balance + label entropy (barrier) or tail skew (continuous) | Degenerate / near-constant targets |
| Regime stability (target's own vol/skew/autocorr, train vs OOS) | Stale-bar / clock artifacts where the target distribution shifts |
| Label-noise proxy (label flip-rate under ±1-tick barrier perturbation) | Tick-exact-vs-OHLC illusions / adverse-selection sensitivity |

A target failing C hard (effective-N collapse, extreme concentration, degenerate
balance) is **flagged ill-posed and Stage A is skipped** to save compute.

### Stage A — Intrinsic ceiling (own-history info set, bracketed)

"Predictable from what?" → **own-history only**: the target's own past path
(lagged returns/vol of the same instrument). This is the honest, low-dimensional
baseline where information-theoretic estimators are reliable. Cross-sectional (panel)
is a deliberate future extension, not in this build.

The ceiling is reported as a **bracket**, not a point — this is what separates
"no signal" from "weak model":

- **Lower bound:** a flexible model (gradient boosting) on the own-history lag
  embedding, under purged + embargoed CV → realized OOS skill. "At least this predictable."
- **Upper estimate:** Kraskov k-NN mutual information on the low-dim lag embedding.
  "Information-theoretically about this much."
- **Null:** block-permutation (autocorrelation-preserving shuffle), N draws, producing
  a null distribution for **both** estimators.

Report the interval `[lower, MI]` and the **distance-from-null** (z-score / empirical p)
for each estimator.

## Skill metrics

- Continuous targets: **Spearman IC** (comparable to existing IC work).
- Barrier-class targets: **balanced accuracy / normalized MI**.

## Output

One `ReportCard` per target:
- A dataclass holding all Stage-C metrics and Stage-A bracket + null stats.
- A printed table row matching the existing script-report style (see `report.py`).
- A `verdict` field reusing canonical-style values: well-posed / ill-posed (Stage C);
  signal / null-indistinguishable (Stage A).

## Module layout

Mirrors existing `scripts/fx_coint/` conventions (pure functions + thin CLI `main()`):

- `target_wellposedness.py` — Stage C metrics as pure, unit-testable functions.
- `target_ceiling.py` — Stage A estimators (model lower bound, kNN-MI, block-perm null).
- `target_report.py` — orchestrates the funnel, builds `ReportCard`, CLI entry point.
- `tests/fx_coint/test_target_wellposedness.py`, `test_target_ceiling.py`,
  `test_target_report.py` — following the existing `test_*.py` pattern.

## Honesty guardrails

- Purged + embargoed CV throughout Stage A.
- Block-permutation null on **every** Stage-A number (non-negotiable — too many past
  results were null-indistinguishable).
- Own-history only; no cross-sectional leakage in the ceiling estimate.
- Label-noise via **real** ±1-tick barrier perturbation, not synthetic noise injection.

## Decisions locked

- Information set for ceiling: own-history only (panel = future extension).
- Ceiling estimation: bracketed (model LB + kNN-MI), both vs block-permutation null.
- Stage-C hard fail → skip Stage A (flag + skip, not always-run).
- Stage B (achievable best-effort) not rebuilt — existing IC/WFO scripts serve that role.

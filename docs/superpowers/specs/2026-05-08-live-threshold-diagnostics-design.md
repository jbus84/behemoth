# Live Threshold Diagnostics Design

## Context

EURUSD live prediction probability q90 fell from roughly 0.77 in late April to roughly 0.676 on May 7-8, while the live Rolling Threshold remained anchored near older seed and Warmup history. The initial evidence suggests lower recent `range_pips`, but the system must not assume this is normal Runtime Variance until it proves the local data path and threshold pool are correct.

This design is local-only. It uses governed local evidence and does not depend on external market data.

## Objective

Create a reproducible diagnostic that classifies the May 7-8 behavior as one of:

- `PARITY_BREACH`: Runtime State, Feature Computation, bar alignment, or Rolling Threshold reconstruction diverges from the governed contract.
- `THRESHOLD_DRIFT`: Feature Set parity passes, live probabilities are genuinely lower, and the current Rolling Threshold lags because older seed or Warmup rows dominate.
- `RUNTIME_VARIANCE`: Feature Set parity passes and May 7-8 is unusual but still inside local historical distribution bands.
- `MODEL_VALIDITY_CONCERN`: Feature Set parity passes, but the April Model Fit no longer produces enough useful May selections under governed Candidate States.
- `INCONCLUSIVE`: required evidence is missing or row alignment cannot be proven.

The first deliverable is a diagnostic report and machine-readable evidence, not a behavior change.

## Evidence Sources

Use only local governed sources:

- Runtime `audit_logs`
- Runtime `predict_evaluations`
- Runtime Tick Bars
- Raw Tick Data or existing Tick Bars for offline recomputation
- Velocity Dataset and Monthly WFO artifacts where available
- Candidate Catalog and Model Binding
- Feature Schema and Model Feature Contract

## Diagnostic Phases

### Phase 1: Provenance And Pool Audit

Reconstruct the exact Rolling Threshold pool used by live for each `symbol` and `candidate_uid`.

Capture:

- row count
- date span
- `run_id`
- source period classification: seed, Warmup, or live
- `pred_prob` q50, q75, q90, q95
- current live threshold
- threshold recomputed from the same pool

This phase directly tests whether the proposed 1,300 seed/Warmup rows versus 26 live rows explanation is true.

### Phase 2: Feature Set Parity

For May 7-8, recompute Tick Bars and Feature Set offline using the same `compute_feature_matrix_from_bars()` path. Compare the offline rows with live Runtime State rows.

Key comparison columns:

- `range_pips`
- `cost_est_pips`
- `ret_abs_z`
- `vel_abs_cost_units_h1`
- `spread_z`
- `tick_rate_z`
- `hl_first`
- `hl_first_mean_24`
- `hl_pos_frac_mean_24`

Stop condition: if Feature Set parity, Tick Bar alignment, or timestamp matching fails beyond tolerance, classify as `PARITY_BREACH` and do not evaluate threshold smoothing.

### Phase 3: Distribution Decomposition

Compare May 7-8 against prior local periods for EURUSD and the active Symbol Universe.

Break down the probability drop by:

- Feature Set distribution
- Candidate State mix
- time-of-day mix
- spread and cost behavior
- Tick Bar range behavior
- model probability quantiles

The report should make clear whether May 7-8 is symbol-specific or broad across the Symbol Universe.

### Phase 4: Rolling Threshold Replay

Replay the current live Rolling Threshold calculation exactly from `audit_logs`, then compare it with the Monthly WFO causal threshold behavior.

The comparison should identify:

- whether live can reproduce its own threshold value exactly
- whether live and Monthly WFO use equivalent history windows
- whether fallback behavior differs when recent history is thin
- whether seeded rows are weighted the same as live rows

This phase separates legitimate Threshold Drift from a Parity Breach in threshold mechanics.

### Phase 5: Threshold Estimator Bake-Off

Only run this phase if Phases 1-4 pass.

Evaluate offline alternatives:

- current 20-day equal-weight quantile
- shorter equal-weight windows
- recency-weighted quantile
- seed-decay after Warmup
- regime-conditioned threshold by volatility bucket

No production behavior changes should be made from this design alone. A follow-up implementation plan must define acceptance criteria before any estimator change is promoted.

### Phase 6: Model Validity Review

Replay May 1-8 with the April Model Fit and current Candidate Catalog.

Evaluate:

- selected signal count
- daily probability quantiles
- label outcomes where available
- whether useful selections vanish under governed Candidate States

If parity is clean but May behavior is materially weaker, classify as `MODEL_VALIDITY_CONCERN`.

## Outputs

Write a Markdown report and machine-readable artifacts:

- `docs/analysis/live_threshold_diagnostics/<run_id>_report.md`
- `data/analysis/live_threshold_diagnostics/<run_id>_summary.json`
- `data/analysis/live_threshold_diagnostics/<run_id>_threshold_pool.csv`
- `data/analysis/live_threshold_diagnostics/<run_id>_feature_parity.csv`
- `data/analysis/live_threshold_diagnostics/<run_id>_distribution_decomposition.csv`
- `data/analysis/live_threshold_diagnostics/<run_id>_threshold_estimators.csv`

The report must lead with:

- final classification
- one-paragraph explanation
- evidence completeness
- recommended next action: no change, fix parity bug, adjust Rolling Threshold design, or escalate Model Validity review

## Decision Rules

Classify as `PARITY_BREACH` if:

- Feature Set recomputation differs from live beyond tolerance
- Tick Bar alignment differs
- live threshold cannot be reconstructed from `audit_logs`
- required Candidate Catalog or Model Binding evidence conflicts with runtime usage

Classify as `THRESHOLD_DRIFT` if:

- Feature Set parity passes
- live probabilities are genuinely lower than the current pool
- current equal-weight Rolling Threshold materially lags because seed or Warmup rows dominate

Classify as `RUNTIME_VARIANCE` if:

- Feature Set parity passes
- Rolling Threshold replay passes
- May 7-8 is unusual but within local historical distribution bands

Classify as `MODEL_VALIDITY_CONCERN` if:

- parity passes
- alternative threshold behavior does not explain the issue
- April Model Fit produces materially weaker May selections under current governed Candidate States

Classify as `INCONCLUSIVE` if:

- local evidence is missing
- row alignment cannot be proven
- runtime and offline periods cannot be matched reliably

## Testing Strategy

Add targeted tests around the future diagnostic implementation:

- threshold pool reconstruction from synthetic `audit_logs`
- source period classification for seed, Warmup, and live rows
- Feature Set parity comparison with exact and tolerance-bound cases
- decision-rule classification for each terminal state
- estimator bake-off remains disabled when parity fails

## Non-Goals

- Do not change production Rolling Threshold behavior in this diagnostic.
- Do not use external market data.
- Do not recertify a model or promote a new Model Fit.
- Do not collapse `THRESHOLD_DRIFT`, `RUNTIME_VARIANCE`, and `MODEL_VALIDITY_CONCERN` into a single verdict.

## Usage

Example local run:

```bash
uv run python scripts/diagnose_live_thresholds.py \
  --db data/live_state.db \
  --symbol EURUSD \
  --run-id eurusd_20260508 \
  --start-ts 2026-05-01T00:00:00Z \
  --end-ts 2026-05-08T23:59:59Z \
  --lookback-days 20 \
  --execution-quantile 0.9 \
  --min-history 300 \
  --out-dir data/analysis/live_threshold_diagnostics
```

The script writes a Markdown report and CSV/JSON artifacts under the output directory. The classification is evidence-only and does not change production Rolling Threshold behavior.

# Path-aware directional model — Stage 1 design

**Date:** 2026-06-25
**Branch:** worktree-fx-sample-weights
**Status:** approved (design), pending implementation plan

## Motivation

Prior diagnostics (run inline, not committed) established two facts that reframe the
modeling objective:

1. **Models CAN boost the edge, but only per-symbol and de-diluted.** Single-feature
   per-symbol ridge nets EURUSD +3.3 / GBPUSD +3.2 bps (4/4 folds) vs the pooled
   30-feature ladder at +1.1 bps. The pooled, many-feature architecture was the
   problem — not "models are useless."
2. **A single-feature linear model is a deterministic rescaled copy of the raw
   signal.** `sign(mu) = -sign(ffd_zvol20)` on every event, so top-decile |mu|
   selects the identical trades as top-decile |raw|. Linear point-in-time models add
   zero new information over the raw feature.

The open question this spec answers: **does the path (sequence of bars leading into
an entry) carry directional information that point-in-time features miss?** If yes, a
sequence-aware model can beat the incumbent raw fade. If no, no sequence architecture
will help and we stop before building heavy infra.

## Horizon constraint (hard)

Gross edge exists only at longer triple-barrier horizons:

- N=30, N=50 (1000-tick bars): single-feature fade nets +0.6 to +3.3 bps per symbol.
- N=1,2,3: every strategy nets −0.6 to −1.0 bps, 0/4 folds positive — sub-cost,
  microstructure-noise dominated. **Excluded.** A sequence model cannot manufacture
  gross edge from a horizon that has none.

This spec targets **N ∈ {30, 50}** only.

## Approach: staged ladder

**Stage 1 (this spec):** path-aware model on the *flattened* W-bar window, using
models already in the env (sklearn MLP + HistGBM). Near-zero infra. Isolates whether
the path carries extra information vs point-in-time features.

**Stage 2 (gated, separate spec):** only if Stage 1 shows the path matters — install
torch (CPU, isolated uv venv) and build a recurrent (GRU) or causal-conv (TCN) model
to exploit the sequence structure properly. The numpy 2.4 / numba conflict that
blocked prior aeon attempts does not apply to torch.

## Inputs

For each event (entry bar index `e`), build a window of the **W preceding 1000-tick
bars** `[e-W+1 .. e]`. Each bar contributes a fixed channel set:

- per-bar log-return
- per-bar realized vol
- signed intra-bar momentum (`intra_bar_mom`)
- within-bar high/low position fraction (`hl_pos_frac`) — used as the range/structure
  channel in place of raw bar range, since it is directly available per bar from
  `build_all` without OHLC reconstruction

Flatten to a length `W × C` vector (C = 4). Sweep **W ∈ {16, 32, 64}**.

Feature scaling: standardize per-channel using train-fold statistics only (no
leakage), reusing the existing design-matrix conventions where applicable.

## Models (Stage 1)

- `MLPRegressor` (sklearn) on the flattened window.
- `HistGradientBoostingRegressor` on the flattened window (reuse the regularized
  hyperparameters already in `model_search.py`).

Target: forward triple-barrier return at the given N (signed return, consistent with
the existing `model_oos_pnl` directional convention).

## Benchmarks (same events, same folds)

1. **Point-in-time ridge / HistGBM** (current ladder) — the "does path help?"
   control. A path model must beat this to justify the window.
2. **Raw single-feature fade, top-decile** — the deployable incumbent.

## Evaluation (reuse existing harness — non-negotiable for comparability)

- `model_oos_pnl`: walk-forward, expanding folds, non-overlap, top-decile |mu|
  selection, net of **per-symbol realistic cost**.
- `fold_block_bootstrap_ci`: report net bps, bootstrap CI [lo, hi], pNeg, folds+,
  sym+.
- **Per-symbol** evaluation (primary, per the diagnostic) plus a standardized-pool
  readout for reference.
- Sweep grid: {N ∈ 30,50} × {W ∈ 16,32,64} × {MLP, HistGBM} × {per-symbol}.

## Gate to Stage 2

Promote to a torch GRU/TCN **only if** the flattened-window model beats the
point-in-time benchmark by a margin whose fold-level block-bootstrap CI excludes zero,
on a **majority of (symbol, N) cells**. Otherwise: documented NO-GO — the path carries
no extra directional information at these horizons — and we stop.

## Files

- New: `scripts/fx_coint/path_window_model.py`
- New: `tests/fx_coint/test_path_window_model.py`
- Reuses: `feature_ic_definitive.build_all`, `triple_barrier.triple_barrier_core`,
  `sample_weights.event_weights`, `pnl_walkforward.model_oos_pnl`,
  `pnl_walkforward.fold_block_bootstrap_ci`, `model_search.build_design`.

## Out of scope

- N=1,2,3 (gross-dead).
- Cross-symbol pooling as the primary readout (reference only).
- torch / GRU / TCN (Stage 2, gated).
- Regime-conditional ensembles and per-bar ffd channels (deferred; can be added if
  Stage 1 is promising but ambiguous).

## Success criteria

A clear, bootstrap-backed verdict on whether path structure adds directional
information over point-in-time features at N=30/50, with per-symbol net-bps tables
comparable to the existing harness output, and a go/no-go decision on Stage 2.

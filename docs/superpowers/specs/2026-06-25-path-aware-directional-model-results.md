# Path-aware directional model — Stage 1 results & Stage-2 gate verdict

**Date:** 2026-06-25
**Driver:** `scripts/fx_coint/path_window_model.py`
**Spec:** `docs/superpowers/specs/2026-06-25-path-aware-directional-model-design.md`
**Plan:** `docs/superpowers/plans/2026-06-25-path-aware-directional-model.md`

## Verdict: 🛑 NO-GO for Stage 2 (torch GRU/TCN)

The W-bar **path** into an entry does **not** add directional information over
point-in-time features at N=30/50. Window models are noisier than, and generally
worse than, both the point-in-time benchmark and the raw single-feature fade
incumbent (+0.608 bps net at N=50). Do not build the torch sequence model.

## Method

- Per-symbol (primary) + pooled (reference), 5 majors, walk-forward 5 expanding
  folds, non-overlap, top-decile |mu| gating, per-symbol realistic cost.
- Identical sampled events for window vs point-in-time (shared `sample_events`), so
  the comparison isolates the input representation.
- Window inputs: flattened `W×4` path (log-return, vol, intra_bar_mom, hl_pos_frac),
  W ∈ {16,32,64}. Models: scaled-MLP, regularized HistGBM. Benchmark: same two model
  classes on the existing 30-feature point-in-time design matrix.
- net bps / fold-level block-bootstrap CI / pNeg / folds+ reported per cell.

**Caveat (conservative for the verdict):** the MLP arm is fit *unweighted*, while
HistGBM (both window and point-in-time) and the raw-fade incumbent use sample weights.
This handicaps only the MLP rows and can therefore only *understate* the path's value.
The NO-GO is carried by the weighted HistGBM arm alone (it degrades monotonically as W
grows), so the unweighted MLP does not affect the conclusion.

## Headline (pooled net bps)

| N  | pt mlp | pt histgbm | win16 mlp | win32 mlp | win64 mlp | win16 gbm | win32 gbm | win64 gbm |
|----|--------|-----------|-----------|-----------|-----------|-----------|-----------|-----------|
| 30 | −0.037 | −0.353    | −0.129    | +0.121    | −0.333    | −0.916    | −1.103    | −0.594    |
| 50 | −0.443 | −0.235    | −1.137    | −1.162    | −0.782    | −1.709    | −0.930    | −1.945    |

Incumbent for context: **raw single-feature fade (ffd_zvol20), N=50, +0.608 bps,
bootCI [+0.15,+1.24], 4/4 folds** (from prior `pnl_walkforward` runs). Every window
pooled cell is below it; at N=50 the window is materially worse.

## Stage-2 gate evaluation

Gate (from spec): window beats the point-in-time benchmark of the same model/N by a
margin whose fold-level bootstrap CI excludes zero, on a **majority of the 10
(symbol, N) cells**.

- Window cells that are positive with a bootstrap CI excluding zero **and** beat
  point-in-time: only **2** —
  - AUDUSD W16/N30: +3.454 [+0.27,+7.78], 3/4 folds (pt mlp AUDUSD: +0.011).
  - USDCHF W16/N50: +1.180 [+0.13,+2.23], 4/4 folds (pt mlp USDCHF: +0.138).
- Both are **isolated and non-monotone in W** (AUDUSD N30 mlp: W16 +3.45 → W32 −1.88 →
  W64 +0.53; USDCHF N50 mlp positive at all W but CI excludes zero only at W16). Across
  60 window cells, 2 scattered survivors is consistent with multiple-comparison noise.
- **2/10 (symbol, N) cells ≠ majority → gate FAILS.**

## Interpretation

This confirms the prior diagnostic that the surviving FX edge is a **single-feature
extreme-fade**, not a path/structure phenomenon. Adding the W-bar path multiplies the
input dimensionality (up to 256 features at W=64) and **dilutes** the one weak channel
rather than enriching it — exactly the feature-dilution failure seen with the pooled
30-feature ladder. HistGBM degrades monotonically as W grows (more noise columns);
the MLP is noisier still. A recurrent/attention model would inherit the same
signal-to-noise problem: there is no path structure to exploit at these horizons.

## Where the edge actually lives (unchanged)

- Raw single-feature fade, per-symbol, N=50, top-decile gating: net +0.608 bps,
  CI excludes zero. This remains the deployable incumbent.
- Modeling effort should stop chasing architecture and instead pursue: (1) execution
  verification (tick-exact maker fills on the +0.6 bps fade), or (2) orthogonal breadth
  (index/rate futures) — not more model capacity over the same spot-FX features.

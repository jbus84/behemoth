# Offset Tick-Bar Robustness Method

## Objective

Measure whether the active `100`-tick OCO pipeline is materially sensitive to fixed-tick bar phase shifts and reduced runtime warmup.

## Method

- Rebuild `100`-tick bars from raw HistData after dropping the first `k` source ticks globally.
- Recompute the repo-side Stage 02 to Stage 08 path for each `symbol x offset` using the offset-defined bars only.
- Treat `offset=0` as the repo baseline for that symbol.
- Compare each offset to baseline on selected rows, trade rows, reduced-core state overlap, execution realism, and confidence-bound performance.
- Run a sampled API confirmation slice on offsets `0,25,50,75` over the validated Stage 12 window `2025-07-07` to `2025-07-09`.
- Run a sampled warmup sweep on the same offsets using `73,145,217,289,400` bars.

## Warmup Interpretation

Feature warmup comes from `src/behemoth/core/features.py`:

- minimum usable warmup: `73` bars
- full-precision warmup: `289` bars

For `t100`, that maps to:

- `7300` ticks
- `28900` ticks

The warmup study reports:

- `first_feature_available_bar`: first live bar where minimum usable features are available
- `first_full_precision_bar`: first live bar where full-precision features are available
- plateau warmup: the minimum sampled warmup with zero signal drift versus `289` bars and gross mean drift within `0.05` pips

## Classification

- `stable`: no advisory degradation, no sampled API failures, warmup plateau observed
- `mildly_phase_sensitive`: repo pipeline completes but one or more advisory thresholds breach
- `materially_phase_sensitive`: sampled API parity fails, pipeline fails for one or more offsets, qualifying states disappear, or warmup plateau is not observed

## Outputs

- `data/analysis/tick_opportunity_mining/offset_robustness/<SYMBOL>_offset_robustness_by_offset.csv`
- `data/analysis/tick_opportunity_mining/offset_robustness/<SYMBOL>_offset_state_overlap.csv`
- `data/analysis/tick_opportunity_mining/offset_robustness/<SYMBOL>_warmup_sensitivity.csv`
- `data/analysis/tick_opportunity_mining/offset_robustness/<SYMBOL>_api_offset_confirmation.csv`
- `docs/analysis/<symbol>_offset_tickbar_robustness_report.md`

## Policy

This study is advisory-first in v1.

It is designed to expose phase sensitivity before deployment decisions, not to create a new hard governance gate yet.

# Cross-Symbol Alignment Infrastructure

**Date:** 2026-05-19
**Status:** Approved (design)
**Roadmap:** Sub-project 0 of the cross-symbol mining effort (foundation for
families A — dollar-factor residual, B — cross-sectional dispersion,
C — lead-lag follow).

## Problem

Every mining family to date (`oco_first_touch`, `directional`,
`double_touch`, `pullback`, `no_touch`) looks at a *single symbol's own
path*. The next research direction compares the 6 FX majors against each
other to find a symbol behaving as an outlier relative to its peers — a
divergence the market may correct.

Three families are planned on top of this:

- **A — dollar-factor residual:** decompose each symbol's move into a common
  USD-factor component and an idiosyncratic residual; bet the residual
  reverts.
- **B — cross-sectional dispersion:** rank the symbols' returns each aligned
  bar; trade the rank extreme.
- **C — lead-lag follow:** when one symbol moves, enter a lagging peer.

All three need the same thing first: bars from all 6 symbols available
together, aligned in time. The mining pipeline has no cross-symbol path —
`run()` loads exactly one symbol. This sub-project builds that shared seam.
It is infrastructure, not research: no family, no candidates, no edge claim.

## Goals

- A reusable utility that, given a target symbol and a `bar_ticks` setting,
  returns the target symbol's own tick frame enriched with as-of-joined peer
  columns and a synthetic mean-market (USD) measure.
- Strictly look-ahead-free alignment.
- The market measure available under three construction methods so the
  downstream families can compare them.

## Non-Goals

- No mining family, no candidate rows, no `run()`/`_mine_frame_pair` changes.
  Families A/B/C are separate sub-projects that consume this utility.
- No change to `_prepare_frame` or the single-symbol path.
- No clock-time resampling — see Design §1.
- No net-of-cost or edge evaluation — this sub-project produces data only.

## Design

### 1. Why no fixed clock grid

Tick bars are volatility-clock sampled: each bar represents roughly equal
market activity, which keeps per-bar returns far closer to i.i.d. and
stationary. Resampling to a fixed clock grid would reintroduce exactly what
the pipeline is built to avoid — fat tails, volatility clustering, dead
low-activity bars — and would discard tick-rate / bar-velocity signals. The
alignment is therefore tick-native: no resampling, no global clock.

### 2. Alignment model — per-target, backward as-of join

There is no single global reference clock. Each downstream family trades one
specific symbol, so alignment is anchored to *that* symbol:

- The target symbol's own tick bars are the row axis, unchanged. Entry
  timing, OHLC, and the existing barrier/gross machinery are untouched.
- For each target bar closing at time `T`, every peer symbol contributes its
  most-recent **completed** bar with `close_ts ≤ T`. This is a pandas
  `merge_asof` with `direction='backward'` on `close_ts`.
- Because every joined value comes from a bar that closed at or before `T`,
  it was knowable at `T` — the join is look-ahead-free by construction.

The target symbol keeps its full OHLC columns. Peers contribute only the
columns the families need (see §3) — not full OHLC — to keep the frame lean.

### 3. Cross-symbol return unit and sign alignment

Raw pip returns are not comparable across symbols: the JPY pip is `0.01`
versus `0.0001` for the others, and price levels differ. All cross-symbol
quantities therefore use the existing **volatility-normalised return**
column `ret_z` (sourced from `vel_z_h1` in `_prepare_frame`), which puts all
6 symbols on one scale.

For a coherent "USD strength" measure the majors must be sign-aligned,
because USD sits on different sides of the pair:

| Symbol | USD side | Sign |
|---|---|---|
| EURUSD | quote | −1 |
| GBPUSD | quote | −1 |
| AUDUSD | quote | −1 |
| USDJPY | base | +1 |
| USDCAD | base | +1 |
| USDCHF | base | +1 |

A symbol's **USD-aligned return** is `sign · ret_z`. When EURUSD falls and
USDJPY rises, both yield a positive USD-aligned return — USD strengthened.

### 4. The synthetic mean-market measure — three methods

The enriched frame carries three market-measure columns, all computed from
the as-of-aligned cross-section of USD-aligned `ret_z` values:

- **`mkt_all6`** — equal-weighted mean of all 6 USD-aligned returns. One
  shared series; the target symbol is included in its own benchmark.
- **`mkt_loo`** — equal-weighted mean of the 5 USD-aligned returns
  *excluding the target symbol*. Avoids the target contaminating its own
  benchmark — important for the residual family, where including the target
  mechanically shrinks its residual by roughly `1/6`.
- **`mkt_pca`** — the first principal component of the 6 symbols'
  USD-aligned returns. The PC weights are fit on a strictly-trailing rolling
  window (only bars with `close_ts` before the current bar), so the factor
  is look-ahead-free. Captures the dominant co-movement without assuming
  equal weights.

Carrying all three lets families A/B/C select one or mine across the choice.

### 5. Interface

A single entry point:

```
build_cross_symbol_frame(
    target_symbol: str,
    bar_ticks: int,
    dataset_dir: Path,
    horizons: list[int],
) -> pd.DataFrame
```

- Loads each of the 6 symbols' `{symbol}_{bar_ticks}tick_velocity.parquet`
  via the existing `_prepare_frame`.
- Performs the backward as-of joins of peer `ret_z` (USD-aligned) onto the
  target frame.
- Computes `mkt_all6`, `mkt_loo`, `mkt_pca`.
- Returns the target frame with the new columns appended; the original
  columns (OHLC, `close_ts`, features) are preserved unchanged.

Added columns: one USD-aligned `ret_z` per peer (`xs_ret_z__{peer}`), and
`mkt_all6`, `mkt_loo`, `mkt_pca`. The train/test split stays downstream and
unchanged (by `close_ts` year), applied by whichever family consumes the
frame.

A missing peer file is a hard error — a coherent cross-section requires all
6 symbols. (This matches the pipeline's fail-loud posture.)

### 6. Look-ahead discipline

- Peer joins are `merge_asof` `direction='backward'` only.
- The PCA fit window is strictly trailing: the covariance for the bar at
  index `i` uses only bars `< i`.
- No target-bar value is ever derived from a peer bar that closed after the
  target bar.

## File Structure

- `scripts/cross_symbol.py` — new module: `build_cross_symbol_frame`, the
  sign-alignment table, the as-of join, and the three market-measure
  constructions.
- `tests/test_cross_symbol.py` — new test file.

## Testing

- **Alignment correctness** — for a constructed multi-symbol fixture, each
  peer column at target time `T` equals that peer's last bar with
  `close_ts ≤ T`.
- **No look-ahead** — a peer bar that closes after `T` never appears in the
  target row at `T`; shifting a peer's future bars does not change earlier
  aligned rows.
- **Sign alignment** — the synthetic USD index (`mkt_all6`) correlates
  positively with `USDJPY`'s raw move and negatively with `EURUSD`'s.
- **Leave-one-out** — `mkt_loo` for target `X` is independent of `X`'s own
  returns; perturbing only `X` leaves `mkt_loo` unchanged.
- **PCA trailing fit** — the PC weights for bar `i` are unchanged when bars
  `≥ i` are altered (fit uses only the trailing window).
- **Three distinct methods** — on non-degenerate data `mkt_all6`,
  `mkt_loo`, and `mkt_pca` are not identical series.
- **Missing peer** — a missing symbol file raises a clear error.

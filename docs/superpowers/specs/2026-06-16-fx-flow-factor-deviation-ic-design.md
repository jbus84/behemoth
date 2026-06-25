# FX flow-factor deviation — gross predictability probe (Step 1)

**Date:** 2026-06-16
**Status:** design approved, pre-implementation
**Predecessor:** `docs/analysis/fx_usd_factor_residual_STALE_BAR_KILL.md` — intraday
*price*-residual reversion is a NO-GO at retail cost (a stale-bar artifact). This
investigation applies the same USD-factor decomposition to **quote flow** instead
of price.

## Objective

Measure, **gross of cost and before building any strategy**, whether a *deviation in
normalised quote flow* — the PCA residual after extracting a USD-flow factor — carries
any predictive edge over forward price. Sign (reversion vs continuation) is to be
discovered empirically, not assumed. Deliver a go/no-go on "does the signal exist,"
with the horizon where it is strongest as a key output.

This is the FX analog of the crypto order-flow XS signal
(`project_crypto_flow_xs_signal`), which showed public OFI predicting cross-sectional
returns gross IS+OOS.

## Non-goals (Step 1)

- No strategy construction, no cost model, no tick-exact fills, no position sizing.
- No assumption that flow "leads" price as momentum. We study deviations, not direction.

## Data

- **Source:** raw dukascopy quote ticks (`~/Desktop/dukascopy_ticks`, 6 USD majors,
  2018–2026). Quote-only: `timestamp, bid, ask, mid, spread`. **No trade sizes** — spot
  FX has no consolidated volume, so flow must be a quote-based proxy.
- **Bars:** a **1-minute base grid**, built correctly (last tick before each boundary;
  the validated `build_rawtick_timebars.py` machinery). No tick-count→time resampling
  anywhere (that was the prior fatal flaw).
- Pairs and USD orientation (negate XXXUSD so + = USD buying):
  EURUSD −, GBPUSD −, AUDUSD −, USDJPY +, USDCHF +, USDCAD +.

## Signal construction

### Flow proxies (per pair, per 1-min bar)

Two literature-grounded sizeless quote-flow measures, computed from the raw tick stream
within each bar:

1. **Tick-rule signed flow** — `Σ sign(Δmid)` over the bar, normalised by tick count.
   Net up- vs down-ticks (Lee-Ready without size).
2. **Quote OFI (Cont-style, sizeless)** —
   `Σ [ I(bid↑) − I(bid↓) − I(ask↑) + I(ask↓) ]` across consecutive ticks in the bar.
   Bid rising / ask falling = buy pressure; bid falling / ask rising = sell pressure.

Conditioning/cross-check variables (not primary signals): **tick intensity**
(ticks/min), and the pre-engineered `quote_revisions` / `bar_return_sign` from the
1000-tick bar data as an independent sanity check.

### Normalisation

Each pair's flow proxy is **causally z-scored** with an EWMA mean/std (look-ahead-free)
before PCA, so the cross-sectional decomposition is not dominated by per-pair scale or
volatility differences.

### USD-factor decomposition

On the cross-section of the 6 oriented, normalised flows at each `t`:

- **USD-flow factor** = cross-pair mean (≈PC1; estimation-free → no look-ahead).
- **Residual flow** `residual_flow_{i,t}` = oriented normalised flow − factor = the
  *deviation*.
- Optional **2-factor PCA** (dollar + risk), fit on the IS window only and applied OOS —
  attempted **only if** the 1-factor version shows life.

### Signal candidates

- (a) **|residual flow|** — a pair whose normalised flow dislocates from the dollar-flow
  factor (cross-sectional deviation).
- (b) **USD-flow factor extreme** — the dollar-flow itself stretched (time-series
  deviation).

## Measurement protocol

### Targets

Forward price log-return over horizons **h ∈ {1, 5, 15, 30, 60} min**, strictly
`t → t+h`:
- per pair (for the residual-flow signal),
- dollar-basket oriented return (for the USD-flow-factor signal).

### Metrics (gross, sign empirical)

1. **IC** = corr(signal_t, fwd_ret_{t,h}) — per pair, pooled, per horizon. Sign reveals
   continuation (+) vs reversion (−).
2. **Deviation-tail conditional return** — bucket by |residual flow| (deciles + a fixed
   band), report mean forward move. Direct "does an outlying flow deviation carry edge"
   test, mirroring the price-band analysis.
3. **Decomposition** — USD-factor signal vs residual signal reported separately, with
   t-stat and hit-rate.
4. **Price baseline** — the *price*-residual IC at the same horizons, run alongside, so
   we see whether flow deviation predicts price **where price-deviation didn't**, and
   whether the two are independent or redundant.

### Look-ahead guards

- Flow at `t` uses only ticks with timestamp ≤ `t`.
- EWMA normalisation is causal.
- USD-flow factor is the contemporaneous cross-pair mean (no future data, no estimation).
- Forward return strictly `> t`.
- Any 2-factor PCA fit on the IS window only.

### IS/OOS and multiplicity

- Split **2018–2022 in-sample / 2023–2026 out-of-sample**.
- Tests span 2 proxies × {factor, residual} × 5 horizons × 6 pairs — many — so the bar
  is **pooled |t| with IS→OOS sign stability** (BH-FDR over the pooled set), not a lone
  in-sample hit. Overlapping forward windows → use non-overlapping sampling or
  Newey-West / block-aware t-stats.

## Go / No-Go (set in advance)

- **GO → build strategy** only if a flow-deviation signal has pooled gross IC with stable
  IS→OOS sign **and** the implied conditional move at its best horizon is **≳ the
  ~0.7 bps round-trip Razor cost** (room to clear the wall later).
- **PARK** → gross signal real (|t| ~2–3) but implied move < cost: document as
  "predictable but sub-cost," do not build.
- **NO-GO** → IC ≈ 0 or sign flips IS→OOS.

The most likely honest outcome, given the thread's history, is gross-positive but
sub-cost; the bar for proceeding is explicitly gross **and** plausibly cost-clearing.

## Deliverables

- One probe script (e.g. `scripts/fx_coint/flow_factor_deviation_ic.py`) producing the
  IC tables, deviation-tail conditional returns, and the price baseline.
- A short report `docs/analysis/fx_flow_factor_deviation_ic.md` with the
  horizon × signal × pair IC, IS/OOS, deviation-tail returns, the price baseline, and the
  go/no-go verdict.
- No strategy or cost build in Step 1.

## Reuse / dependencies

- Reuses `build_rawtick_timebars.py` (extend to emit per-bar flow proxies alongside the
  mid).
- Mirrors the decomposition structure of `usd_factor_residual_probe.py` but on flow.
- Implementation will run in its own git worktree.

# FX flow-factor deviation — gross predictability (Step 1 results)

**Question:** does a deviation in normalised quote flow (the USD-factor residual, or
the USD-flow factor itself) predict forward price, gross of cost?

**Verdict: PARK (predictable but ~35× sub-cost).** A real, IS→OOS-stable, theory-consistent
flow signal exists at 1-minute horizon for the tick-rule proxy — but its economic
magnitude is ±0.01–0.02 bps, against a ~0.70 bps round-trip Razor cost. The
quote-OFI proxy carries no predictive power at all. No tradeable edge; do not build a
strategy.

## Setup

Raw-tick 1-min flow bars (`build_flow_bars.py`, ~3.05M aligned bars across the 6 USD
majors, 2018-2026), two sizeless quote-flow proxies (tick-rule signed flow; Cont-style
quote OFI), causal EWMA z-score (span 240 = 4h), estimation-free USD-flow factor +
residual. Targets: forward oriented price log-return at h ∈ {1,5,15,30,60} min. ICs use
non-overlapping sampling (within each pair, then pooled). IS ≤ 2022, OOS 2023-2026.
BH-FDR over all 30 tests per proxy. `tail_bps` = mean forward move in the top-decile of
|signal|, oriented by sign(signal) (+ = continuation), in basis points.

## Results — quote OFI proxy

Flow factor and residual are indistinguishable from zero at every horizon; **nothing
flow-based survives BH-FDR**. Only the price-residual baseline is significant.

| signal     | h1 IS IC (t) | h1 OOS IC (t) | best tail_bps | FDR |
|------------|:------------:|:-------------:|:-------------:|:---:|
| factor     | +0.0007 (+1.0) | +0.0012 (+1.3) | +0.16 | no |
| residual   | +0.0001 (+0.3) | +0.0006 (+1.7) | +0.09 | no |
| price_res  | −0.0237 (−78.6) | −0.0175 (−47.6) | −0.17 | yes |

## Results — tick-rule proxy

A genuine, IS→OOS-stable signal at **h1 only**, decaying to noise by h15:

| signal     | h1 IS IC (t) | h1 OOS IC (t) | sign | tail_bps | FDR |
|------------|:------------:|:-------------:|:----:|:--------:|:---:|
| factor     | +0.0091 (+12.3) | +0.0106 (+11.7) | continuation | +0.02 | yes |
| residual   | −0.0047 (−15.5) | −0.0052 (−14.2) | reversion | −0.01 | yes |
| price_res  | −0.0237 (−78.6) | −0.0175 (−47.6) | reversion | −0.17 | yes |

- **USD-flow factor → continuation** (+): the common dollar order-flow pushes price the
  same way at 1 min — informed.
- **Residual flow → reversion** (−): idiosyncratic, pair-specific flow deviations
  overshoot and revert — uninformed/liquidity noise. A clean, sensible decomposition.
- By h5 the factor is weak (IC +0.003-0.004) and the residual still mildly reverts; by
  h15+ both are noise.

## Interpretation: why this is dead, not just small

1. **Economic magnitude.** The best deviation-tail move is ±0.02 bps. Round-trip cost is
   ~0.70 bps. That is a **~35× shortfall** — not a tuning gap. There is no horizon or
   selection where the gross move approaches cost.
2. **The only "flow" signal is the part that echoes price.** Tick-rule flow is
   `sign(Δmid)` compressed, so it is mechanically correlated with the recent price path;
   its residual "reversion" overlaps the price-residual reversion (which is itself
   sub-cost). The price-*independent* quote-OFI shows **zero** edge — i.e. there is no
   genuinely flow-specific predictive information beyond what price already contains.
3. **Price baseline validates the probe.** It recovers the known intraday price-residual
   reversion (t up to −79) at a tail of ≤0.17 bps — significant but sub-cost, exactly the
   conclusion of `fx_usd_factor_residual_STALE_BAR_KILL.md`.

## Verdict (against the spec's go/no-go)

- Gross signal exists and is IS→OOS stable (tick-rule factor/residual at h1) → clears the
  "does a signal exist" bar.
- Implied move (≤0.02 bps) is **far below ~0.70 bps cost** → fails the "plausibly
  cost-clearing" bar by ~35×.
- **→ PARK.** Predictable but sub-cost. Do not proceed to a strategy build.

The retail-FX intraday cost wall holds once more, now confirmed on order-flow as well as
price. The surviving FX edge remains weekly+ (`project_fx_weekly_meanreversion_lead`).

## Reproduce

```
PYTHONPATH=. uv run python scripts/fx_coint/build_flow_bars.py            # cache 1-min flow bars
PYTHONPATH=. uv run python scripts/fx_coint/flow_factor_deviation_ic.py flow_ofi
PYTHONPATH=. uv run python scripts/fx_coint/flow_factor_deviation_ic.py flow_tick
```

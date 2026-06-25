# USD-factor residual reversion — correction: the intraday edge was a stale-bar artifact

**Status: NO-GO at retail cost.** This supersedes the positive intraday results in
`fx_usd_factor_residual_reversion_report.md` and PR #336 (the +0.75 bps walk-forward
and the +1.32 bps tick-exact headline).

## Two compounding flaws

1. **Look-ahead from open-time truncation.** All scripts bucketed 1000-tick bars to
   15m/30m by `timestamp` (the bar's *open*) while storing its *close* price. EURUSD
   1000-tick bars have median duration 10.5 min (p95 38 min), so the close stamped on
   bar `t` routinely materialised inside bar t+1's window — real forward leakage.
   Fixing to `close_ts` cut the mid-bar walk-forward from +0.75 → +0.26 bps.

2. **Tick-count bars resampled into time bars (the fatal one).** Even with `close_ts`,
   a "15m close" built from 1000-tick bars is the last *1000-tick bar's* close, which is
   **median 5.5 min stale** vs the true 15m boundary (p75 9.2, p95 13.7 min), and the
   staleness is volatility-endogenous (quiet markets → longer bars → staler). This
   manufactures mean-reversion between consecutive ragged sample points.

## Evidence: gross reversion decays as bars get fresher

True time bars were rebuilt from raw dukascopy ticks (last tick before each boundary,
~0 staleness; `build_rawtick_timebars.py`). Gross close-to-close reversion, 30m:

| source                       | EURUSD gross | USDCHF gross | staleness |
|------------------------------|:------------:|:------------:|:---------:|
| 1000-tick → time (original)  |    +0.93     |    +1.55     | 5.5 min   |
| 100-tick → time              |    +0.50     |    +0.55     | 48 s      |
| **raw-tick → time (honest)** |  **+0.40**   |  **+0.51**   | ~0        |

Monotonic decay with fresher bars = textbook staleness artifact.

## Definitive result (true raw-tick bars, real cTrader Razor cost: 0.60 bps RT
commission + published avg spread)

Net bps/trade, top-decile |1-factor residual| fade, enter k+1 / exit k+2:

| pair   | 30m net | 15m net | positive years /9 |
|--------|:-------:|:-------:|:-----------------:|
| EURUSD | −0.29   | −0.42   | 2 / 0             |
| GBPUSD | −0.31   | −0.45   | 2 / 1             |
| AUDUSD | −0.51   | −0.58   | 0 / 0             |
| USDCHF | −0.52   | −0.71   | 1 / 0             |
| USDCAD | −0.62   | −0.78   | 1 / 0             |
| USDJPY | −0.93   | −0.83   | 0 / 0             |

Every pair, both frequencies, all-hours **and** liquid-hours 7–16 UTC: net-negative.
True gross reversion (~0.3–0.5 bps at 30m) is real but sits below the ~0.7–1.0 bps
Razor cost on every pair.

## Verdict & lesson

The intraday USD-factor residual reversion edge does not exist at retail cost once the
bar clock is honest. Triangulated by two independent honest-timing builds (100-tick
bars and raw ticks) both killing it, versus the single stale 1000-tick build that
showed it.

**Lesson: never resample tick-count bars into time bars.** A time bar's close must be
the last *tick* before the boundary, not the last *tick-count bar's* close (stale by
~half a tick-bar duration). Build time bars from raw ticks.

## Reproduce

```
python scripts/fx_coint/build_rawtick_timebars.py            # cache raw-tick 15m/30m bars
python scripts/fx_coint/usd_factor_rawtick_cost.py 30m       # definitive NO-GO
python scripts/fx_coint/usd_factor_rawtick_cost.py 30m liquid
python scripts/fx_coint/usd_factor_pepperstone_cost.py 30m 100tick   # 100-tick cross-check
python scripts/fx_coint/usd_factor_tickexact_fill_closets.py 30m     # look-ahead (open vs close_ts)
```

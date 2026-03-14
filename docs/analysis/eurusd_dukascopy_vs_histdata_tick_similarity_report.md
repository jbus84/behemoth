# EURUSD Dukascopy vs HistData Tick Similarity Report

## Window

- Generated: `2026-03-13T13:51:37.663253+00:00`
- Reference root: `/Users/danielfisher/Desktop/dukascopy_ticks`
- Candidate root: `/Users/danielfisher/Desktop/tick`
- Bar size for cadence diagnostics: `100` ticks

## Headline Findings

- `EURUSD` as stored: minute-return correlation `0.0093`; candidate/reference row ratio `0.6522`; mean spread `0.426` vs `0.334` pips.
- `EURUSD` after lag correction: minute-return correlation `0.9950`; minute mid MAE `0.079` pips; hourly coverage ratio mean `0.997`.
- `EURUSD` `201801` inferred whole-hour lag set: `5`.
- `EURUSD` `201802` inferred whole-hour lag set: `5`.
- `EURUSD` `201803` inferred whole-hour lag set: `4,5`.
- `EURUSD` `201804` inferred whole-hour lag set: `4`.
- `EURUSD` `201805` inferred whole-hour lag set: `4`.
- `EURUSD` `201806` inferred whole-hour lag set: `4`.

## Overall Summary

| symbol   | month   | lens          |   candidate_to_reference_row_ratio |   minute_return_corr |   minute_mid_mae_pips |   minute_spread_mae_pips |   hourly_coverage_ratio_mean |   seconds_per_bar_mean_delta |
|:---------|:--------|:--------------|-----------------------------------:|---------------------:|----------------------:|-------------------------:|-----------------------------:|-----------------------------:|
| EURUSD   | OVERALL | as_is         |                           0.652174 |           0.00930699 |            17.6308    |                 0.234631 |                     0.962403 |                      64.4459 |
| EURUSD   | OVERALL | lag_corrected |                           0.652953 |           0.99503    |             0.0787762 |                 0.164967 |                     0.996874 |                      64.4575 |

## Month-by-Month Summary

| symbol   |   month | lens          |   candidate_to_reference_row_ratio |   minute_return_corr |   minute_mid_mae_pips |   minute_spread_mae_pips |   hourly_coverage_ratio_mean |   seconds_per_bar_mean_delta |
|:---------|--------:|:--------------|-----------------------------------:|---------------------:|----------------------:|-------------------------:|-----------------------------:|-----------------------------:|
| EURUSD   |  201801 | as_is         |                           0.61905  |           0.00839019 |            21.6128    |                 0.203677 |                     0.961543 |                      68.5463 |
| EURUSD   |  201801 | lag_corrected |                           0.617319 |           0.99629    |             0.0768709 |                 0.146488 |                     0.99909  |                      69.0294 |
| EURUSD   |  201802 | as_is         |                           0.649402 |           0.00480538 |            20.6524    |                 0.210853 |                     0.957222 |                      56.279  |
| EURUSD   |  201802 | lag_corrected |                           0.650217 |           0.995504   |             0.0791167 |                 0.146044 |                     0.998281 |                      56.0272 |
| EURUSD   |  201803 | as_is         |                           0.633585 |           0.017171   |            16.4457    |                 0.246372 |                     0.963158 |                      69.7008 |
| EURUSD   |  201803 | lag_corrected |                           0.636037 |           0.99285    |             0.0859857 |                 0.174538 |                     0.994741 |                      69.1578 |
| EURUSD   |  201804 | as_is         |                           0.569282 |           0.0115281  |            12.5161    |                 0.261594 |                     0.96559  |                      99.4363 |
| EURUSD   |  201804 | lag_corrected |                           0.569065 |           0.99485    |             0.0759018 |                 0.180932 |                     0.994969 |                      99.5618 |
| EURUSD   |  201805 | as_is         |                           0.748586 |           0.0127598  |            16.7087    |                 0.251238 |                     0.968575 |                      37.8052 |
| EURUSD   |  201805 | lag_corrected |                           0.748342 |           0.994959   |             0.0781186 |                 0.171645 |                     0.996794 |                      37.7799 |
| EURUSD   |  201806 | as_is         |                           0.70108  |          -0.00818133 |            18.3258    |                 0.229533 |                     0.952682 |                      48.9371 |
| EURUSD   |  201806 | lag_corrected |                           0.709018 |           0.99646    |             0.0745646 |                 0.173161 |                     0.997925 |                      48.9149 |

## Lag Schedule Snapshot

| symbol   |   month | date_utc                  |   inferred_lag_hours |   best_corr | lag_source    |
|:---------|--------:|:--------------------------|---------------------:|------------:|:--------------|
| EURUSD   |  201801 | 2018-01-01T00:00:00+00:00 |                  nan |  nan        | unresolved    |
| EURUSD   |  201801 | 2018-01-02T00:00:00+00:00 |                    5 |    0.994931 | inferred      |
| EURUSD   |  201801 | 2018-01-03T00:00:00+00:00 |                    5 |    0.994806 | inferred      |
| EURUSD   |  201801 | 2018-01-04T00:00:00+00:00 |                    5 |    0.995446 | inferred      |
| EURUSD   |  201801 | 2018-01-05T00:00:00+00:00 |                    5 |    0.996984 | inferred      |
| EURUSD   |  201801 | 2018-01-06T00:00:00+00:00 |                    5 |  nan        | carry_forward |
| EURUSD   |  201801 | 2018-01-07T00:00:00+00:00 |                    5 |  nan        | carry_forward |
| EURUSD   |  201801 | 2018-01-08T00:00:00+00:00 |                    5 |    0.993674 | inferred      |
| EURUSD   |  201801 | 2018-01-09T00:00:00+00:00 |                    5 |    0.994744 | inferred      |
| EURUSD   |  201801 | 2018-01-10T00:00:00+00:00 |                    5 |    0.996582 | inferred      |
| EURUSD   |  201801 | 2018-01-11T00:00:00+00:00 |                    5 |    0.99678  | inferred      |
| EURUSD   |  201801 | 2018-01-12T00:00:00+00:00 |                    5 |    0.997408 | inferred      |
| EURUSD   |  201801 | 2018-01-13T00:00:00+00:00 |                    5 |  nan        | carry_forward |
| EURUSD   |  201801 | 2018-01-14T00:00:00+00:00 |                    5 |  nan        | carry_forward |
| EURUSD   |  201801 | 2018-01-15T00:00:00+00:00 |                    5 |    0.997154 | inferred      |
| EURUSD   |  201801 | 2018-01-16T00:00:00+00:00 |                    5 |    0.997097 | inferred      |
| EURUSD   |  201801 | 2018-01-17T00:00:00+00:00 |                    5 |    0.997079 | inferred      |
| EURUSD   |  201801 | 2018-01-18T00:00:00+00:00 |                    5 |    0.996311 | inferred      |
| EURUSD   |  201801 | 2018-01-19T00:00:00+00:00 |                    5 |    0.99639  | inferred      |
| EURUSD   |  201801 | 2018-01-20T00:00:00+00:00 |                    5 |  nan        | carry_forward |

## Coverage Snapshot

| hour_start_utc            |   reference_minutes |   candidate_minutes |   coverage_ratio_candidate_vs_reference | symbol   |   month | lens   |
|:--------------------------|--------------------:|--------------------:|----------------------------------------:|:---------|--------:|:-------|
| 2018-01-01 22:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-01 23:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 00:00:00+00:00 |                  60 |                  58 |                                0.966667 | EURUSD   |  201801 | as_is  |
| 2018-01-02 01:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 02:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 03:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 04:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 05:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 06:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 07:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 08:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 09:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 10:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 11:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 12:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 13:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 14:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 15:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 16:00:00+00:00 |                  60 |                  60 |                                1        | EURUSD   |  201801 | as_is  |
| 2018-01-02 17:00:00+00:00 |                  60 |                  59 |                                0.983333 | EURUSD   |  201801 | as_is  |

## Interpretation

- `as_is` reflects the exact parquet timestamps your models consume today.
- `lag_corrected` is diagnostic and isolates whole-hour timestamp policy drift from genuine quote-path differences.
- Dukascopy remains the reference feed; remaining spread or cadence differences after correction indicate feed microstructure divergence rather than a pure timezone issue.

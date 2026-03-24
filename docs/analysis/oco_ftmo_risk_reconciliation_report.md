# FTMO Risk Reservation Reconciliation Report

- generated_at_utc: `2026-03-23T20:05:01Z`
- runtime_db_path: `data/db/behemoth_runtime.db`
- event_lookback_days: `30`
- stale_pending_hours: `6.0`
- stale_open_hours: `72.0`
- reconciliation_csv: `data/analysis/tick_opportunity_mining/ftmo_reservation_reconciliation.csv`

## Failed Symbols
| symbol   |   pending_count |   open_count |   admitted_events |   blocked_events |   stale_pending_count |   open_without_broker_pos_count |   open_missing_trade_count |   admitted_missing_reservation_id_count |   admitted_unknown_reservation_id_count | reconciliation_pass   |
|:---------|----------------:|-------------:|------------------:|-----------------:|----------------------:|--------------------------------:|---------------------------:|----------------------------------------:|----------------------------------------:|:----------------------|
| EURUSD   |               0 |            0 |               115 |               81 |                     0 |                               0 |                          0 |                                       0 |                                      26 | False                 |

## Full Reconciliation
| symbol   |   pending_count |   open_count |   admitted_events |   blocked_events |   stale_pending_count |   open_without_broker_pos_count |   open_missing_trade_count |   admitted_missing_reservation_id_count |   admitted_unknown_reservation_id_count | reconciliation_pass   |   active_reserved_loss_ccy |
|:---------|----------------:|-------------:|------------------:|-----------------:|----------------------:|--------------------------------:|---------------------------:|----------------------------------------:|----------------------------------------:|:----------------------|---------------------------:|
| AUDUSD   |               0 |            0 |                 0 |              298 |                     0 |                               0 |                          0 |                                       0 |                                       0 | True                  |                      0     |
| EURUSD   |               0 |            0 |               115 |               81 |                     0 |                               0 |                          0 |                                       0 |                                      26 | False                 |                      0     |
| GBPUSD   |               0 |            2 |               165 |             1748 |                     0 |                               0 |                          0 |                                       0 |                                       0 | True                  |                      9.424 |
| USDCAD   |               0 |            0 |                 1 |              420 |                     0 |                               0 |                          0 |                                       0 |                                       0 | True                  |                      0     |
| USDCHF   |               0 |            0 |                 0 |              279 |                     0 |                               0 |                          0 |                                       0 |                                       0 | True                  |                      0     |
| USDJPY   |               0 |            0 |                 1 |             2092 |                     0 |                               0 |                          0 |                                       0 |                                       0 | True                  |                      0     |
| ALL      |               0 |            2 |               282 |             4918 |                     0 |                               0 |                          0 |                                       0 |                                      26 | False                 |                      9.424 |
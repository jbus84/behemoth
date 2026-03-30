# Account Risk Reservation Reconciliation Report

- generated_at_utc: `2026-03-30T10:10:56Z`
- runtime_db_path: `data/db/behemoth_runtime.db`
- event_lookback_days: `30`
- stale_pending_hours: `6.0`
- stale_open_hours: `72.0`
- reconciliation_csv: `data/analysis/tick_opportunity_mining/account_risk_reservation_reconciliation.csv`

## Failed Symbols
| symbol   |   pending_count |   open_count |   admitted_events |   blocked_events |   stale_pending_count |   open_without_broker_pos_count |   open_missing_trade_count |   admitted_missing_reservation_id_count |   admitted_unknown_reservation_id_count | reconciliation_pass   |
|:---------|----------------:|-------------:|------------------:|-----------------:|----------------------:|--------------------------------:|---------------------------:|----------------------------------------:|----------------------------------------:|:----------------------|
| EURUSD   |               4 |            0 |                15 |               10 |                     4 |                               0 |                          0 |                                       0 |                                       5 | False                 |

## Full Reconciliation
| symbol   |   pending_count |   open_count |   admitted_events |   blocked_events |   stale_pending_count |   open_without_broker_pos_count |   open_missing_trade_count |   admitted_missing_reservation_id_count |   admitted_unknown_reservation_id_count | reconciliation_pass   |   active_reserved_loss_ccy |
|:---------|----------------:|-------------:|------------------:|-----------------:|----------------------:|--------------------------------:|---------------------------:|----------------------------------------:|----------------------------------------:|:----------------------|---------------------------:|
| AUDUSD   |               0 |            0 |                 0 |                0 |                     0 |                               0 |                          0 |                                       0 |                                       0 | True                  |                          0 |
| EURUSD   |               4 |            0 |                15 |               10 |                     4 |                               0 |                          0 |                                       0 |                                       5 | False                 |                         45 |
| GBPUSD   |               0 |            0 |                 0 |                0 |                     0 |                               0 |                          0 |                                       0 |                                       0 | True                  |                          0 |
| USDCAD   |               0 |            0 |                 0 |                0 |                     0 |                               0 |                          0 |                                       0 |                                       0 | True                  |                          0 |
| USDCHF   |               0 |            0 |                 0 |                0 |                     0 |                               0 |                          0 |                                       0 |                                       0 | True                  |                          0 |
| USDJPY   |               0 |            0 |                 0 |                0 |                     0 |                               0 |                          0 |                                       0 |                                       0 | True                  |                          0 |
| ALL      |               4 |            0 |                15 |               10 |                     4 |                               0 |                          0 |                                       0 |                                       5 | False                 |                         45 |
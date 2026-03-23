# FTMO Allocator Monitoring Report

- generated_at_utc: `2026-03-23T14:44:51Z`
- runtime_db_path: `data/db/behemoth_runtime.db`
- lookback_days: `7`
- metrics_csv: `data/analysis/tick_opportunity_mining/ftmo_allocator_monitoring_metrics.csv`
- alerts_csv: `data/analysis/tick_opportunity_mining/ftmo_allocator_monitoring_alerts.csv`

## Alert Bands
| symbol   | band   |   rows |
|:---------|:-------|-------:|
| AUDUSD   | green  |      6 |
| EURUSD   | amber  |      2 |
| EURUSD   | green  |      2 |
| EURUSD   | red    |      2 |
| GBPUSD   | green  |      6 |
| USDCAD   | green  |      6 |
| USDCHF   | green  |      6 |
| USDJPY   | green  |      6 |

## Snapshot By Symbol
| symbol   |   FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |   FTMO_ALLOC_BLOCK_RATE |   FTMO_ALLOC_BUDGET_EXCEEDED_RATE |   FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT |   FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE |   FTMO_ALLOC_STALE_PENDING_COUNT |
|:---------|---------------------------------------------------:|------------------------:|----------------------------------:|-------------------------------------------:|----------------------------------------:|---------------------------------:|
| AUDUSD   |                                                  0 |                     0   |                               0   |                                          0 |                                       0 |                                0 |
| EURUSD   |                                                 15 |                     0.4 |                               0.2 |                                          0 |                                       0 |                                4 |
| GBPUSD   |                                                  0 |                     0   |                               0   |                                          0 |                                       0 |                                0 |
| USDCAD   |                                                  0 |                     0   |                               0   |                                          0 |                                       0 |                                0 |
| USDCHF   |                                                  0 |                     0   |                               0   |                                          0 |                                       0 |                                0 |
| USDJPY   |                                                  0 |                     0   |                               0   |                                          0 |                                       0 |                                0 |

## Full Alerts
| source_alert   | symbol   | test_month   | metric_id                                        |   metric_value |   warn_threshold |   fail_threshold | band   | severity   | source_path                 | details_json                                                                                                                       | evaluated_at_utc     |
|:---------------|:---------|:-------------|:-------------------------------------------------|---------------:|-----------------:|-----------------:|:-------|:-----------|:----------------------------|:-----------------------------------------------------------------------------------------------------------------------------------|:---------------------|
| ftmo_allocator | AUDUSD   | 2026-03      | FTMO_ALLOC_BLOCK_RATE                            |            0   |            0.35  |             0.55 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | AUDUSD   | 2026-03      | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |            0   |            0.15  |             0.3  | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | AUDUSD   | 2026-03      | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |            0   |            0.005 |             0.02 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | AUDUSD   | 2026-03      | FTMO_ALLOC_STALE_PENDING_COUNT                   |            0   |            1     |             3    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | AUDUSD   | 2026-03      | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |            0   |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | AUDUSD   | 2026-03      | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |            0   |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | EURUSD   | 2026-03      | FTMO_ALLOC_BLOCK_RATE                            |            0.4 |            0.35  |             0.55 | amber  | medium     | data/db/behemoth_runtime.db | {"admitted": 45, "blocked": 30, "lookback_days": 7, "preselected_total": 75, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-23T14:44:51Z |
| ftmo_allocator | EURUSD   | 2026-03      | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |            0.2 |            0.15  |             0.3  | amber  | medium     | data/db/behemoth_runtime.db | {"admitted": 45, "blocked": 30, "lookback_days": 7, "preselected_total": 75, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-23T14:44:51Z |
| ftmo_allocator | EURUSD   | 2026-03      | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |            0   |            0.005 |             0.02 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 45, "blocked": 30, "lookback_days": 7, "preselected_total": 75, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-23T14:44:51Z |
| ftmo_allocator | EURUSD   | 2026-03      | FTMO_ALLOC_STALE_PENDING_COUNT                   |            4   |            1     |             3    | red    | high       | data/db/behemoth_runtime.db | {"admitted": 45, "blocked": 30, "lookback_days": 7, "preselected_total": 75, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-23T14:44:51Z |
| ftmo_allocator | EURUSD   | 2026-03      | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |            0   |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 45, "blocked": 30, "lookback_days": 7, "preselected_total": 75, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-23T14:44:51Z |
| ftmo_allocator | EURUSD   | 2026-03      | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |           15   |            1     |             2    | red    | high       | data/db/behemoth_runtime.db | {"admitted": 45, "blocked": 30, "lookback_days": 7, "preselected_total": 75, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-23T14:44:51Z |
| ftmo_allocator | GBPUSD   | 2026-03      | FTMO_ALLOC_BLOCK_RATE                            |            0   |            0.35  |             0.55 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 79, "blocked": 0, "lookback_days": 7, "preselected_total": 79, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}  | 2026-03-23T14:44:51Z |
| ftmo_allocator | GBPUSD   | 2026-03      | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |            0   |            0.15  |             0.3  | green  | info       | data/db/behemoth_runtime.db | {"admitted": 79, "blocked": 0, "lookback_days": 7, "preselected_total": 79, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}  | 2026-03-23T14:44:51Z |
| ftmo_allocator | GBPUSD   | 2026-03      | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |            0   |            0.005 |             0.02 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 79, "blocked": 0, "lookback_days": 7, "preselected_total": 79, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}  | 2026-03-23T14:44:51Z |
| ftmo_allocator | GBPUSD   | 2026-03      | FTMO_ALLOC_STALE_PENDING_COUNT                   |            0   |            1     |             3    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 79, "blocked": 0, "lookback_days": 7, "preselected_total": 79, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}  | 2026-03-23T14:44:51Z |
| ftmo_allocator | GBPUSD   | 2026-03      | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |            0   |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 79, "blocked": 0, "lookback_days": 7, "preselected_total": 79, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}  | 2026-03-23T14:44:51Z |
| ftmo_allocator | GBPUSD   | 2026-03      | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |            0   |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 79, "blocked": 0, "lookback_days": 7, "preselected_total": 79, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}  | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDCAD   | 2026-03      | FTMO_ALLOC_BLOCK_RATE                            |            0   |            0.35  |             0.55 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDCAD   | 2026-03      | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |            0   |            0.15  |             0.3  | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDCAD   | 2026-03      | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |            0   |            0.005 |             0.02 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDCAD   | 2026-03      | FTMO_ALLOC_STALE_PENDING_COUNT                   |            0   |            1     |             3    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDCAD   | 2026-03      | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |            0   |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDCAD   | 2026-03      | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |            0   |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDCHF   | 2026-03      | FTMO_ALLOC_BLOCK_RATE                            |            0   |            0.35  |             0.55 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDCHF   | 2026-03      | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |            0   |            0.15  |             0.3  | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDCHF   | 2026-03      | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |            0   |            0.005 |             0.02 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDCHF   | 2026-03      | FTMO_ALLOC_STALE_PENDING_COUNT                   |            0   |            1     |             3    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDCHF   | 2026-03      | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |            0   |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDCHF   | 2026-03      | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |            0   |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDJPY   | 2026-03      | FTMO_ALLOC_BLOCK_RATE                            |            0   |            0.35  |             0.55 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDJPY   | 2026-03      | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |            0   |            0.15  |             0.3  | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDJPY   | 2026-03      | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |            0   |            0.005 |             0.02 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDJPY   | 2026-03      | FTMO_ALLOC_STALE_PENDING_COUNT                   |            0   |            1     |             3    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDJPY   | 2026-03      | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |            0   |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |
| ftmo_allocator | USDJPY   | 2026-03      | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |            0   |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0}    | 2026-03-23T14:44:51Z |

## Full Metrics
|   stage_id | symbol   | metric_id                                        |   metric_value | source_path                 | evaluated_at_utc     |
|-----------:|:---------|:-------------------------------------------------|---------------:|:----------------------------|:---------------------|
|         10 | AUDUSD   | FTMO_ALLOC_BLOCK_RATE                            |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | AUDUSD   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | AUDUSD   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | AUDUSD   | FTMO_ALLOC_STALE_PENDING_COUNT                   |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | AUDUSD   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | AUDUSD   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | AUDUSD   | FTMO_ALLOC_EVENT_ROWS_LOOKBACK                   |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | AUDUSD   | FTMO_ALLOC_ADMITTED_ROWS_LOOKBACK                |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | AUDUSD   | FTMO_ALLOC_BLOCKED_ROWS_LOOKBACK                 |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | AUDUSD   | FTMO_ALLOC_STALE_OPEN_COUNT                      |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | EURUSD   | FTMO_ALLOC_BLOCK_RATE                            |            0.4 | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | EURUSD   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |            0.2 | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | EURUSD   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | EURUSD   | FTMO_ALLOC_STALE_PENDING_COUNT                   |            4   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | EURUSD   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | EURUSD   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |           15   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | EURUSD   | FTMO_ALLOC_EVENT_ROWS_LOOKBACK                   |           75   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | EURUSD   | FTMO_ALLOC_ADMITTED_ROWS_LOOKBACK                |           45   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | EURUSD   | FTMO_ALLOC_BLOCKED_ROWS_LOOKBACK                 |           30   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | EURUSD   | FTMO_ALLOC_STALE_OPEN_COUNT                      |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | GBPUSD   | FTMO_ALLOC_BLOCK_RATE                            |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | GBPUSD   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | GBPUSD   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | GBPUSD   | FTMO_ALLOC_STALE_PENDING_COUNT                   |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | GBPUSD   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | GBPUSD   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | GBPUSD   | FTMO_ALLOC_EVENT_ROWS_LOOKBACK                   |           79   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | GBPUSD   | FTMO_ALLOC_ADMITTED_ROWS_LOOKBACK                |           79   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | GBPUSD   | FTMO_ALLOC_BLOCKED_ROWS_LOOKBACK                 |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | GBPUSD   | FTMO_ALLOC_STALE_OPEN_COUNT                      |            2   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCAD   | FTMO_ALLOC_BLOCK_RATE                            |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCAD   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCAD   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCAD   | FTMO_ALLOC_STALE_PENDING_COUNT                   |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCAD   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCAD   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCAD   | FTMO_ALLOC_EVENT_ROWS_LOOKBACK                   |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCAD   | FTMO_ALLOC_ADMITTED_ROWS_LOOKBACK                |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCAD   | FTMO_ALLOC_BLOCKED_ROWS_LOOKBACK                 |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCAD   | FTMO_ALLOC_STALE_OPEN_COUNT                      |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCHF   | FTMO_ALLOC_BLOCK_RATE                            |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCHF   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCHF   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCHF   | FTMO_ALLOC_STALE_PENDING_COUNT                   |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCHF   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCHF   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCHF   | FTMO_ALLOC_EVENT_ROWS_LOOKBACK                   |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCHF   | FTMO_ALLOC_ADMITTED_ROWS_LOOKBACK                |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCHF   | FTMO_ALLOC_BLOCKED_ROWS_LOOKBACK                 |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDCHF   | FTMO_ALLOC_STALE_OPEN_COUNT                      |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDJPY   | FTMO_ALLOC_BLOCK_RATE                            |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDJPY   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDJPY   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDJPY   | FTMO_ALLOC_STALE_PENDING_COUNT                   |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDJPY   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDJPY   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDJPY   | FTMO_ALLOC_EVENT_ROWS_LOOKBACK                   |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDJPY   | FTMO_ALLOC_ADMITTED_ROWS_LOOKBACK                |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDJPY   | FTMO_ALLOC_BLOCKED_ROWS_LOOKBACK                 |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
|         10 | USDJPY   | FTMO_ALLOC_STALE_OPEN_COUNT                      |            0   | data/db/behemoth_runtime.db | 2026-03-23T14:44:51Z |
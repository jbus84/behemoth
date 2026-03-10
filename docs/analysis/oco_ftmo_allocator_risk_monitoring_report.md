# FTMO Allocator Monitoring Report

- generated_at_utc: `2026-03-10T10:13:08Z`
- runtime_db_path: `data/db/behemoth_runtime.db`
- lookback_days: `7`
- metrics_csv: `data/analysis/tick_opportunity_mining/ftmo_allocator_monitoring_metrics.csv`
- alerts_csv: `data/analysis/tick_opportunity_mining/ftmo_allocator_monitoring_alerts.csv`

## Alert Bands
| symbol   | band   |   rows |
|:---------|:-------|-------:|
| AUDUSD   | green  |      6 |
| EURUSD   | green  |      4 |
| EURUSD   | red    |      2 |
| GBPUSD   | green  |      6 |
| USDCAD   | green  |      6 |
| USDCHF   | green  |      6 |
| USDJPY   | green  |      6 |

## Snapshot By Symbol
| symbol   |   FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |   FTMO_ALLOC_BLOCK_RATE |   FTMO_ALLOC_BUDGET_EXCEEDED_RATE |   FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT |   FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE |   FTMO_ALLOC_STALE_PENDING_COUNT |
|:---------|---------------------------------------------------:|------------------------:|----------------------------------:|-------------------------------------------:|----------------------------------------:|---------------------------------:|
| AUDUSD   |                                                  0 |                0        |                          0        |                                          0 |                                       0 |                                0 |
| EURUSD   |                                                  0 |                0.333333 |                          0.333333 |                                          0 |                                       0 |                                4 |
| GBPUSD   |                                                  0 |                0        |                          0        |                                          0 |                                       0 |                                0 |
| USDCAD   |                                                  0 |                0        |                          0        |                                          0 |                                       0 |                                0 |
| USDCHF   |                                                  0 |                0        |                          0        |                                          0 |                                       0 |                                0 |
| USDJPY   |                                                  0 |                0        |                          0        |                                          0 |                                       0 |                                0 |

## Full Alerts
| source_alert   | symbol   | test_month   | metric_id                                        |   metric_value |   warn_threshold |   fail_threshold | band   | severity   | source_path                 | details_json                                                                                                                    | evaluated_at_utc     |
|:---------------|:---------|:-------------|:-------------------------------------------------|---------------:|-----------------:|-----------------:|:-------|:-----------|:----------------------------|:--------------------------------------------------------------------------------------------------------------------------------|:---------------------|
| ftmo_allocator | AUDUSD   | 2026-03      | FTMO_ALLOC_BLOCK_RATE                            |       0        |            0.35  |             0.55 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | AUDUSD   | 2026-03      | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |       0        |            0.15  |             0.3  | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | AUDUSD   | 2026-03      | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |       0        |            0.005 |             0.02 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | AUDUSD   | 2026-03      | FTMO_ALLOC_STALE_PENDING_COUNT                   |       0        |            1     |             3    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | AUDUSD   | 2026-03      | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |       0        |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | AUDUSD   | 2026-03      | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |       0        |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | EURUSD   | 2026-03      | FTMO_ALLOC_BLOCK_RATE                            |       0.333333 |            0.35  |             0.55 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 4, "blocked": 2, "lookback_days": 7, "preselected_total": 6, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | EURUSD   | 2026-03      | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |       0.333333 |            0.15  |             0.3  | red    | high       | data/db/behemoth_runtime.db | {"admitted": 4, "blocked": 2, "lookback_days": 7, "preselected_total": 6, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | EURUSD   | 2026-03      | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |       0        |            0.005 |             0.02 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 4, "blocked": 2, "lookback_days": 7, "preselected_total": 6, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | EURUSD   | 2026-03      | FTMO_ALLOC_STALE_PENDING_COUNT                   |       4        |            1     |             3    | red    | high       | data/db/behemoth_runtime.db | {"admitted": 4, "blocked": 2, "lookback_days": 7, "preselected_total": 6, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | EURUSD   | 2026-03      | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |       0        |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 4, "blocked": 2, "lookback_days": 7, "preselected_total": 6, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | EURUSD   | 2026-03      | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |       0        |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 4, "blocked": 2, "lookback_days": 7, "preselected_total": 6, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | GBPUSD   | 2026-03      | FTMO_ALLOC_BLOCK_RATE                            |       0        |            0.35  |             0.55 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | GBPUSD   | 2026-03      | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |       0        |            0.15  |             0.3  | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | GBPUSD   | 2026-03      | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |       0        |            0.005 |             0.02 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | GBPUSD   | 2026-03      | FTMO_ALLOC_STALE_PENDING_COUNT                   |       0        |            1     |             3    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | GBPUSD   | 2026-03      | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |       0        |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | GBPUSD   | 2026-03      | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |       0        |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDCAD   | 2026-03      | FTMO_ALLOC_BLOCK_RATE                            |       0        |            0.35  |             0.55 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDCAD   | 2026-03      | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |       0        |            0.15  |             0.3  | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDCAD   | 2026-03      | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |       0        |            0.005 |             0.02 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDCAD   | 2026-03      | FTMO_ALLOC_STALE_PENDING_COUNT                   |       0        |            1     |             3    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDCAD   | 2026-03      | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |       0        |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDCAD   | 2026-03      | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |       0        |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDCHF   | 2026-03      | FTMO_ALLOC_BLOCK_RATE                            |       0        |            0.35  |             0.55 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDCHF   | 2026-03      | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |       0        |            0.15  |             0.3  | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDCHF   | 2026-03      | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |       0        |            0.005 |             0.02 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDCHF   | 2026-03      | FTMO_ALLOC_STALE_PENDING_COUNT                   |       0        |            1     |             3    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDCHF   | 2026-03      | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |       0        |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDCHF   | 2026-03      | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |       0        |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDJPY   | 2026-03      | FTMO_ALLOC_BLOCK_RATE                            |       0        |            0.35  |             0.55 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDJPY   | 2026-03      | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |       0        |            0.15  |             0.3  | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDJPY   | 2026-03      | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |       0        |            0.005 |             0.02 | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDJPY   | 2026-03      | FTMO_ALLOC_STALE_PENDING_COUNT                   |       0        |            1     |             3    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDJPY   | 2026-03      | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |       0        |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |
| ftmo_allocator | USDJPY   | 2026-03      | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |       0        |            1     |             2    | green  | info       | data/db/behemoth_runtime.db | {"admitted": 0, "blocked": 0, "lookback_days": 7, "preselected_total": 0, "stale_open_hours": 72.0, "stale_pending_hours": 6.0} | 2026-03-10T10:13:08Z |

## Full Metrics
|   stage_id | symbol   | metric_id                                        |   metric_value | source_path                 | evaluated_at_utc     |
|-----------:|:---------|:-------------------------------------------------|---------------:|:----------------------------|:---------------------|
|         10 | AUDUSD   | FTMO_ALLOC_BLOCK_RATE                            |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | AUDUSD   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | AUDUSD   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | AUDUSD   | FTMO_ALLOC_STALE_PENDING_COUNT                   |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | AUDUSD   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | AUDUSD   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | AUDUSD   | FTMO_ALLOC_EVENT_ROWS_LOOKBACK                   |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | AUDUSD   | FTMO_ALLOC_ADMITTED_ROWS_LOOKBACK                |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | AUDUSD   | FTMO_ALLOC_BLOCKED_ROWS_LOOKBACK                 |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | AUDUSD   | FTMO_ALLOC_STALE_OPEN_COUNT                      |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | EURUSD   | FTMO_ALLOC_BLOCK_RATE                            |       0.333333 | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | EURUSD   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |       0.333333 | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | EURUSD   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | EURUSD   | FTMO_ALLOC_STALE_PENDING_COUNT                   |       4        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | EURUSD   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | EURUSD   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | EURUSD   | FTMO_ALLOC_EVENT_ROWS_LOOKBACK                   |       6        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | EURUSD   | FTMO_ALLOC_ADMITTED_ROWS_LOOKBACK                |       4        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | EURUSD   | FTMO_ALLOC_BLOCKED_ROWS_LOOKBACK                 |       2        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | EURUSD   | FTMO_ALLOC_STALE_OPEN_COUNT                      |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | GBPUSD   | FTMO_ALLOC_BLOCK_RATE                            |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | GBPUSD   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | GBPUSD   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | GBPUSD   | FTMO_ALLOC_STALE_PENDING_COUNT                   |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | GBPUSD   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | GBPUSD   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | GBPUSD   | FTMO_ALLOC_EVENT_ROWS_LOOKBACK                   |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | GBPUSD   | FTMO_ALLOC_ADMITTED_ROWS_LOOKBACK                |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | GBPUSD   | FTMO_ALLOC_BLOCKED_ROWS_LOOKBACK                 |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | GBPUSD   | FTMO_ALLOC_STALE_OPEN_COUNT                      |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCAD   | FTMO_ALLOC_BLOCK_RATE                            |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCAD   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCAD   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCAD   | FTMO_ALLOC_STALE_PENDING_COUNT                   |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCAD   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCAD   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCAD   | FTMO_ALLOC_EVENT_ROWS_LOOKBACK                   |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCAD   | FTMO_ALLOC_ADMITTED_ROWS_LOOKBACK                |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCAD   | FTMO_ALLOC_BLOCKED_ROWS_LOOKBACK                 |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCAD   | FTMO_ALLOC_STALE_OPEN_COUNT                      |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCHF   | FTMO_ALLOC_BLOCK_RATE                            |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCHF   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCHF   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCHF   | FTMO_ALLOC_STALE_PENDING_COUNT                   |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCHF   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCHF   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCHF   | FTMO_ALLOC_EVENT_ROWS_LOOKBACK                   |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCHF   | FTMO_ALLOC_ADMITTED_ROWS_LOOKBACK                |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCHF   | FTMO_ALLOC_BLOCKED_ROWS_LOOKBACK                 |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDCHF   | FTMO_ALLOC_STALE_OPEN_COUNT                      |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDJPY   | FTMO_ALLOC_BLOCK_RATE                            |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDJPY   | FTMO_ALLOC_BUDGET_EXCEEDED_RATE                  |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDJPY   | FTMO_ALLOC_PIP_VALUE_UNAVAILABLE_RATE            |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDJPY   | FTMO_ALLOC_STALE_PENDING_COUNT                   |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDJPY   | FTMO_ALLOC_OPEN_WITHOUT_BROKER_POS_COUNT         |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDJPY   | FTMO_ALLOC_ADMITTED_MISSING_RESERVATION_ID_COUNT |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDJPY   | FTMO_ALLOC_EVENT_ROWS_LOOKBACK                   |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDJPY   | FTMO_ALLOC_ADMITTED_ROWS_LOOKBACK                |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDJPY   | FTMO_ALLOC_BLOCKED_ROWS_LOOKBACK                 |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |
|         10 | USDJPY   | FTMO_ALLOC_STALE_OPEN_COUNT                      |       0        | data/db/behemoth_runtime.db | 2026-03-10T10:13:08Z |